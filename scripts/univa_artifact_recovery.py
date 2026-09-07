#!/usr/bin/env python3
"""Inspect canonical UniVA artifacts when handing interrupted work to an agent."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from univa.utils.artifact_store import ArtifactStore


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a read-only UniVA Artifact recovery snapshot")
    parser.add_argument("--job-id", required=True, help="Pipeline session/job ID")
    parser.add_argument("--project-id", help="Optional project filter")
    parser.add_argument("--output", help="Optional JSON output path; stdout is used otherwise")
    parser.add_argument("--artifact-root")
    parser.add_argument("--artifact-db")
    args = parser.parse_args()

    store = ArtifactStore(root_dir=args.artifact_root, db_path=args.artifact_db)
    snapshot = store.recovery_snapshot(job_id=args.job_id, project_id=args.project_id)
    rendered = json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        output = Path(args.output).expanduser().resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered, encoding="utf-8")
        print(output)
    else:
        print(rendered, end="")


if __name__ == "__main__":
    main()
