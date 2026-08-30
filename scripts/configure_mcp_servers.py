#!/usr/bin/env python3
"""Generate UniVA MCP server config for the active Python interpreter."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


SERVERS = {
    "video_gen": "univa.mcp_tools.video_gen",
    "image_gen": "univa.mcp_tools.image_gen",
    "audio_gen": "univa.mcp_tools.audio_gen",
    "video_editing": "univa.mcp_tools.video_editing",
    "video_understanding": "univa.mcp_tools.video_understanding",
    "video_tracking": "univa.mcp_tools.video_tracking",
}


def build_config(project_root: Path, python_path: str) -> dict[str, object]:
    return {
        "mcpServers": {
            name: {
                "command": python_path,
                "args": ["-m", module],
                "env": {
                    "PYTHONPATH": str(project_root),
                    "CWD": str(project_root),
                },
                "auto_confirm": [],
            }
            for name, module in SERVERS.items()
        }
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Write univa/config/mcp_configs.json for the selected Python interpreter."
    )
    parser.add_argument(
        "--python",
        dest="python_path",
        default=sys.executable,
        help="Python executable used to launch MCP servers. Defaults to the interpreter running this script.",
    )
    parser.add_argument(
        "--project-root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="UniVA repository root. Defaults to the parent directory of scripts/.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the generated config instead of writing it.",
    )
    args = parser.parse_args()

    project_root = args.project_root.resolve()
    out = project_root / "univa" / "config" / "mcp_configs.json"
    config = build_config(project_root, args.python_path)

    payload = json.dumps(config, indent=2) + "\n"
    if args.dry_run:
        print(payload, end="")
        return 0

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(payload, encoding="utf-8")
    print(f"wrote: {out}")
    print(f"python: {args.python_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
