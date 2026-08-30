import json
import os
import subprocess
from pathlib import Path
from typing import Any


def has_audio_stream(media_path: str) -> bool:
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-select_streams",
        "a:0",
        "-show_entries",
        "stream=codec_type",
        "-of",
        "json",
        media_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        return False
    try:
        data = json.loads(result.stdout or "{}")
    except json.JSONDecodeError:
        return False
    return bool(data.get("streams"))


def _float_value(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def mix_audio_timeline(
    video_path: str,
    audio_events: list[dict[str, Any]],
    output_path: str,
    keep_original_audio: bool = True,
    original_audio_volume: float = 0.35,
    default_event_volume: float = 0.45,
) -> str:
    """Mux a declarative audio timeline onto a video using ffmpeg.

    Each audio event supports:
      path, start_seconds, duration_seconds, volume, fade_in_seconds,
      fade_out_seconds, role, note.
    """
    if not os.path.exists(video_path):
        raise FileNotFoundError(f"Video file not found: {video_path}")

    valid_events = []
    for event in audio_events or []:
        audio_path = event.get("path") or event.get("audio_path") or event.get("file_path")
        if not audio_path or not os.path.exists(str(audio_path)):
            continue
        valid_events.append({**event, "path": str(audio_path)})

    output_dir = os.path.dirname(output_path)
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)

    if not valid_events and not (keep_original_audio and has_audio_stream(video_path)):
        cmd = ["ffmpeg", "-i", video_path, "-c", "copy", "-y", output_path]
        subprocess.run(cmd, check=True)
        return output_path

    cmd = ["ffmpeg", "-i", video_path]
    for event in valid_events:
        cmd.extend(["-i", event["path"]])

    filters: list[str] = []
    mix_labels: list[str] = []

    if keep_original_audio and has_audio_stream(video_path):
        filters.append(f"[0:a]volume={float(original_audio_volume):.3f}[orig]")
        mix_labels.append("[orig]")

    for idx, event in enumerate(valid_events, start=1):
        label = f"a{idx}"
        start_ms = max(0, int(round(_float_value(event.get("start_seconds"), 0.0) * 1000)))
        duration = event.get("duration_seconds")
        volume = _float_value(event.get("volume"), default_event_volume)
        fade_in = max(0.0, _float_value(event.get("fade_in_seconds"), 0.0))
        fade_out = max(0.0, _float_value(event.get("fade_out_seconds"), 0.0))

        chain = f"[{idx}:a]asetpts=PTS-STARTPTS"
        if duration is not None:
            dur = max(0.05, _float_value(duration, 0.05))
            chain += f",atrim=0:{dur:.3f},asetpts=PTS-STARTPTS"
        chain += f",volume={volume:.3f}"
        if fade_in > 0:
            chain += f",afade=t=in:st=0:d={fade_in:.3f}"
        if fade_out > 0 and duration is not None:
            dur = max(0.05, _float_value(duration, 0.05))
            fade_out_start = max(0.0, dur - fade_out)
            chain += f",afade=t=out:st={fade_out_start:.3f}:d={fade_out:.3f}"
        chain += f",adelay={start_ms}|{start_ms}[{label}]"
        filters.append(chain)
        mix_labels.append(f"[{label}]")

    if not mix_labels:
        cmd = ["ffmpeg", "-i", video_path, "-c", "copy", "-y", output_path]
        subprocess.run(cmd, check=True)
        return output_path

    filters.append(f"{''.join(mix_labels)}amix=inputs={len(mix_labels)}:duration=longest[mix]")

    cmd.extend([
        "-filter_complex",
        ";".join(filters),
        "-map",
        "0:v:0",
        "-map",
        "[mix]",
        "-c:v",
        "copy",
        "-c:a",
        "aac",
        "-shortest",
        "-y",
        output_path,
    ])
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg audio timeline mix failed: {result.stderr[-2000:]}")
    return output_path
