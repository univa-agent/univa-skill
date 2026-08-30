#!/usr/bin/env python3
"""Validate UniVA local media runtime without calling remote providers."""

from __future__ import annotations

import importlib
import json
import os
import platform
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def _run(cmd: list[str]) -> tuple[bool, str]:
    try:
        result = subprocess.run(cmd, cwd=PROJECT_ROOT, capture_output=True, text=True, timeout=30)
    except FileNotFoundError:
        return False, "not found"
    except subprocess.TimeoutExpired:
        return False, "timeout"
    output = (result.stdout or result.stderr or "").strip().splitlines()
    return result.returncode == 0, output[0] if output else "ok"


def _import_status(module: str) -> dict[str, Any]:
    try:
        importlib.import_module(module)
        return {"ok": True}
    except Exception as exc:
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}


def _section_ready(config: dict[str, Any], section: str, key_names: list[str] | None = None) -> bool:
    value = config.get(section)
    if not isinstance(value, dict):
        return False
    if key_names:
        return all(key in value for key in key_names)
    return True


def _make_test_video(path: Path, color: str) -> tuple[bool, str]:
    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-f",
        "lavfi",
        "-i",
        f"color=c={color}:s=160x90:d=0.5:r=24",
        "-pix_fmt",
        "yuv420p",
        "-y",
        str(path),
    ]
    return _run(cmd)


def _write_matrix(run_dir: Path, report: dict[str, Any]) -> None:
    lines = [
        "# UniVA Media Runtime Preflight",
        "",
        f"- Python: `{sys.executable}`",
        f"- Version: `{platform.python_version()}`",
        f"- Platform: `{platform.platform()}`",
        f"- Project root: `{PROJECT_ROOT}`",
        f"- FFmpeg: `{report['tools']['ffmpeg']['message']}`",
        f"- FFprobe: `{report['tools']['ffprobe']['message']}`",
        "",
        "## Status",
        "",
    ]
    for name, status in report["summary"].items():
        lines.append(f"- {name}: `{status}`")
    (run_dir / "environment_matrix.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = PROJECT_ROOT / "results" / f"preflight_media_runtime_{timestamp}"
    run_dir.mkdir(parents=True, exist_ok=True)

    report: dict[str, Any] = {
        "created_at": datetime.now().isoformat(),
        "project_root": str(PROJECT_ROOT),
        "python": sys.executable,
        "platform": platform.platform(),
        "tools": {},
        "imports": {},
        "config": {},
        "merge": {},
        "summary": {},
    }

    for tool in ("ffmpeg", "ffprobe"):
        ok, message = _run([tool, "-version"])
        report["tools"][tool] = {"ok": ok, "message": message, "path": shutil.which(tool)}

    for module in ("mcp", "univa", "yaml", "dotenv", "imageio", "requests"):
        report["imports"][module] = _import_status(module)

    try:
        from univa.config.mcp_config import load_mcp_config

        mcp_config = load_mcp_config()
        report["config"] = {
            "loaded": True,
            "sections": sorted(mcp_config.keys()),
            "typed_values": {
                "video_gen.auto_audio": type((mcp_config.get("video_gen") or {}).get("auto_audio")).__name__,
                "video_gen.min_duration_seconds": type((mcp_config.get("video_gen") or {}).get("min_duration_seconds")).__name__,
                "audio_gen.bgm_volume": type((mcp_config.get("audio_gen") or {}).get("bgm_volume")).__name__,
            },
        }
    except Exception as exc:
        mcp_config = {}
        report["config"] = {"loaded": False, "error": f"{type(exc).__name__}: {exc}"}

    merge_ok = False
    if report["tools"].get("ffmpeg", {}).get("ok") and report["tools"].get("ffprobe", {}).get("ok"):
        try:
            from univa.utils.video_process import merge_videos

            first = run_dir / "preflight_a.mp4"
            second = run_dir / "preflight_b.mp4"
            output = run_dir / "preflight_merged.mp4"
            first_ok, first_msg = _make_test_video(first, "red")
            second_ok, second_msg = _make_test_video(second, "blue")
            if first_ok and second_ok:
                merged = merge_videos([str(first), str(second)], output_file=str(output))
                merge_ok = bool(merged and output.exists() and output.stat().st_size > 0)
                report["merge"] = {"ok": merge_ok, "output_path": str(output), "size_bytes": output.stat().st_size if output.exists() else 0}
            else:
                report["merge"] = {"ok": False, "error": f"test video failed: {first_msg}; {second_msg}"}
        except Exception as exc:
            report["merge"] = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
    else:
        report["merge"] = {"ok": False, "error": "ffmpeg or ffprobe missing"}

    imports_ok = all(item["ok"] for item in report["imports"].values())
    config_ok = bool(report["config"].get("loaded"))
    local_common_ok = imports_ok and report["tools"].get("ffmpeg", {}).get("ok") and report["tools"].get("ffprobe", {}).get("ok") and config_ok

    report["summary"] = {
        "image": "READY_UNTIL_PROVIDER" if local_common_ok and _section_ready(mcp_config, "image_gen") else "CHECK_FAILED",
        "video": "READY_UNTIL_PROVIDER" if local_common_ok and _section_ready(mcp_config, "video_gen") else "CHECK_FAILED",
        "audio": "READY_UNTIL_PROVIDER" if local_common_ok and _section_ready(mcp_config, "audio_gen") else "CHECK_FAILED",
        "video_editing": "READY_UNTIL_PROVIDER" if local_common_ok and _section_ready(mcp_config, "video_editing") else "CHECK_FAILED",
        "merge": "LOCAL_PASS" if merge_ok else "CHECK_FAILED",
    }

    (run_dir / "preflight_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    _write_matrix(run_dir, report)
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))
    print(f"report: {run_dir / 'preflight_report.json'}")
    return 0 if all(value in {"READY_UNTIL_PROVIDER", "LOCAL_PASS"} for value in report["summary"].values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
