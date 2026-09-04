"""UniVA localization MCP tools built on existing media runtimes."""

from __future__ import annotations

import json
import os
import uuid
from pathlib import Path
from typing import Any, Optional

from mcp.server.fastmcp import FastMCP

from univa.config.mcp_config import get_mcp_section
from univa.mcp_tools.base import ToolResponse, setup_logger
from univa.utils.localization import (
    bilingual_cues,
    normalize_cues,
    parse_captions,
    transcribe_media as run_transcription,
    translate_cues,
    write_srt,
    write_vtt,
)
from univa.utils.media_index import probe_media
from univa.utils.query_llm import query_openai


logger = setup_logger(__name__, "logs/mcp_tools", "localization.log")
mcp = FastMCP("Localization_Server")
llm_config = get_mcp_section("llm")


def _as_dict(response: Any) -> dict:
    if hasattr(response, "model_dump"):
        return response.model_dump()
    if hasattr(response, "dict"):
        return response.dict()
    return response if isinstance(response, dict) else {"success": False, "error": str(response)}


def _load_cues(captions: Any) -> list[dict[str, Any]]:
    if isinstance(captions, list):
        return normalize_cues(captions)
    if isinstance(captions, str) and os.path.isfile(captions):
        return parse_captions(Path(captions).read_text(encoding="utf-8"), Path(captions).suffix)
    if isinstance(captions, str):
        return parse_captions(captions)
    return []


def _extract_json(content: str) -> dict:
    text = (content or "").strip()
    if text.startswith("```"):
        lines = text.splitlines()
        text = "\n".join(lines[1:-1]).strip()
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end < start:
        raise ValueError("Translation provider did not return a JSON object")
    return json.loads(text[start:end + 1])


@mcp.tool()
def transcribe_media(
    media_path: str,
    language: str = "",
    word_timestamps: bool = True,
    model_size: str = "small",
) -> dict:
    """Transcribe local audio/video with optional faster-whisper ASR."""
    try:
        result = run_transcription(media_path, language or None, word_timestamps, model_size)
        if result.get("success"):
            result["transcript"] = {
                "source_path": str(Path(media_path).resolve()),
                "language": result.get("language"),
                "captions": result.get("captions", []),
                "words": result.get("words", []),
                "backend": result.get("backend"),
            }
        return result
    except Exception as exc:
        logger.exception("Transcription failed")
        return {"success": False, "error": str(exc), "error_code": "transcription_failed"}


@mcp.tool()
def translate_captions(
    captions: Any,
    target_language: str,
    source_language: str = "",
) -> dict:
    """Translate timed captions while preserving cue IDs and timing."""
    source = _load_cues(captions)
    if not source:
        return {"success": False, "error": "No valid caption cues were supplied"}
    api_key = llm_config.get("openai_api_key")
    if not api_key:
        return {
            "success": False,
            "error": "LLM_OPENAI_API_KEY is not configured; no translation was generated",
            "error_code": "backend_unavailable",
        }

    def provider(cues, target, source_lang):
        request = {
            "source_language": source_lang or "auto",
            "target_language": target,
            "captions": [{"id": cue["id"], "text": cue["text"]} for cue in cues],
        }
        prompt = (
            "Translate each caption naturally for video localization. Preserve every id, "
            "do not merge or split cues, and return strict JSON only in the shape "
            "{\"captions\":[{\"id\":\"1\",\"text\":\"...\"}]}.\n"
            + json.dumps(request, ensure_ascii=False)
        )
        response = query_openai(
            api_key=api_key,
            model=llm_config.get("model", "gpt-5"),
            base_url=llm_config.get("base_url", "https://api.openai.com/v1"),
            messages=[{"role": "user", "content": prompt}],
            max_completion_tokens=max(1024, len(cues) * 80),
            temperature=0.2,
        )
        return _extract_json(response.get("content", "")).get("captions", [])

    try:
        result = translate_cues(source, target_language, provider, source_language or None)
    except Exception as exc:
        logger.exception("Caption translation failed")
        return {"success": False, "error": str(exc), "error_code": "translation_failed"}
    if result.get("success"):
        result["localized_captions"] = {
            "source_language": source_language or None,
            "target_language": target_language,
            "captions": result["captions"],
        }
    return result


