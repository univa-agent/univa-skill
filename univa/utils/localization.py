"""Caption, transcription, translation, and localization helpers."""

from __future__ import annotations

import importlib.util
import json
import os
import re
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional


_TIMECODE_RE = re.compile(
    r"(?P<sh>\d{1,2}):(?P<sm>\d{2}):(?P<ss>\d{2})[,.](?P<sms>\d{3})\s*-->\s*"
    r"(?P<eh>\d{1,2}):(?P<em>\d{2}):(?P<es>\d{2})[,.](?P<ems>\d{3})"
)


def _seconds(hours: str, minutes: str, seconds: str, millis: str) -> float:
    return int(hours) * 3600 + int(minutes) * 60 + int(seconds) + int(millis) / 1000


def _timecode(value: float, separator: str = ",") -> str:
    milliseconds = max(0, round(float(value) * 1000))
    hours, remainder = divmod(milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    seconds, millis = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}{separator}{millis:03d}"


def parse_captions(value: str, format_hint: Optional[str] = None) -> List[Dict[str, Any]]:
    """Parse SRT or WebVTT text into normalized caption cues."""
    text = value.replace("\r\n", "\n").strip()
    if text.startswith("WEBVTT"):
        text = text.partition("\n")[2].lstrip()
    cues = []
    blocks = re.split(r"\n\s*\n", text)
    for block in blocks:
        lines = [line.strip("\ufeff") for line in block.splitlines() if line.strip()]
        timing_index = next((i for i, line in enumerate(lines) if "-->" in line), None)
        if timing_index is None:
            continue
        match = _TIMECODE_RE.search(lines[timing_index])
        if not match:
            continue
        data = match.groupdict()
        cue_id = lines[timing_index - 1] if timing_index > 0 else str(len(cues) + 1)
        cue_text = "\n".join(lines[timing_index + 1:]).strip()
        if not cue_text:
            continue
        cues.append({
            "id": cue_id,
            "start_seconds": _seconds(data["sh"], data["sm"], data["ss"], data["sms"]),
            "end_seconds": _seconds(data["eh"], data["em"], data["es"], data["ems"]),
            "text": cue_text,
        })
    return normalize_cues(cues)


def normalize_cues(cues: Iterable[Dict[str, Any]], min_duration: float = 0.1) -> List[Dict[str, Any]]:
    """Sort cues and repair invalid durations and overlaps deterministically."""
    normalized = []
    for index, cue in enumerate(cues, start=1):
        try:
            start = max(0.0, float(cue.get("start_seconds", cue.get("startSeconds", 0))))
            end = float(cue.get("end_seconds", cue.get("endSeconds", start + 1.6)))
        except (TypeError, ValueError):
            continue
        text = str(cue.get("text", "")).strip()
        if not text:
            continue
        normalized.append({
            "id": str(cue.get("id", index)),
            "start_seconds": round(start, 3),
            "end_seconds": round(max(end, start + min_duration), 3),
            "text": text,
            **({"source_text": cue["source_text"]} if cue.get("source_text") else {}),
        })
    normalized.sort(key=lambda cue: (cue["start_seconds"], cue["end_seconds"]))
    for index in range(len(normalized) - 1):
        current, following = normalized[index], normalized[index + 1]
        if current["end_seconds"] > following["start_seconds"]:
            boundary = following["start_seconds"]
            if boundary < current["start_seconds"] + min_duration:
                boundary = current["start_seconds"] + min_duration
                following["start_seconds"] = round(boundary, 3)
                following["end_seconds"] = round(
                    max(following["end_seconds"], boundary + min_duration), 3
                )
            current["end_seconds"] = round(boundary, 3)
    return normalized


def write_srt(cues: Iterable[Dict[str, Any]]) -> str:
    blocks = []
    for index, cue in enumerate(normalize_cues(cues), start=1):
        blocks.append(
            f"{index}\n{_timecode(cue['start_seconds'])} --> {_timecode(cue['end_seconds'])}\n{cue['text']}"
        )
    return "\n\n".join(blocks) + ("\n" if blocks else "")


def write_vtt(cues: Iterable[Dict[str, Any]]) -> str:
    blocks = ["WEBVTT"]
    for cue in normalize_cues(cues):
        blocks.append(
            f"{cue['id']}\n{_timecode(cue['start_seconds'], '.')} --> {_timecode(cue['end_seconds'], '.')}\n{cue['text']}"
        )
    return "\n\n".join(blocks) + "\n"


def bilingual_cues(source: Iterable[Dict[str, Any]], translated: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    targets = {str(cue.get("id")): cue for cue in translated}
    result = []
    for cue in normalize_cues(source):
        target = targets.get(cue["id"])
        if not target:
            raise ValueError(f"Missing translated cue: {cue['id']}")
        result.append({**cue, "source_text": cue["text"], "text": f"{cue['text']}\n{str(target.get('text', '')).strip()}"})
    return normalize_cues(result)


def transcribe_media(media_path: str, language: Optional[str] = None, word_timestamps: bool = True, model_size: str = "small") -> Dict[str, Any]:
    """Run optional faster-whisper ASR or report that the backend is unavailable."""
    path = str(Path(media_path).resolve())
    if not os.path.isfile(path):
        return {"success": False, "error": f"Media file not found: {path}", "error_code": "media_not_found"}
    if importlib.util.find_spec("faster_whisper") is None:
        return {
            "success": False,
            "error": "faster-whisper is not installed; no transcript was generated",
            "error_code": "backend_unavailable",
            "backend": "faster-whisper",
        }
    from faster_whisper import WhisperModel

    model = WhisperModel(model_size, device="cpu", compute_type="int8")
    segments, info = model.transcribe(path, language=language, word_timestamps=word_timestamps)
    cues = []
    words = []
    for index, segment in enumerate(segments, start=1):
        cues.append({"id": str(index), "start_seconds": segment.start, "end_seconds": segment.end, "text": segment.text.strip()})
        for word in getattr(segment, "words", None) or []:
            words.append({"word": word.word, "start_seconds": word.start, "end_seconds": word.end, "probability": word.probability})
    return {
        "success": True,
        "backend": "faster-whisper",
        "language": getattr(info, "language", language),
        "language_probability": getattr(info, "language_probability", None),
        "captions": normalize_cues(cues),
        "words": words,
    }


def translate_cues(
    cues: Iterable[Dict[str, Any]],
    target_language: str,
    translator: Callable[[List[Dict[str, Any]], str, Optional[str]], List[Dict[str, Any]]],
    source_language: Optional[str] = None,
) -> Dict[str, Any]:
    source = normalize_cues(cues)
    translated = translator(source, target_language, source_language)
    if not isinstance(translated, list) or len(translated) != len(source):
        return {"success": False, "error": "Translation must preserve the number of caption cues"}
    translated_by_id = {str(item.get("id")): item for item in translated if isinstance(item, dict)}
    output = []
    for cue in source:
        item = translated_by_id.get(cue["id"])
        if not item or not str(item.get("text", "")).strip():
            return {"success": False, "error": f"Missing translation for cue {cue['id']}"}
        output.append({**cue, "source_text": cue["text"], "text": str(item["text"]).strip()})
    return {"success": True, "source_language": source_language, "target_language": target_language, "captions": output}
