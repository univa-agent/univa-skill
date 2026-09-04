"""Lightweight, durable video index with time-coded keyword search.

The first implementation intentionally has no model or vector-database
requirement. It creates useful local metadata and thumbnails immediately, and
leaves caption, transcript and keyword enrichment fields available for VLM/ASR
backends to fill later.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import sqlite3
import subprocess
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional


def _file_hash(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def probe_media(path: str) -> Dict[str, Any]:
    if not os.path.isfile(path):
        raise FileNotFoundError(f"Media file not found: {path}")
    command = [
        "ffprobe", "-v", "error", "-print_format", "json", "-show_format", "-show_streams", path
    ]
    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.strip() or "ffprobe failed")
    data = json.loads(completed.stdout or "{}")
    streams = data.get("streams", [])
    video = next((item for item in streams if item.get("codec_type") == "video"), {})
    audio = [item for item in streams if item.get("codec_type") == "audio"]
    rate = str(video.get("r_frame_rate", "0/1"))
    try:
        numerator, denominator = rate.split("/", 1)
        fps = float(numerator) / float(denominator or 1)
    except (ValueError, ZeroDivisionError):
        fps = 0.0
    duration = float(video.get("duration") or data.get("format", {}).get("duration") or 0.0)
    return {
        "duration_seconds": max(0.0, duration),
        "width": int(video.get("width") or 0),
        "height": int(video.get("height") or 0),
        "fps": fps,
        "video_codec": video.get("codec_name"),
        "audio_streams": len(audio),
        "format": data.get("format", {}).get("format_name"),
    }


class MediaIndex:
    def __init__(self, root_dir: Optional[str] = None, db_path: Optional[str] = None):
        project_root = Path(__file__).resolve().parents[2]
        root = Path(root_dir or os.getenv("UNIVA_MEDIA_INDEX_ROOT") or project_root / "data" / ".univa" / "media_index")
        self.root_dir = root.expanduser()
        self.thumbnail_dir = self.root_dir / "thumbnails"
        self.thumbnail_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = str(Path(db_path or os.getenv("UNIVA_MEDIA_INDEX_DB") or self.root_dir / "index.db").expanduser())
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
                CREATE TABLE IF NOT EXISTS media (
                    media_id TEXT PRIMARY KEY,
                    source_path TEXT NOT NULL UNIQUE,
                    content_hash TEXT NOT NULL,
                    metadata_json TEXT NOT NULL,
                    indexed_at REAL NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS segments (
                    segment_id TEXT PRIMARY KEY,
                    media_id TEXT NOT NULL,
                    start_seconds REAL NOT NULL,
                    end_seconds REAL NOT NULL,
                    thumbnail_path TEXT,
                    caption TEXT NOT NULL DEFAULT '',
                    transcript TEXT NOT NULL DEFAULT '',
                    keywords TEXT NOT NULL DEFAULT '',
                    FOREIGN KEY(media_id) REFERENCES media(media_id),
                    UNIQUE(media_id, start_seconds, end_seconds)
                )
                """
            )
            connection.execute("CREATE INDEX IF NOT EXISTS idx_segments_media ON segments(media_id, start_seconds)")

    def index_video(self, video_path: str, segment_duration_seconds: float = 5.0, force: bool = False) -> Dict[str, Any]:
        path = str(Path(video_path).resolve())
        duration = float(segment_duration_seconds)
        if not math.isfinite(duration) or duration <= 0:
            raise ValueError("segment_duration_seconds must be a positive finite number")
        metadata = probe_media(path)
        if metadata["duration_seconds"] <= 0:
            raise ValueError("Video has no readable duration")
        digest = _file_hash(path)
        with self._connect() as connection:
            existing = connection.execute("SELECT * FROM media WHERE source_path = ?", (path,)).fetchone()
        if existing and existing["content_hash"] == digest and not force:
            return self._index_response(existing["media_id"], path, metadata, reused=True)

        media_id = existing["media_id"] if existing else f"media_{uuid.uuid4().hex}"
        now = time.time()
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO media(media_id, source_path, content_hash, metadata_json, indexed_at) VALUES (?, ?, ?, ?, ?) "
                "ON CONFLICT(source_path) DO UPDATE SET content_hash=excluded.content_hash, metadata_json=excluded.metadata_json, indexed_at=excluded.indexed_at",
                (media_id, path, digest, json.dumps(metadata, sort_keys=True), now),
            )
            connection.execute("DELETE FROM segments WHERE media_id = ?", (media_id,))

        segments = []
        start = 0.0
        while start < metadata["duration_seconds"]:
            end = min(start + duration, metadata["duration_seconds"])
            thumbnail = self._make_thumbnail(path, media_id, start)
            segment = {
                "segment_id": f"segment_{uuid.uuid4().hex}",
                "media_id": media_id,
                "source_path": path,
                "start_seconds": round(start, 3),
                "end_seconds": round(end, 3),
                "thumbnail_path": thumbnail,
                "caption": "",
                "transcript": "",
                "keywords": "",
                "score": None,
            }
            segments.append(segment)
            with self._connect() as connection:
                connection.execute(
                    "INSERT INTO segments(segment_id, media_id, start_seconds, end_seconds, thumbnail_path, caption, transcript, keywords) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (segment["segment_id"], media_id, segment["start_seconds"], segment["end_seconds"], thumbnail, "", "", ""),
                )
            start = end
        return self._index_response(media_id, path, metadata, segments=segments, reused=False)

    def enrich_segments(
        self,
        media_path: str,
        annotations: List[Dict[str, Any]],
        replace_existing: bool = False,
    ) -> Dict[str, Any]:
        """Write trusted time-coded text into overlapping indexed segments."""
        path = str(Path(media_path).resolve())
        if not isinstance(annotations, list) or not annotations:
            raise ValueError("annotations must be a non-empty list")

        normalized = []
        for index, annotation in enumerate(annotations, start=1):
            if not isinstance(annotation, dict):
                raise ValueError(f"annotation {index} must be an object")
            try:
                start = float(annotation.get("start_seconds"))
                end = float(annotation.get("end_seconds"))
            except (TypeError, ValueError) as exc:
                raise ValueError(
                    f"annotation {index} requires numeric start_seconds and end_seconds"
                ) from exc
            if not all(math.isfinite(value) for value in (start, end)) or start < 0 or end <= start:
                raise ValueError(f"annotation {index} has an invalid time range")
            values = {
                "caption": self._annotation_text(annotation.get("caption")),
                "transcript": self._annotation_text(annotation.get("transcript")),
                "keywords": self._annotation_text(annotation.get("keywords"), separator=" "),
            }
            if not any(values.values()):
                raise ValueError(
                    f"annotation {index} must include caption, transcript, or keywords"
                )
            normalized.append({"start_seconds": start, "end_seconds": end, **values})

        with self._connect() as connection:
            media = connection.execute(
                "SELECT * FROM media WHERE source_path = ?", (path,)
            ).fetchone()
            if not media:
                raise ValueError("Video is not indexed; call index_video_media first")
            segments = connection.execute(
                "SELECT * FROM segments WHERE media_id = ? ORDER BY start_seconds",
                (media["media_id"],),
            ).fetchall()
            updated = 0
            for segment in segments:
                overlapping = [
                    item for item in normalized
                    if item["start_seconds"] < segment["end_seconds"]
                    and item["end_seconds"] > segment["start_seconds"]
                ]
                if not overlapping:
                    continue
                changes = {}
                for field in ("caption", "transcript", "keywords"):
                    separator = " " if field == "keywords" else "\n"
                    incoming = separator.join(
                        item[field] for item in overlapping if item[field]
                    )
                    if not incoming:
                        continue
                    changes[field] = (
                        incoming
                        if replace_existing
                        else self._merge_text(segment[field], incoming, separator)
                    )
                if not changes:
                    continue
                connection.execute(
                    "UPDATE segments SET caption = ?, transcript = ?, keywords = ? WHERE segment_id = ?",
                    (
                        changes.get("caption", segment["caption"]),
                        changes.get("transcript", segment["transcript"]),
                        changes.get("keywords", segment["keywords"]),
                        segment["segment_id"],
                    ),
                )
                updated += 1

        metadata = json.loads(media["metadata_json"])
        response = self._index_response(media["media_id"], path, metadata, reused=True)
        response.update({"annotations_applied": len(normalized), "segments_updated": updated})
        return response

    @staticmethod
    def _annotation_text(value: Any, separator: str = "\n") -> str:
        if isinstance(value, list):
            value = separator.join(str(item).strip() for item in value if str(item).strip())
        return str(value or "").strip()

    @staticmethod
    def _merge_text(existing: str, incoming: str, separator: str) -> str:
        parts = []
        for value in (existing, incoming):
            for part in str(value or "").split(separator):
                cleaned = part.strip()
                if cleaned and cleaned not in parts:
                    parts.append(cleaned)
        return separator.join(parts)

    def _make_thumbnail(self, path: str, media_id: str, start: float) -> Optional[str]:
        target = self.thumbnail_dir / f"{media_id}_{int(start * 1000)}.jpg"
        command = [
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-ss", str(start), "-i", path,
            "-frames:v", "1", "-vf", "scale=320:-2", "-y", str(target),
        ]
        completed = subprocess.run(command, capture_output=True, text=True, check=False)
        if completed.returncode == 0 and target.is_file() and target.stat().st_size > 0:
            return str(target.resolve())
        return None

    def _index_response(self, media_id: str, path: str, metadata: Dict[str, Any], *, segments=None, reused=False) -> Dict[str, Any]:
        if segments is None:
            with self._connect() as connection:
                rows = connection.execute("SELECT * FROM segments WHERE media_id = ? ORDER BY start_seconds", (media_id,)).fetchall()
            segments = [self._row_to_segment(row, path) for row in rows]
        return {"success": True, "index_id": media_id, "source_path": path, "metadata": metadata, "reused": reused, "segments": segments}

    @staticmethod
    def _row_to_segment(row: sqlite3.Row, path: str) -> Dict[str, Any]:
        return {
            "segment_id": row["segment_id"], "media_id": row["media_id"], "source_path": path,
            "start_seconds": row["start_seconds"], "end_seconds": row["end_seconds"],
            "thumbnail_path": row["thumbnail_path"], "caption": row["caption"],
            "transcript": row["transcript"], "keywords": row["keywords"], "score": None,
        }

    def search(self, query: str, media_path: Optional[str] = None, top_k: int = 10) -> Dict[str, Any]:
        terms = [term.lower() for term in (query or "").split() if term.strip()]
        if not terms:
            return {"success": False, "error": "query must not be empty", "segments": []}
        params: List[Any] = []
        sql = "SELECT s.*, m.source_path FROM segments s JOIN media m ON m.media_id = s.media_id"
        if media_path:
            sql += " WHERE m.source_path = ?"
            params.append(str(Path(media_path).resolve()))
        with self._connect() as connection:
            rows = connection.execute(sql, params).fetchall()
        matches = []
        for row in rows:
            haystack = " ".join((row["caption"], row["transcript"], row["keywords"])).lower()
            score = sum(1 for term in terms if term in haystack) / len(terms)
            if score > 0:
                segment = self._row_to_segment(row, row["source_path"])
                segment["score"] = round(score, 3)
                matches.append(segment)
        matches.sort(key=lambda item: (-item["score"], item["start_seconds"]))
        return {"success": True, "query": query, "segments": matches[:max(1, int(top_k))], "semantic_search": False}

    def get_moment(self, media_path: str, start_seconds: float, end_seconds: float) -> Dict[str, Any]:
        path = str(Path(media_path).resolve())
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT s.*, m.source_path FROM segments s JOIN media m ON m.media_id = s.media_id WHERE m.source_path = ? AND s.start_seconds < ? AND s.end_seconds > ? ORDER BY s.start_seconds",
                (path, float(end_seconds), float(start_seconds)),
            ).fetchall()
        return {"success": True, "source_path": path, "start_seconds": start_seconds, "end_seconds": end_seconds, "segments": [self._row_to_segment(row, path) for row in rows]}
