"""Durable storage for interactive pipeline state.

The orchestrator keeps a memory cache for fast access, while this store is the
source of truth across process restarts and multiple worker processes. SQLite
is deliberately used here because it is already available in the runtime and
does not introduce another service or dependency.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import sqlite3
import time
from pathlib import Path
from typing import Any, Dict, Optional

from univa.utils.budget_tracker import BudgetTracker


def _json_default(value: Any) -> str:
    return str(value)


class PipelineStateStore:
    """Persist pipeline states and the hash of their continuation token."""

    def __init__(
        self,
        db_path: Optional[str] = None,
        ttl_seconds: int = 7 * 24 * 3600,
        resume_lease_seconds: int = 300,
    ):
        default_path = Path(__file__).resolve().parents[2] / "data" / ".univa" / "pipeline_state.db"
        configured_path = db_path or os.getenv("UNIVA_PIPELINE_STATE_DB") or str(default_path)
        self.db_path = str(Path(configured_path).expanduser())
        self.ttl_seconds = max(60, int(ttl_seconds))
        self.resume_lease_seconds = max(10, int(resume_lease_seconds))
        if self.db_path != ":memory:":
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path, timeout=10)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS pipeline_states (
                    session_id TEXT PRIMARY KEY,
                    pipeline_name TEXT NOT NULL,
                    owner_id TEXT NOT NULL DEFAULT '',
                    project_id TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL,
                    state_json TEXT NOT NULL,
                    continuation_token_hash TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL,
                    expires_at REAL NOT NULL
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_pipeline_states_owner ON pipeline_states(owner_id, project_id)"
            )

    @staticmethod
    def token_hash(token: str) -> str:
        return hashlib.sha256((token or "").encode("utf-8")).hexdigest()

    def save(self, state: Any) -> None:
        """Atomically upsert a state without ever persisting the raw token."""
        now = time.time()
        created_at = float(getattr(state, "created_at", now) or now)
        expires_at = float(getattr(state, "expires_at", 0.0) or now + self.ttl_seconds)
        state.created_at = created_at
        state.updated_at = now
        state.expires_at = expires_at
        state_data = {
            "pipeline_name": state.pipeline_name,
            "session_id": state.session_id,
            "current_stage_index": state.current_stage_index,
            "status": state.status,
            "artifacts": state.artifacts,
            "artifact_records": getattr(state, "artifact_records", {}),
            "budget": state.budget.to_dict() if state.budget else None,
            "interaction_stage": state.interaction_stage,
            "interaction_prompt": state.interaction_prompt,
            "interaction_data": state.interaction_data,
            "stage_timeline": state.stage_timeline,
            "quality_reports": state.quality_reports,
            "send_back_count": state.send_back_count,
            "original_user_request": getattr(state, "original_user_request", ""),
            "created_at": created_at,
            "updated_at": now,
            "expires_at": expires_at,
        }
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO pipeline_states (
                    session_id, pipeline_name, owner_id, project_id, status,
                    state_json, continuation_token_hash, created_at, updated_at, expires_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(session_id) DO UPDATE SET
                    pipeline_name=excluded.pipeline_name,
                    owner_id=excluded.owner_id,
                    project_id=excluded.project_id,
                    status=excluded.status,
                    state_json=excluded.state_json,
                    continuation_token_hash=excluded.continuation_token_hash,
                    updated_at=excluded.updated_at,
                    expires_at=excluded.expires_at
                """,
                (
                    state.session_id,
                    state.pipeline_name,
                    getattr(state, "owner_id", "") or "",
                    getattr(state, "project_id", "") or "",
                    state.status,
                    json.dumps(state_data, ensure_ascii=False, default=_json_default),
                    self.token_hash(getattr(state, "continuation_token", "")),
                    created_at,
                    now,
                    expires_at,
                ),
            )

    def load(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Load a raw persisted row, returning ``None`` for expired sessions."""
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM pipeline_states WHERE session_id = ?", (session_id,)
            ).fetchone()
        if not row:
            return None
        if float(row["expires_at"]) <= time.time():
            self.delete(session_id)
            return None
        data = json.loads(row["state_json"])
        status = row["status"]
        if status == "resuming" and float(row["updated_at"]) <= time.time() - self.resume_lease_seconds:
            status = "awaiting_human"
            data["status"] = status
            data["updated_at"] = time.time()
            with self._connect() as connection:
                connection.execute(
                    "UPDATE pipeline_states SET status = ?, state_json = ?, updated_at = ? WHERE session_id = ? AND status = 'resuming'",
                    (status, json.dumps(data, ensure_ascii=False, default=_json_default), data["updated_at"], session_id),
                )
        else:
            data["status"] = status
        data["owner_id"] = row["owner_id"]
        data["project_id"] = row["project_id"]
        data["continuation_token_hash"] = row["continuation_token_hash"]
        return data

    def claim_resume(self, session_id: str, token: str, owner_id: Optional[str] = None) -> Dict[str, Any]:
        """Atomically claim an awaiting state before any resumed work executes."""
        now = time.time()
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT * FROM pipeline_states WHERE session_id = ?", (session_id,)
            ).fetchone()
            if not row or float(row["expires_at"]) <= now:
                raise ValueError(f"No active pipeline for session '{session_id}'")
            if owner_id is not None and row["owner_id"] and row["owner_id"] != owner_id:
                raise PermissionError(f"Pipeline session '{session_id}' does not belong to this user")
            if not hmac.compare_digest(row["continuation_token_hash"], self.token_hash(token)):
                raise PermissionError("Invalid continuation token")
            stale_resume = (
                row["status"] == "resuming"
                and float(row["updated_at"]) <= now - self.resume_lease_seconds
            )
            if row["status"] != "awaiting_human" and not stale_resume:
                raise ValueError(
                    f"Pipeline session '{session_id}' is not awaiting input (status: {row['status']})"
                )
            data = json.loads(row["state_json"])
            data["status"] = "resuming"
            data["updated_at"] = now
            connection.execute(
                "UPDATE pipeline_states SET status = 'resuming', state_json = ?, updated_at = ? WHERE session_id = ?",
                (json.dumps(data, ensure_ascii=False, default=_json_default), now, session_id),
            )
        data["owner_id"] = row["owner_id"]
        data["project_id"] = row["project_id"]
        data["continuation_token_hash"] = row["continuation_token_hash"]
        return data

    def validate_token(self, session_id: str, token: str) -> bool:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT continuation_token_hash, expires_at FROM pipeline_states WHERE session_id = ?",
                (session_id,),
            ).fetchone()
        if not row or float(row["expires_at"]) <= time.time():
            return False
        return hmac.compare_digest(row["continuation_token_hash"], self.token_hash(token))

    def get_owner(self, session_id: str) -> Optional[str]:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT owner_id FROM pipeline_states WHERE session_id = ?", (session_id,)
            ).fetchone()
        return row["owner_id"] if row else None

    def delete(self, session_id: str) -> None:
        with self._connect() as connection:
            connection.execute("DELETE FROM pipeline_states WHERE session_id = ?", (session_id,))

    def purge_expired(self) -> int:
        with self._connect() as connection:
            cursor = connection.execute(
                "DELETE FROM pipeline_states WHERE expires_at <= ?", (time.time(),)
            )
            return cursor.rowcount
