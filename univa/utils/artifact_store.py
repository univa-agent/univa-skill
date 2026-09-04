"""Canonical artifact and execution receipt storage.

Pipeline stage output remains backward compatible in ``PipelineState.artifacts``.
This module adds a durable envelope around it so plans, reviews, media results,
and reports can be versioned and traced without replacing existing schemas.
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Any, Dict, Iterable, Optional


def _stable_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str, separators=(",", ":"))


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def content_sha256(value: Any) -> str:
    return _sha256_bytes(_stable_json(value).encode("utf-8"))


def file_sha256(path: str) -> Optional[str]:
    try:
        digest = hashlib.sha256()
        with open(path, "rb") as source:
            for block in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(block)
        return digest.hexdigest()
    except (OSError, TypeError):
        return None


def _source_files(value: Any) -> Iterable[str]:
    if isinstance(value, str):
        if os.path.isfile(value):
            yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from _source_files(item)
    elif isinstance(value, list):
        for item in value:
            yield from _source_files(item)


class ArtifactStore:
    """Store immutable artifact records and append-only execution receipts."""

    def __init__(self, root_dir: Optional[str] = None, db_path: Optional[str] = None):
        project_root = Path(__file__).resolve().parents[2]
        root = Path(root_dir or os.getenv("UNIVA_ARTIFACT_ROOT") or project_root / "data" / ".univa" / "artifacts")
        self.root_dir = root.expanduser()
        self.root_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = str(Path(db_path or os.getenv("UNIVA_ARTIFACT_DB") or self.root_dir.parent / "artifacts.db").expanduser())
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
                CREATE TABLE IF NOT EXISTS artifacts (
                    artifact_id TEXT PRIMARY KEY,
                    artifact_type TEXT NOT NULL,
                    project_id TEXT NOT NULL DEFAULT '',
                    job_id TEXT NOT NULL DEFAULT '',
                    version INTEGER NOT NULL,
                    content_sha256 TEXT NOT NULL,
                    record_json TEXT NOT NULL,
                    created_at REAL NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS execution_receipts (
                    operation_id TEXT PRIMARY KEY,
                    job_id TEXT NOT NULL DEFAULT '',
                    receipt_json TEXT NOT NULL,
                    created_at REAL NOT NULL
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_artifacts_lookup ON artifacts(project_id, job_id, artifact_type, version)"
            )
            connection.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_artifacts_version ON artifacts(project_id, job_id, artifact_type, version)"
            )

    def write_artifact(
        self,
        artifact_type: str,
        content: Any,
        *,
        project_id: str = "",
        job_id: str = "",
        parent_artifact_ids: Optional[list[str]] = None,
        status: str = "draft",
        source_files: Optional[list[str]] = None,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        cost_usd: Optional[float] = None,
        created_by: str = "agent",
        approved_by: Optional[str] = None,
        provenance: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        now = time.time()
        digest = content_sha256(content)
        artifact_id = f"artifact_{uuid.uuid4().hex}"
        files = []
        for path in source_files or list(_source_files(content)):
            resolved = str(Path(path).resolve())
            files.append({"path": resolved, "sha256": file_sha256(resolved)})
        json_path = self.root_dir / f"{artifact_id}.json"
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT COALESCE(MAX(version), 0) AS version FROM artifacts WHERE project_id = ? AND job_id = ? AND artifact_type = ?",
                (project_id or "", job_id or "", artifact_type),
            ).fetchone()
            version = int(row["version"] or 0) + 1
            record = {
                "artifact_id": artifact_id,
                "artifact_type": artifact_type,
                "schema_version": "1.0",
                "version": version,
                "status": status,
                "project_id": project_id or "",
                "job_id": job_id or "",
                "parent_artifact_ids": parent_artifact_ids or [],
                "content": content,
                "content_sha256": digest,
                "source_files": files,
                "provider": provider,
                "model": model,
                "cost_usd": cost_usd,
                "created_by": created_by,
                "approved_by": approved_by,
                "created_at": now,
                "provenance": provenance or {},
                "record_path": str(json_path.resolve()),
            }
            json_path.write_text(_stable_json(record), encoding="utf-8")
            connection.execute(
                "INSERT INTO artifacts (artifact_id, artifact_type, project_id, job_id, version, content_sha256, record_json, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (artifact_id, artifact_type, project_id or "", job_id or "", version, digest, _stable_json(record), now),
            )
        return record

    def write_receipt(self, receipt: Dict[str, Any]) -> Dict[str, Any]:
        value = dict(receipt)
        value.setdefault("operation_id", f"operation_{uuid.uuid4().hex}")
        value.setdefault("created_at", time.time())
        value["input_sha256"] = value.get("input_sha256") or content_sha256(value.get("input"))
        outputs = value.get("output_paths") or []
        if isinstance(outputs, str):
            outputs = [outputs]
        value["output_paths"] = [
            {"path": str(Path(path).resolve()), "sha256": file_sha256(path)}
            for path in outputs
            if path
        ]
        try:
            with self._connect() as connection:
                connection.execute(
                    "INSERT INTO execution_receipts (operation_id, job_id, receipt_json, created_at) VALUES (?, ?, ?, ?)",
                    (value["operation_id"], value.get("job_id", ""), _stable_json(value), value["created_at"]),
                )
        except sqlite3.IntegrityError as exc:
            raise ValueError(
                f"Execution receipt '{value['operation_id']}' already exists and cannot be overwritten"
            ) from exc
        return value

    def get_artifact(self, artifact_id: str) -> Optional[Dict[str, Any]]:
        with self._connect() as connection:
            row = connection.execute("SELECT record_json FROM artifacts WHERE artifact_id = ?", (artifact_id,)).fetchone()
        return json.loads(row["record_json"]) if row else None

    def get_receipt(self, operation_id: str) -> Optional[Dict[str, Any]]:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT receipt_json FROM execution_receipts WHERE operation_id = ?",
                (operation_id,),
            ).fetchone()
        return json.loads(row["receipt_json"]) if row else None