@mcp.tool()
def prepare_localized_captions(
    captions: Any,
    translated_captions: Any = None,
    bilingual: bool = False,
    output_path: str = "",
    output_format: str = "srt",
) -> dict:
    """Normalize captions, optionally make them bilingual, and write SRT/VTT."""
    source = _load_cues(captions)
    if not source:
        return {"success": False, "error": "No valid caption cues were supplied"}
    try:
        final_cues = (
            bilingual_cues(source, _load_cues(translated_captions))
            if bilingual else normalize_cues(_load_cues(translated_captions) or source)
        )
    except Exception as exc:
        return {"success": False, "error": str(exc)}
    fmt = output_format.lower().lstrip(".")
    if fmt not in {"srt", "vtt"}:
        return {"success": False, "error": "output_format must be srt or vtt"}
    if not output_path:
        directory = Path(__file__).resolve().parents[2] / "results" / "localization"
        directory.mkdir(parents=True, exist_ok=True)
        output_path = str(directory / f"captions_{uuid.uuid4().hex[:12]}.{fmt}")
    target = Path(output_path).resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(write_vtt(final_cues) if fmt == "vtt" else write_srt(final_cues), encoding="utf-8")
    return {
        "success": True,
        "output_path": str(target),
        "caption_count": len(final_cues),
        "captions": final_cues,
        "bilingual": bilingual,
    }


@mcp.tool()
def generate_localized_voiceover(
    video_path: str,
    captions: Any,
    output_path: str = "",
    voice: str = "",
    emotion: str = "neutral",
    keep_original_audio: bool = True,
) -> dict:
    """Generate approved TTS cues and place them on their caption timecodes."""
    cues = _load_cues(captions)
    if not cues:
        return {"success": False, "error": "No valid caption cues were supplied"}
    from univa.mcp_tools.audio_gen import generate_audio_assets_from_plan

    plan = {
        "voiceover_segments": [
            {
                "id": cue["id"],
                "start_seconds": cue["start_seconds"],
                "duration_seconds": cue["end_seconds"] - cue["start_seconds"],
                "text": cue["text"],
                "voice": voice or None,
                "emotion": emotion,
            }
            for cue in cues
        ],
        "mixing": {"original_audio_volume": 0.25 if keep_original_audio else 0.0},
    }
    result = generate_audio_assets_from_plan(
        audio_plan=plan,
        video_path=video_path,
        mux_output_path=output_path or None,
    )
    return _as_dict(result)


@mcp.tool()
def render_localized_video(
    video_path: str,
    captions: Any,
    output_path: str = "",
    bilingual: bool = False,
    aspect_ratio: str = "",
    title: str = "",
) -> dict:
    """Render approved localized captions using UniVA's Remotion/FFmpeg layer."""
    cues = _load_cues(captions)
    if not cues:
        return {"success": False, "error": "No valid caption cues were supplied"}
    dimensions = {"16:9": (1920, 1080), "9:16": (1080, 1920), "1:1": (1080, 1080)}
    width, height = dimensions.get(aspect_ratio, (None, None))
    from univa.mcp_tools.video_gen import remotion_compose_video

    result = remotion_compose_video(
        input_video_path=video_path,
        output_path=output_path or None,
        title=title or None,
        captions=[
            {"text": cue["text"], "startSeconds": cue["start_seconds"], "endSeconds": cue["end_seconds"]}
            for cue in cues
        ],
        width=width,
        height=height,
        fit="contain" if aspect_ratio and width and height else "cover",
        fallback_to_ffmpeg_subtitles=True,
    )
    data = _as_dict(result)
    data["locale_render"] = {
        "source_path": str(Path(video_path).resolve()),
        "caption_count": len(cues),
        "bilingual": bilingual,
        "aspect_ratio": aspect_ratio or "source",
    }
    return data


@mcp.tool()
def validate_localized_media(video_path: str, captions: Any) -> dict:
    """Check localized output existence, timing, overlap, and video bounds."""
    cues = _load_cues(captions)
    checks = []
    path = str(Path(video_path).resolve())
    exists = os.path.isfile(path) and os.path.getsize(path) > 0
    checks.append({"name": "output_exists", "passed": exists})
    if not exists:
        return {"success": False, "locale_qa": {"status": "failed", "checks": checks}, "error": "Localized video is missing or empty"}
    try:
        metadata = probe_media(path)
    except Exception as exc:
        return {"success": False, "locale_qa": {"status": "failed", "checks": checks}, "error": str(exc)}
    overlap_free = all(cues[i]["end_seconds"] <= cues[i + 1]["start_seconds"] for i in range(len(cues) - 1))
    in_bounds = all(0 <= cue["start_seconds"] < cue["end_seconds"] <= metadata["duration_seconds"] + 0.1 for cue in cues)
    max_lines = max((len(cue["text"].splitlines()) for cue in cues), default=0)
    checks.extend([
        {"name": "caption_timing_valid", "passed": in_bounds},
        {"name": "captions_do_not_overlap", "passed": overlap_free},
        {"name": "caption_line_count", "passed": max_lines <= 2, "value": max_lines},
        {"name": "video_probe", "passed": metadata["duration_seconds"] > 0, "metadata": metadata},
    ])
    passed = all(item["passed"] for item in checks)
    return {"success": passed, "locale_qa": {"status": "passed" if passed else "failed", "checks": checks, "caption_count": len(cues)}}


if __name__ == "__main__":
    mcp.run(transport="stdio")
