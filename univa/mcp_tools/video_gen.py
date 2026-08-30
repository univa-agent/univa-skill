import json
import platform
import math
import os
import subprocess
import hashlib
import shutil
import uuid
from pathlib import Path
from typing import Any, Dict, List
from datetime import datetime
from mcp.server.fastmcp import FastMCP

from univa.config.mcp_config import UNIVA_ROOT, get_mcp_section, get_wavespeed_config
from univa.mcp_tools.base import ToolResponse, redact_secrets, setup_logger
from univa.mcp_tools.audio_gen import plan_audio_for_video as plan_audio_tool, generate_audio_assets_from_plan as generate_audio_assets_tool
from univa.utils.audio_timeline import has_audio_stream
from univa.utils.video_process import merge_videos, merge_videos_with_transitions, resolve_merge_transition, storyboard_generate, save_last_frame_decord, supported_merge_transitions
from univa.utils.query_llm import query_openai, refine_gen_prompt, audio_prompt_gen
from univa.utils.image_process import download_image
from univa.utils.text_process import extract_dict
from univa.utils.wavespeed_api import (
    text_to_video_generate as ws_text_to_video,
    image_to_video_generate as ws_image_to_video,
    text_to_image_generate as ws_text_to_image,
    image_to_image_generate as ws_image_to_image,
    audio_gen,
    hailuo_i2v_pro,
)
from univa.utils.volcengine_api import (
    text_to_video_generate as ark_text_to_video,
    image_to_video_generate as ark_image_to_video,
    text_to_image_generate as ark_text_to_image,
    image_to_image_generate as ark_image_to_image,
)

video_gen_config = get_mcp_section("video_gen")
image_gen_config = get_mcp_section("image_gen")
llm_config = get_mcp_section("llm")
# Configure logging
logger = setup_logger(__name__, "logs/mcp_tools", "video_gen.log")
logger.info("Loaded video_gen_config: %s", redact_secrets(video_gen_config))

mcp = FastMCP("Video_Generation_Server")

# Ark Seedance 2.0 rejects 3s duration requests; keep the runtime floor aligned
# with the provider instead of only relying on planning prompts.
MIN_GENERATED_SHOT_DURATION_SECONDS = 4
GENERATION_CONTRACT_SCHEMA_VERSION = 1
GENERATION_CONTRACT_HEADER = "UNIVA_APPROVED_GENERATION_CONTRACT_V1"

_GENERATION_CONTRACT_PLAN_FIELDS = {"generation_contract"}
_GENERATION_CONTRACT_SHOT_FIELDS = {
    "expanded_generation_prompt",
    "generation_contract",
    "generation_contract_schema_version",
    "generation_contract_sha256",
    "generation_prompt_sha256",
    "generation_prompt_source",
}


def _univa_path(relative_path: str) -> str:
    return os.path.abspath(UNIVA_ROOT / relative_path)


def _config_float(key: str, default: float) -> float:
    value = video_gen_config.get(key, default)
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _config_bool(key: str, default: bool) -> bool:
    value = video_gen_config.get(key, default)
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value) if value is not None else default


def _auto_audio_enabled(auto_audio: bool | None = None) -> bool:
    if auto_audio is not None:
        return bool(auto_audio)
    return _config_bool("auto_audio", _config_bool("if_audio", True))


def _ffmpeg_audio_output_path(video_path: str) -> str:
    source = Path(video_path)
    return str(source.with_name(f"{source.stem}_ffmpeg_audio{source.suffix or '.mp4'}"))


def _ffmpeg_audio_profile(prompt: str, include_bgm: bool, include_sfx: bool) -> dict[str, Any]:
    text = (prompt or "").lower()
    action_markers = (
        "car", "truck", "pickup", "engine", "race", "racing", "desert", "sand", "dust",
        "cinematic", "advert", "ad", "wild", "汽车", "皮卡", "越野", "沙漠", "沙尘", "引擎", "广告", "大片",
    )
    nature_markers = ("nature", "forest", "wind", "water", "ocean", "rain", "自然", "森林", "海", "雨", "风")
    if any(marker in text for marker in action_markers):
        profile = {"name": "cinematic_action_bed", "noise_color": "brown", "noise_amplitude": 0.02, "tone_frequency": 82, "tone_volume": 0.045}
    elif any(marker in text for marker in nature_markers):
        profile = {"name": "natural_ambient_bed", "noise_color": "pink", "noise_amplitude": 0.014, "tone_frequency": 174, "tone_volume": 0.018}
    else:
        profile = {"name": "neutral_promo_bed", "noise_color": "pink", "noise_amplitude": 0.012, "tone_frequency": 196, "tone_volume": 0.022}
    profile["include_bgm_tone"] = bool(include_bgm)
    profile["include_sfx_texture"] = bool(include_sfx)
    return profile


def _attach_ffmpeg_generated_audio(
    video_path: str,
    prompt: str,
    *,
    include_voiceover: bool,
    include_bgm: bool,
    include_sfx: bool,
    target_duration_seconds: int | float | None,
) -> tuple[str | None, dict]:
    if not shutil.which("ffmpeg"):
        return video_path, {"audio_error": "ffmpeg is not available for local audio fallback."}

    duration = target_duration_seconds or _probe_video_duration(video_path) or 5
    try:
        duration = max(1.0, float(duration))
    except (TypeError, ValueError):
        duration = 5.0

    profile = _ffmpeg_audio_profile(prompt, include_bgm=include_bgm, include_sfx=include_sfx)
    output_path = _ffmpeg_audio_output_path(video_path)
    fade_out_start = max(0.0, duration - 0.8)
    inputs = [
        "ffmpeg",
        "-y",
        "-i",
        video_path,
        "-f",
        "lavfi",
        "-t",
        f"{duration:.3f}",
        "-i",
        f"anoisesrc=color={profile['noise_color']}:amplitude={profile['noise_amplitude']}:sample_rate=44100",
    ]
    filters = [
        (
            f"[1:a]afade=t=in:st=0:d=0.350,"
            f"afade=t=out:st={fade_out_start:.3f}:d=0.800,"
            "volume=0.500[bed]"
        )
    ]
    mix_labels = ["[bed]"]
    if profile["include_bgm_tone"]:
        inputs.extend([
            "-f",
            "lavfi",
            "-t",
            f"{duration:.3f}",
            "-i",
            f"sine=frequency={profile['tone_frequency']}:sample_rate=44100",
        ])
        filters.append(
            (
                f"[2:a]afade=t=in:st=0:d=0.500,"
                f"afade=t=out:st={fade_out_start:.3f}:d=0.800,"
                f"volume={profile['tone_volume']:.3f}[tone]"
            )
        )
        mix_labels.append("[tone]")

    if len(mix_labels) == 1:
        filters.append("[bed]anull[a]")
    else:
        filters.append(f"{''.join(mix_labels)}amix=inputs={len(mix_labels)}:duration=first[a]")

    cmd = [
        *inputs,
        "-filter_complex",
        ";".join(filters),
        "-map",
        "0:v:0",
        "-map",
        "[a]",
        "-c:v",
        "copy",
        "-c:a",
        "aac",
        "-shortest",
        "-movflags",
        "+faststart",
        output_path,
    ]
    completed = subprocess.run(cmd, capture_output=True, text=True)
    if completed.returncode != 0 or not Path(output_path).exists() or Path(output_path).stat().st_size == 0:
        stderr_tail = "\n".join((completed.stderr or completed.stdout or "").splitlines()[-20:])
        return video_path, {
            "audio_error": f"ffmpeg local audio fallback failed with exit {completed.returncode}: {stderr_tail}",
            "ffmpeg_audio_command": cmd,
        }
    if not has_audio_stream(output_path):
        return video_path, {
            "audio_error": "ffmpeg local audio fallback produced a file without an audio stream.",
            "ffmpeg_audio_output_path": output_path,
            "ffmpeg_audio_command": cmd,
        }
    return output_path, {
        "audio_source": "ffmpeg_synthetic_fallback",
        "audio_output_path": output_path,
        "audio_profile": profile,
        "audio_warning": (
            "Local ffmpeg fallback generated a simple synthetic ambience/BGM bed; semantic SFX or voiceover "
            "requires a dedicated audio generation API."
        ) if include_voiceover else "Local ffmpeg fallback generated a simple synthetic ambience/BGM bed.",
        "ffmpeg_audio_command": cmd,
    }


def _attach_auto_audio(
    video_path: str | None,
    prompt: str,
    auto_audio: bool | None = None,
    include_voiceover: bool | None = None,
    include_bgm: bool | None = None,
    include_sfx: bool | None = None,
    video_plan: dict | None = None,
    target_duration_seconds: int | float | None = None,
) -> tuple[str | None, dict | None]:
    if not video_path or not _auto_audio_enabled(auto_audio):
        return video_path, None
    if not os.path.exists(video_path):
        return video_path, {"audio_error": f"Video path does not exist: {video_path}"}

    if has_audio_stream(video_path):
        return video_path, {
            "audio_source": "video_api_native",
            "audio_output_path": video_path,
            "audio_message": "Using the audio stream returned by the video generation API.",
        }

    use_voiceover = (
        bool(include_voiceover)
        if include_voiceover is not None
        else _config_bool("auto_audio_include_voiceover", False)
    )
    audio_errors: list[str] = []
    try:
        plan_response = plan_audio_tool(
            video_prompt=prompt,
            video_plan=video_plan,
            target_duration_seconds=target_duration_seconds,
            include_voiceover=use_voiceover,
            include_bgm=_config_bool("auto_audio_include_bgm", True) if include_bgm is None else bool(include_bgm),
            include_sfx=_config_bool("auto_audio_include_sfx", True) if include_sfx is None else bool(include_sfx),
        )
        if not getattr(plan_response, "success", False):
            audio_errors.append(getattr(plan_response, "message", None) or "Audio planning failed")
            plan_response = None

        audio_plan = getattr(plan_response, "content", None) if plan_response is not None else None
        if isinstance(audio_plan, dict):
            if not use_voiceover:
                audio_plan["voiceover_segments"] = []
            assets_response = generate_audio_assets_tool(audio_plan=audio_plan, video_path=video_path)
            if getattr(assets_response, "success", False) and getattr(assets_response, "output_path", None):
                return assets_response.output_path, {
                    "audio_source": "dedicated_audio_api",
                    "audio_plan": audio_plan,
                    "audio_assets": (getattr(assets_response, "content", None) or {}).get("assets", []),
                    "audio_timeline_events": (getattr(assets_response, "content", None) or {}).get("timeline_events", []),
                    "audio_output_path": assets_response.output_path,
                }
            audio_errors.append(
                getattr(assets_response, "message", None)
                or getattr(assets_response, "error", None)
                or "Audio asset generation failed"
            )
    except Exception as exc:
        logger.warning("Auto audio generation failed: %s", exc)
        audio_errors.append(str(exc))

    fallback_path, fallback_meta = _attach_ffmpeg_generated_audio(
        video_path,
        prompt,
        include_voiceover=use_voiceover,
        include_bgm=_config_bool("auto_audio_include_bgm", True) if include_bgm is None else bool(include_bgm),
        include_sfx=_config_bool("auto_audio_include_sfx", True) if include_sfx is None else bool(include_sfx),
        target_duration_seconds=target_duration_seconds,
    )
    fallback_meta["audio_fallback_reason"] = "Video API output had no audio stream and dedicated audio API was unavailable or failed."
    if audio_errors:
        fallback_meta["audio_errors"] = audio_errors
    return fallback_path, fallback_meta


def _resolve_duration(duration_seconds: int | float | None = None) -> int | None:
    if duration_seconds is None:
        return None
    try:
        duration = float(duration_seconds)
    except (TypeError, ValueError):
        return None

    min_duration = max(
        MIN_GENERATED_SHOT_DURATION_SECONDS,
        _config_float("min_duration_seconds", MIN_GENERATED_SHOT_DURATION_SECONDS),
    )
    max_duration = max(min_duration, _config_float("max_duration_seconds", 10))
    duration = max(min_duration, min(max_duration, duration))
    return max(1, int(round(duration)))


def _set_shot_duration(shot: dict, duration: int) -> None:
    timing = shot.get("timing") if isinstance(shot.get("timing"), dict) else None
    for key in ("duration_seconds", "duration_sec", "duration"):
        if key in shot:
            shot[key] = duration
            return
        if timing is not None and key in timing:
            timing[key] = duration
            return
    shot["duration_seconds"] = duration


def _normalize_shot_durations(shots: list[dict] | None, default_key: str = "duration_seconds") -> int:
    if not isinstance(shots, list):
        return 0

    total_duration = 0
    cumulative_start = 0
    for shot in shots:
        if not isinstance(shot, dict):
            continue

        duration = _duration_from_shot(shot)
        if duration is None:
            duration = MIN_GENERATED_SHOT_DURATION_SECONDS
            shot[default_key] = duration
        else:
            _set_shot_duration(shot, duration)

        if "start_time" in shot:
            shot["start_time"] = cumulative_start
        if "end_time" in shot:
            shot["end_time"] = cumulative_start + duration

        total_duration += duration
        cumulative_start += duration

    return total_duration




def _as_bool(value) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on", "single_take", "single-take"}
    return bool(value)


def _text_value(value) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, tuple)):
        return ", ".join(_text_value(item) for item in value if _text_value(item))
    if isinstance(value, dict):
        return ", ".join(f"{key}: {_text_value(val)}" for key, val in value.items() if _text_value(val))
    return str(value).strip()


def _stable_json(value) -> str:
    """Serialize generation contracts deterministically for review and hashing."""
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _generation_value_copy(value):
    """Return a JSON-safe deep copy without sharing mutable plan objects."""
    return json.loads(json.dumps(value, ensure_ascii=False, default=str))


def _shot_generation_spec(shot: dict) -> dict:
    return {
        key: _generation_value_copy(value)
        for key, value in shot.items()
        if key not in _GENERATION_CONTRACT_SHOT_FIELDS
    }


def _generation_contract_for_shot(plan: dict, shot: dict, shot_index: int) -> dict:
    shots = [item for item in plan.get("shots", []) if isinstance(item, dict)]
    global_plan = {
        key: _generation_value_copy(value)
        for key, value in plan.items()
        if key not in _GENERATION_CONTRACT_PLAN_FIELDS and key != "shots"
    }
    aspect_ratio = (
        shot.get("aspect_ratio")
        or plan.get("aspect_ratio")
        or video_gen_config.get("default_aspect_ratio", "16:9")
    )
    return {
        "schema_version": GENERATION_CONTRACT_SCHEMA_VERSION,
        "instruction": (
            "Render only current_shot as one coherent generation unit. Apply every approved global, "
            "sequence, style, timing, continuity, transition, and negative constraint below. "
            "Other sequence shots are continuity context and must not be rendered inside this shot."
        ),
        "provider_parameters": {
            "duration_seconds": _duration_from_shot(shot),
            "aspect_ratio": aspect_ratio,
        },
        "global_plan": global_plan,
        "sequence": {
            "shot_count": len(shots),
            "current_shot_index": shot_index,
            "shots": [_shot_generation_spec(item) for item in shots],
        },
        "current_shot": _shot_generation_spec(shot),
    }


def _render_generation_contract_prompt(creative_prompt: str, contract: dict) -> str:
    return (
        f"[{GENERATION_CONTRACT_HEADER}]\n"
        "The following is the complete, user-reviewed generation input. Do not omit, summarize, "
        "reinterpret, or replace any approved specification. If a compact summary conflicts with a "
        "more detailed field, follow the more detailed field.\n\n"
        "PRIMARY_CINEMATIC_PROMPT:\n"
        f"{creative_prompt.strip()}\n\n"
        "FULL_APPROVED_GENERATION_CONTEXT_JSON:\n"
        f"{_stable_json(contract)}\n"
        f"[/{GENERATION_CONTRACT_HEADER}]"
    )


def _freeze_generation_contracts(plan: dict) -> dict:
    """Freeze the complete provider prompt before storyboard review."""
    if not isinstance(plan, dict):
        return plan
    shots = plan.get("shots")
    if not isinstance(shots, list):
        return plan

    for shot in shots:
        if not isinstance(shot, dict):
            continue
        creative_prompt = _text_value(
            shot.get("creative_generation_prompt") or shot.get("expanded_generation_prompt")
        )
        if creative_prompt:
            shot["creative_generation_prompt"] = creative_prompt

    prompt_hashes = []
    for index, shot in enumerate(shots, start=1):
        if not isinstance(shot, dict):
            continue
        creative_prompt = _text_value(shot.get("creative_generation_prompt"))
        if not creative_prompt:
            continue
        contract = _generation_contract_for_shot(plan, shot, index)
        contract_json = _stable_json(contract)
        provider_prompt = _render_generation_contract_prompt(creative_prompt, contract)
        shot["generation_contract_schema_version"] = GENERATION_CONTRACT_SCHEMA_VERSION
        shot["generation_contract"] = contract
        shot["generation_contract_sha256"] = _sha256_text(contract_json)
        shot["expanded_generation_prompt"] = provider_prompt
        shot["generation_prompt_sha256"] = _sha256_text(provider_prompt)
        shot["generation_prompt_source"] = "frozen_complete_generation_contract"
        prompt_hashes.append(
            {
                "shot_id": shot.get("id") or shot.get("shot_id") or f"shot_{index:02d}",
                "generation_prompt_sha256": shot["generation_prompt_sha256"],
                "generation_contract_sha256": shot["generation_contract_sha256"],
            }
        )

    plan["generation_contract"] = {
        "schema_version": GENERATION_CONTRACT_SCHEMA_VERSION,
        "status": "frozen_for_storyboard_review",
        "aspect_ratio": plan.get("aspect_ratio") or video_gen_config.get("default_aspect_ratio", "16:9"),
        "target_duration_seconds": plan.get("target_duration_seconds"),
        "shot_prompts": prompt_hashes,
        "plan_prompt_set_sha256": _sha256_text(_stable_json(prompt_hashes)),
        "handoff_rule": (
            "storyboard_review.shots[*].expanded_generation_prompt must equal the exact provider prompt; "
            "approved execution verifies hashes and never rewrites it"
        ),
    }
    return plan


def _verify_generation_contracts(plan: dict) -> dict:
    """Verify that an approved plan still matches the prompts shown at review."""
    issues = []
    shots = plan.get("shots") if isinstance(plan, dict) else None
    metadata = plan.get("generation_contract") if isinstance(plan, dict) else None
    if not isinstance(metadata, dict) or metadata.get("schema_version") != GENERATION_CONTRACT_SCHEMA_VERSION:
        issues.append(
            {
                "severity": "high",
                "problem": "Plan has no current frozen generation contract; it must be replanned and reviewed.",
            }
        )
    if not isinstance(shots, list) or not shots:
        issues.append({"severity": "high", "problem": "Plan contains no shots."})
        shots = []

    prompt_hashes = []
    for index, shot in enumerate(shots, start=1):
        if not isinstance(shot, dict):
            continue
        shot_id = shot.get("id") or shot.get("shot_id") or f"shot_{index:02d}"
        creative_prompt = _text_value(shot.get("creative_generation_prompt"))
        provider_prompt = _text_value(shot.get("expanded_generation_prompt"))
        stored_contract = shot.get("generation_contract")
        if not creative_prompt or not provider_prompt or not isinstance(stored_contract, dict):
            issues.append({"severity": "high", "item": shot_id, "problem": "Frozen prompt contract is incomplete."})
            continue

        expected_contract = _generation_contract_for_shot(plan, shot, index)
        expected_contract_json = _stable_json(expected_contract)
        expected_prompt = _render_generation_contract_prompt(creative_prompt, expected_contract)
        expected_contract_hash = _sha256_text(expected_contract_json)
        expected_prompt_hash = _sha256_text(expected_prompt)
        if _stable_json(stored_contract) != expected_contract_json:
            issues.append(
                {
                    "severity": "high",
                    "item": shot_id,
                    "problem": "Plan fields changed after the generation contract was frozen.",
                }
            )
        if provider_prompt != expected_prompt:
            issues.append(
                {
                    "severity": "high",
                    "item": shot_id,
                    "problem": "expanded_generation_prompt differs from the reviewed complete provider prompt.",
                }
            )
        if shot.get("generation_contract_sha256") != expected_contract_hash:
            issues.append({"severity": "high", "item": shot_id, "problem": "Generation contract hash mismatch."})
        if shot.get("generation_prompt_sha256") != expected_prompt_hash:
            issues.append({"severity": "high", "item": shot_id, "problem": "Generation prompt hash mismatch."})
        prompt_hashes.append(
            {
                "shot_id": shot_id,
                "generation_prompt_sha256": expected_prompt_hash,
                "generation_contract_sha256": expected_contract_hash,
            }
        )

    expected_set_hash = _sha256_text(_stable_json(prompt_hashes))
    if isinstance(metadata, dict) and metadata.get("plan_prompt_set_sha256") != expected_set_hash:
        issues.append({"severity": "high", "problem": "Plan prompt-set hash mismatch."})
    return {
        "status": "pass" if not issues else "blocked",
        "ready_for_generation": not issues,
        "issue_count": len(issues),
        "issues": issues,
        "plan_prompt_set_sha256": expected_set_hash,
    }


def _shot_scene_key(shot: dict) -> str:
    for key in ("generation_unit_id", "scene_id", "continuity_anchor"):
        value = _text_value(shot.get(key)).lower()
        if value:
            return value
    return ""


def _shot_duration_total(shot: dict) -> int:
    return _duration_from_shot(shot) or MIN_GENERATED_SHOT_DURATION_SECONDS


def _should_merge_continuous_shots(previous: dict, current: dict, max_duration: float) -> bool:
    if _as_bool(previous.get("force_separate")) or _as_bool(current.get("force_separate")):
        return False
    if _shot_duration_total(previous) + _shot_duration_total(current) > max_duration:
        return False

    same_scene = _shot_scene_key(previous) and _shot_scene_key(previous) == _shot_scene_key(current)
    same_take = _as_bool(previous.get("single_take_preferred")) or _as_bool(current.get("single_take_preferred"))
    same_anchor = (
        _text_value(previous.get("continuity_anchor")).lower()
        and _text_value(previous.get("continuity_anchor")).lower() == _text_value(current.get("continuity_anchor")).lower()
    )
    return bool((same_take and same_scene) or (same_take and same_anchor))


def _merge_shot_text(*parts: str) -> str:
    seen = set()
    merged = []
    for part in parts:
        text = _text_value(part)
        if not text:
            continue
        normalized = " ".join(text.lower().split())
        if normalized in seen:
            continue
        seen.add(normalized)
        merged.append(text.rstrip("."))
    return ". Then, ".join(merged) + ("." if merged else "")


def _merge_prompt_components(previous: dict, current: dict) -> dict:
    previous_components = previous.get("prompt_components") if isinstance(previous.get("prompt_components"), dict) else {}
    current_components = current.get("prompt_components") if isinstance(current.get("prompt_components"), dict) else {}
    keys = set(previous_components) | set(current_components)
    return {
        key: _merge_shot_text(previous_components.get(key), current_components.get(key))
        for key in keys
    }


def _merge_two_continuous_shots(previous: dict, current: dict, default_key: str) -> dict:
    merged = dict(previous)
    previous_duration = _shot_duration_total(previous)
    current_duration = _shot_duration_total(current)
    _set_shot_duration(merged, previous_duration + current_duration)
    if default_key not in merged and "duration_seconds" not in merged and "duration" not in merged:
        merged[default_key] = previous_duration + current_duration

    merged["merged_from_shots"] = [
        *previous.get("merged_from_shots", [previous.get("id") or previous.get("shot_id")]),
        *current.get("merged_from_shots", [current.get("id") or current.get("shot_id")]),
    ]
    merged["single_take_preferred"] = True
    merged["generation_unit_id"] = previous.get("generation_unit_id") or previous.get("scene_id") or current.get("generation_unit_id") or current.get("scene_id")
    merged["narrative_role"] = _merge_shot_text(previous.get("narrative_role"), current.get("narrative_role"))
    merged["scene_blueprint"] = _merge_shot_text(previous.get("scene_blueprint"), current.get("scene_blueprint"))
    merged["camera_motion"] = _merge_shot_text(previous.get("camera_motion"), current.get("camera_motion"))
    merged["background"] = _merge_shot_text(previous.get("background"), current.get("background"))
    merged["continuity_anchor"] = _merge_shot_text(previous.get("continuity_anchor"), current.get("continuity_anchor"))
    merged["plot_correspondence"] = _merge_shot_text(previous.get("plot_correspondence"), current.get("plot_correspondence"))
    merged["visual_prompt"] = _merge_shot_text(previous.get("visual_prompt"), current.get("visual_prompt"))
    merged["setting_description"] = _merge_shot_text(previous.get("setting_description"), current.get("setting_description"))
    merged["static_shot_description"] = _merge_shot_text(previous.get("static_shot_description"), current.get("static_shot_description"))
    merged["start_state"] = previous.get("start_state") or current.get("start_state")
    merged["end_state"] = current.get("end_state") or previous.get("end_state")
    merged["duplicate_guard"] = _merge_shot_text(previous.get("duplicate_guard"), current.get("duplicate_guard"))
    merged["negative_constraints"] = _merge_shot_text(previous.get("negative_constraints"), current.get("negative_constraints"))
    merged["duration_reason"] = _merge_shot_text(previous.get("duration_reason"), current.get("duration_reason"))
    merged["transition_context"] = _merge_shot_text(previous.get("transition_context"), current.get("transition_context"))
    merged["expanded_generation_prompt"] = _merge_shot_text(
        previous.get("expanded_generation_prompt"),
        current.get("expanded_generation_prompt"),
    )
    merged["prompt_components"] = _merge_prompt_components(previous, current)
    merged["visual_logic"] = {
        "link_from_previous": _text_value(previous.get("visual_logic")),
        "composition_change": _merge_shot_text(previous.get("duplicate_guard"), current.get("duplicate_guard")),
        "link_to_next": _text_value(current.get("visual_logic")),
    }
    merged["onstage_characters"] = list(dict.fromkeys((previous.get("onstage_characters") or []) + (current.get("onstage_characters") or [])))
    return merged


def _merge_continuous_shots(shots: list[dict] | None, default_key: str) -> list[dict]:
    if not isinstance(shots, list):
        return []

    _, max_duration = _planned_duration_bounds()
    merged_shots: list[dict] = []
    for shot in shots:
        if not isinstance(shot, dict):
            continue
        if merged_shots and _should_merge_continuous_shots(merged_shots[-1], shot, max_duration):
            merged_shots[-1] = _merge_two_continuous_shots(merged_shots[-1], shot, default_key)
        else:
            merged_shots.append(shot)

    for index, shot in enumerate(merged_shots, start=1):
        if isinstance(shot.get("id"), int):
            shot["id"] = index
        elif shot.get("id"):
            shot["id"] = f"shot_{index:02d}"
        else:
            shot["id"] = index
    return merged_shots


def _merge_shots_to_fit_provider_minimum(
    shots: list[dict] | None,
    requested_total_duration: int | float | None,
    default_key: str,
) -> tuple[list[dict], dict | None]:
    if not isinstance(shots, list) or len(shots) <= 1 or requested_total_duration is None:
        return shots or [], None

    try:
        target = int(round(float(requested_total_duration)))
    except (TypeError, ValueError):
        return shots, None

    min_duration, max_duration = _planned_duration_bounds()
    min_duration = int(round(min_duration))
    max_duration = int(round(max_duration))
    if target < min_duration or target >= len(shots) * min_duration:
        return shots, None

    max_shots_for_target = max(1, target // min_duration)
    if max_shots_for_target >= len(shots):
        return shots, None

    merged_shots = [shot for shot in shots if isinstance(shot, dict)]
    before_count = len(merged_shots)
    before_ids = [shot.get("id") or shot.get("shot_id") for shot in merged_shots]
    forced_merges: list[list[str | int | None]] = []

    while len(merged_shots) > max_shots_for_target:
        merge_index = None
        for index in range(len(merged_shots) - 1):
            if _should_merge_continuous_shots(merged_shots[index], merged_shots[index + 1], max_duration):
                merge_index = index
                break
        if merge_index is None:
            for index in range(len(merged_shots) - 1):
                if _as_bool(merged_shots[index].get("force_separate")) or _as_bool(merged_shots[index + 1].get("force_separate")):
                    continue
                if _shot_duration_total(merged_shots[index]) + _shot_duration_total(merged_shots[index + 1]) <= max_duration:
                    merge_index = index
                    break
        if merge_index is None:
            break

        left_id = merged_shots[merge_index].get("id") or merged_shots[merge_index].get("shot_id")
        right_id = merged_shots[merge_index + 1].get("id") or merged_shots[merge_index + 1].get("shot_id")
        forced_merges.append([left_id, right_id])
        merged = _merge_two_continuous_shots(merged_shots[merge_index], merged_shots[merge_index + 1], default_key)
        merged["duration_reason"] = _merge_shot_text(
            merged.get("duration_reason"),
            (
                f"Provider minimum is {min_duration}s per generated clip; the requested {target}s runtime "
                "cannot contain the previous shot count, so adjacent beats were fused into one generation unit."
            ),
        )
        merged_shots[merge_index:merge_index + 2] = [merged]

    if len(merged_shots) == before_count:
        return shots, None

    for index, shot in enumerate(merged_shots, start=1):
        shot["id"] = f"shot_{index:02d}"

    return merged_shots, {
        "status": "merged_due_provider_minimum",
        "provider_minimum_duration_seconds": min_duration,
        "requested_total_duration": target,
        "before_count": before_count,
        "after_count": len(merged_shots),
        "before_ids": before_ids,
        "merged_pairs": forced_merges,
        "principle": (
            "When remaining target time cannot support another provider clip, fold the beat into an adjacent "
            "generation unit if it fits the provider maximum; otherwise the plan must ask the user to accept "
            "a longer video."
        ),
    }


def _duration_priority(shot: dict) -> int:
    text = _text_value(
        [shot.get("narrative_role"), shot.get("scene_blueprint"), shot.get("visual_prompt"), shot.get("end_state")]
    ).lower()
    if any(marker in text for marker in ("climax", "final", "finale", "hero", "result", "reveal", )):
        return 3
    if any(marker in text for marker in ("hook", "opening", "establish", )):
        return 2
    return 1


def _rebalance_shot_durations_to_target(
    shots: list[dict] | None,
    requested_total_duration: int | float | None,
    default_key: str,
) -> dict:
    if not isinstance(shots, list) or not shots or requested_total_duration is None:
        return {"status": "not_applicable"}

    try:
        target = int(round(float(requested_total_duration)))
    except (TypeError, ValueError):
        return {"status": "invalid_target", "requested_total_duration": requested_total_duration}

    min_duration, max_duration = _planned_duration_bounds()
    min_duration = int(round(min_duration))
    max_duration = int(round(max_duration))
    feasible_min = len(shots) * min_duration
    feasible_max = len(shots) * max_duration
    before = []
    durations = []
    for shot in shots:
        duration = _duration_from_shot(shot) or min_duration
        duration = max(min_duration, min(max_duration, int(round(duration))))
        before.append(duration)
        durations.append(duration)

    if target < feasible_min:
        return {
            "status": "expanded_due_provider_minimum",
            "requested_total_duration": target,
            "minimum_possible_duration": feasible_min,
            "before": before,
            "after": before,
        }
    if target > feasible_max:
        return {
            "status": "target_exceeds_provider_per_shot_maximum",
            "requested_total_duration": target,
            "maximum_possible_duration_with_current_shots": feasible_max,
            "before": before,
            "after": before,
        }

    delta = target - sum(durations)
    while delta < 0:
        candidates = [index for index, duration in enumerate(durations) if duration > min_duration]
        if not candidates:
            break
        index = max(candidates, key=lambda item: (durations[item], -_duration_priority(shots[item]), -item))
        durations[index] -= 1
        delta += 1

    while delta > 0:
        candidates = [index for index, duration in enumerate(durations) if duration < max_duration]
        if not candidates:
            break
        index = max(candidates, key=lambda item: (_duration_priority(shots[item]), durations[item], -item))
        durations[index] += 1
        delta -= 1

    for shot, duration in zip(shots, durations):
        _set_shot_duration(shot, duration)
        shot["duration_reason"] = shot.get("duration_reason") or (
            "Duration was dynamically balanced against action complexity, readability, continuity, "
            "provider limits, and the requested total runtime; not a fixed default per-shot length."
        )

    return {
        "status": "balanced_to_requested_total" if sum(durations) == target else "partially_balanced",
        "requested_total_duration": target,
        "before": before,
        "after": durations,
        "before_total": sum(before),
        "after_total": sum(durations),
        "principle": "Detailed shot expansion does not automatically increase total duration; durations are rebalanced after expansion.",
    }


def _normalize_video_plan_durations(plan: dict, requested_total_duration: int | float | None = None) -> dict:
    shots = plan.get("shots") if isinstance(plan, dict) else None
    if isinstance(shots, list):
        shots = _merge_continuous_shots(shots, default_key="duration_seconds")
        shots, provider_minimum_merge_audit = _merge_shots_to_fit_provider_minimum(
            shots, requested_total_duration, default_key="duration_seconds"
        )
        plan["shots"] = shots
        if provider_minimum_merge_audit:
            plan["provider_minimum_merge_audit"] = provider_minimum_merge_audit

    plan["duration_adjustment_audit"] = _rebalance_shot_durations_to_target(
        shots, requested_total_duration, default_key="duration_seconds"
    )
    total_duration = _normalize_shot_durations(shots, default_key="duration_seconds")
    _normalize_expanded_shot_prompts(plan)
    if total_duration:
        plan["target_duration_seconds"] = total_duration

        shot_duration_by_id = {}
        for shot in shots or []:
            if isinstance(shot, dict):
                shot_id = str(shot.get("id") or shot.get("shot_id") or "")
                duration = _duration_from_shot(shot)
                if shot_id and duration is not None:
                    shot_duration_by_id[shot_id] = duration

        execution_plan = plan.get("execution_plan")
        if isinstance(execution_plan, list):
            rebuilt_execution_plan = []
            for index, shot in enumerate(shots or [], start=1):
                if not isinstance(shot, dict):
                    continue
                shot_id = str(shot.get("id") or shot.get("shot_id") or f"shot_{index:02d}")
                rebuilt_execution_plan.append({
                    "step": index,
                    "tool": shot.get("generation_tool") or "text2video_gen",
                    "shot_id": shot_id,
                    "duration_seconds": _duration_from_shot(shot),
                    "prompt_field": "shots[*].expanded_generation_prompt",
                    "notes": (
                        "Generate this complete generation unit in one provider call; "
                        "use the approved expanded_generation_prompt as the exact tool prompt; "
                        "do not replace it with keywords, visual_prompt, or the original user prompt."
                    ),
                })
            plan["execution_plan"] = rebuilt_execution_plan

    return _freeze_generation_contracts(plan)


def _style_anchor_text(style_anchors: dict | None) -> str:
    if not isinstance(style_anchors, dict):
        return ""
    parts = [
        style_anchors.get("visual_style"),
        style_anchors.get("lighting"),
        style_anchors.get("color_palette"),
        style_anchors.get("camera_language"),
        style_anchors.get("atmosphere"),
        _text_value(style_anchors.get("shared_subject_anchors")),
    ]
    return ". ".join(_text_value(part).rstrip(".") for part in parts if _text_value(part))


def _transition_context(plan: dict, shot_id: str) -> str:
    transitions = plan.get("transitions")
    if not isinstance(transitions, list):
        return ""
    relevant = []
    for transition in transitions:
        if not isinstance(transition, dict):
            continue
        if str(transition.get("from_shot")) == shot_id:
            relevant.append(
                "Transition out: "
                + _merge_shot_text(
                    transition.get("transition_type"),
                    transition.get("bridge_prompt"),
                    _text_value(transition.get("continuity_requirements")),
                )
            )
        if str(transition.get("to_shot")) == shot_id:
            relevant.append(
                "Transition in: "
                + _merge_shot_text(
                    transition.get("transition_type"),
                    transition.get("bridge_prompt"),
                    _text_value(transition.get("continuity_requirements")),
                )
            )
    return " ".join(part for part in relevant if part.strip())


def _default_negative_constraints() -> str:
    return (
        "Avoid exact official logo replication, avoid recognizable real-person facial likeness, "
        "avoid contradictory time-of-day or lighting, avoid repeating the previous shot's same composition and action, "
        "avoid text clutter, malformed lettering, watermarks, and low-detail backgrounds."
    )


def _prompt_components_from_shot(shot: dict, style_anchors: dict | None, transition_context: str) -> dict:
    return {
        "subject": _merge_shot_text(
            shot.get("subject"),
            shot.get("narrative_role"),
            shot.get("onstage_characters"),
            shot.get("shared_subject_anchor"),
        ),
        "subject_motion": _merge_shot_text(
            shot.get("motion"),
            shot.get("action"),
            shot.get("start_state"),
            shot.get("end_state"),
        ),
        "scene": _merge_shot_text(
            shot.get("scene_blueprint"),
            shot.get("background"),
            shot.get("setting_description"),
        ),
        "spatial": _merge_shot_text(
            shot.get("spatial_composition"),
            _shot_perspective_text(shot),
            "foreground, midground, and background layers should be visually readable",
        ),
        "camera": _merge_shot_text(
            shot.get("camera_motion"),
            shot.get("camera_movement"),
            shot.get("lens"),
            "controlled cinematic focus and depth of field",
        ),
        "atmosphere": _merge_shot_text(
            shot.get("atmosphere"),
            shot.get("mood"),
            style_anchors.get("atmosphere") if isinstance(style_anchors, dict) else None,
        ),
        "stylization": _merge_shot_text(
            shot.get("stylization"),
            shot.get("style_keywords"),
            _style_anchor_text(style_anchors),
        ),
        "transition_context": transition_context,
        "negative_constraints": _text_value(shot.get("negative_constraints")) or _default_negative_constraints(),
    }


def _expanded_prompt_from_components(shot: dict, components: dict) -> str:
    parts = [
        f"Shot objective: {_text_value(shot.get('narrative_role'))}" if shot.get("narrative_role") else None,
        f"Subject: {_text_value(components.get('subject'))}",
        f"Subject motion and timing: {_text_value(components.get('subject_motion'))}",
        f"Scene and environment: {_text_value(components.get('scene'))}",
        f"Spatial composition: {_text_value(components.get('spatial'))}",
        f"Camera language: {_text_value(components.get('camera'))}",
        f"Atmosphere: {_text_value(components.get('atmosphere'))}",
        f"Stylization and shared anchors: {_text_value(components.get('stylization'))}",
        f"Continuity anchor: {_text_value(shot.get('continuity_anchor'))}" if shot.get("continuity_anchor") else None,
        f"Visual logic to neighboring shots: {_text_value(shot.get('visual_logic'))}" if shot.get("visual_logic") else None,
        f"Start state: {_text_value(shot.get('start_state'))}" if shot.get("start_state") else None,
        f"End state: {_text_value(shot.get('end_state'))}" if shot.get("end_state") else None,
        f"Transition context: {_text_value(components.get('transition_context'))}" if components.get("transition_context") else None,
        f"Duplicate guard: {_text_value(shot.get('duplicate_guard'))}" if shot.get("duplicate_guard") else None,
        f"Negative constraints: {_text_value(components.get('negative_constraints'))}",
    ]
    prompt = ". ".join(_text_value(part).rstrip(".") for part in parts if _text_value(part))
    words = prompt.split()
    if len(words) > 520:
        prompt = " ".join(words[:520]).rstrip(" ,.;") + "."
    return prompt


def _normalize_expanded_shot_prompts(plan: dict) -> None:
    if not isinstance(plan, dict):
        return
    shots = plan.get("shots")
    if not isinstance(shots, list):
        return
    style_anchors = plan.get("style_anchors") if isinstance(plan.get("style_anchors"), dict) else {}
    for index, shot in enumerate(shots, start=1):
        if not isinstance(shot, dict):
            continue
        shot_id = str(shot.get("id") or shot.get("shot_id") or f"shot_{index:02d}")
        transition_text = _transition_context(plan, shot_id)
        existing_components = shot.get("prompt_components") if isinstance(shot.get("prompt_components"), dict) else {}
        generated_components = _prompt_components_from_shot(shot, style_anchors, transition_text)
        prompt_components = {
            key: existing_components.get(key) or value
            for key, value in generated_components.items()
        }
        shot["prompt_components"] = prompt_components
        shot["transition_context"] = shot.get("transition_context") or transition_text
        if not isinstance(shot.get("visual_logic"), dict):
            shot["visual_logic"] = {
                "link_from_previous": "use transition_context and continuity_anchor to inherit visual state from the previous shot" if index > 1 else "opening visual premise",
                "composition_change": _text_value(shot.get("duplicate_guard")) or "change shot size, angle, subject focus, or action result from adjacent shots",
                "link_to_next": "handoff through transition_out, camera direction, object motion, or color/lighting continuity",
            }
        shot["negative_constraints"] = (
            _text_value(shot.get("negative_constraints"))
            or _text_value(prompt_components.get("negative_constraints"))
            or _default_negative_constraints()
        )
        shot["expanded_generation_prompt"] = (
            _text_value(shot.get("expanded_generation_prompt"))
            or _expanded_prompt_from_components(shot, prompt_components)
        )
        shot["generation_prompt_source"] = "expanded_from_plan_video_shots"


def _normalize_storyboard_durations(storyboard: dict) -> dict:
    shots = storyboard.get("shots") if isinstance(storyboard, dict) else None
    if isinstance(shots, list):
        shots = _merge_continuous_shots(shots, default_key="duration")
        storyboard["shots"] = shots
    _normalize_shot_durations(shots, default_key="duration")
    return storyboard


def _shot_perspective_text(shot: dict) -> str:
    perspective = shot.get("shot_perspective_design") if isinstance(shot.get("shot_perspective_design"), dict) else {}
    distance = perspective.get("distance") or shot.get("shot_type") or "medium shot"
    angle = perspective.get("angle") or "eye-level"
    lens = perspective.get("lens") or "35mm lens"
    motion = shot.get("camera_motion") or shot.get("camera_movement") or "smooth controlled camera motion"
    return f"{distance}, {angle}, {lens}, {motion}"


def _storyboard_shot_prompt(shot: dict, style: str | None = None) -> str:
    parts = [
        style,
        shot.get("scene_blueprint"),
        shot.get("setting_description"),
        shot.get("visual_prompt"),
        shot.get("plot_correspondence"),
        shot.get("static_shot_description"),
        f"Camera and composition: {_shot_perspective_text(shot)}",
        f"Continuity anchor: {_text_value(shot.get('continuity_anchor'))}" if shot.get("continuity_anchor") else None,
        f"Visual logic to neighboring shots: {_text_value(shot.get('visual_logic'))}" if shot.get("visual_logic") else None,
        f"Start state: {_text_value(shot.get('start_state'))}" if shot.get("start_state") else None,
        f"End state: {_text_value(shot.get('end_state'))}" if shot.get("end_state") else None,
        f"Duplicate guard: {_text_value(shot.get('duplicate_guard'))}" if shot.get("duplicate_guard") else None,
    ]
    return ". ".join(_text_value(part).rstrip(".") for part in parts if _text_value(part))


def _probe_video_duration(video_path: str | None) -> float | None:
    if not video_path or not os.path.exists(video_path):
        return None
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            video_path,
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return None
    try:
        return float(result.stdout.strip())
    except (TypeError, ValueError):
        return None




def _probe_video_dimensions(video_path: str | None) -> tuple[int, int] | None:
    if not video_path or not os.path.exists(video_path):
        return None
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=width,height",
            "-of",
            "csv=s=x:p=0",
            video_path,
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return None
    try:
        width, height = result.stdout.strip().split("x", 1)
        return int(width), int(height)
    except (TypeError, ValueError):
        return None


def _remotion_config() -> dict:
    value = video_gen_config.get("remotion") or {}
    return value if isinstance(value, dict) else {}


def _remotion_enabled(requested: bool | None = None) -> bool:
    if requested is not None:
        return bool(requested)
    value = _remotion_config().get("enabled", False)
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def _remotion_package_root() -> Path:
    configured = _remotion_config().get("package_path") or "packages/remotion-compose"
    path = Path(str(configured))
    if path.is_absolute():
        return path

    candidates = [UNIVA_ROOT / path, UNIVA_ROOT.parent / path]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[-1]


def _remotion_binary() -> str | None:
    return shutil.which("bunx") or shutil.which("npx")


def _remotion_local_binary(root: Path) -> Path | None:
    candidates = [
        root / "node_modules" / ".bin" / "remotion",
        root.parent.parent / "node_modules" / ".bin" / "remotion",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def _remotion_command_prefix(root: Path) -> list[str] | None:
    local = _remotion_local_binary(root)
    if local is not None:
        return [str(local)]
    runner = _remotion_binary()
    if runner:
        return [runner, "remotion"]
    return None


def _remotion_browser_executable(requested: str | None = None) -> str | None:
    candidates = [
        requested,
        _remotion_config().get("browser_executable_path"),
        os.environ.get("REMOTION_BROWSER_EXECUTABLE"),
        os.environ.get("PUPPETEER_EXECUTABLE_PATH"),
        shutil.which("google-chrome"),
        shutil.which("google-chrome-stable"),
        shutil.which("chromium"),
        shutil.which("chromium-browser"),
    ]
    for candidate in candidates:
        if not candidate:
            continue
        path = Path(str(candidate))
        if path.exists() and os.access(path, os.X_OK):
            return str(path)
        if os.path.isabs(str(candidate)):
            continue
        resolved = shutil.which(str(candidate))
        if resolved:
            return resolved
    return None


def _host_libc_version_tuple() -> tuple[str, tuple[int, ...]]:
    name, version = platform.libc_ver()
    parsed: list[int] = []
    for chunk in str(version or "").split("."):
        if not chunk.isdigit():
            break
        parsed.append(int(chunk))
    return name or "", tuple(parsed)


def _remotion_binaries_directory(root: Path, requested: str | None = None) -> str | None:
    configured = requested or _remotion_config().get("binaries_directory")
    if configured:
        path = Path(str(configured))
        if not path.is_absolute():
            path = root.parent.parent / path
        if (path / "remotion").exists() or (path / "remotion.exe").exists():
            return str(path.resolve())

    host_libc_name, host_libc_version = _host_libc_version_tuple()
    prefer_musl = host_libc_name == "glibc" and host_libc_version and host_libc_version < (2, 34)
    ordered_candidates = [
        root.parent.parent / "node_modules" / ".bun" / "node_modules" / "@remotion" / "compositor-linux-x64-musl",
        root.parent.parent / "node_modules" / ".bun" / "node_modules" / "@remotion" / "compositor-linux-x64-gnu",
    ] if prefer_musl else [
        root.parent.parent / "node_modules" / ".bun" / "node_modules" / "@remotion" / "compositor-linux-x64-gnu",
        root.parent.parent / "node_modules" / ".bun" / "node_modules" / "@remotion" / "compositor-linux-x64-musl",
    ]
    for candidate in ordered_candidates:
        if (candidate / "remotion").exists():
            return str(candidate.resolve())
    return None


def _remotion_subprocess_env(binaries_directory: str | None = None) -> dict[str, str] | None:
    if not binaries_directory or os.name == "nt":
        return None
    env = os.environ.copy()
    current = env.get("LD_LIBRARY_PATH")
    paths = [binaries_directory]
    if current:
        paths.append(current)
    env["LD_LIBRARY_PATH"] = ":".join(paths)
    return env


def _remotion_fallback_enabled(requested: bool | None = None) -> bool:
    if requested is not None:
        return bool(requested)
    value = _remotion_config().get("fallback_to_ffmpeg_subtitles", True)
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def _remotion_failure_hint(stderr_tail: str) -> str:
    hints: list[str] = []
    if "storage.googleapis.com" in stderr_tail or "EAI_AGAIN" in stderr_tail:
        hints.append(
            "Install Chrome/Chromium locally or set video_gen.remotion.browser_executable_path to avoid runtime browser download."
        )
    if "GLIBC_2.35" in stderr_tail or "GLIBC_2.34" in stderr_tail or "GLIBC_2.33" in stderr_tail:
        hints.append(
            "The installed Remotion compositor is incompatible with this Linux glibc; use a compatible binaries_directory, upgrade the render host, or allow FFmpeg subtitle fallback."
        )
    if "libc.musl-x86_64.so.1" in stderr_tail:
        hints.append("The musl compositor path is missing a complete musl runtime.")
    if "zlibCompileFlags" in stderr_tail or "deflateInit_" in stderr_tail or "inflateInit_" in stderr_tail:
        hints.append(
            "The selected musl compositor cannot resolve zlib symbols in this environment; FFmpeg subtitle fallback is the reliable local path."
        )
    if "libstdc++.so.6" in stderr_tail or "libz.so.1" in stderr_tail:
        hints.append("The selected compositor cannot resolve its C++/zlib runtime libraries.")
    return (" " + " ".join(hints)) if hints else ""


def _ass_time(seconds: float) -> str:
    seconds = max(0.0, float(seconds))
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    whole_seconds = int(seconds % 60)
    centiseconds = int(round((seconds - int(seconds)) * 100))
    if centiseconds >= 100:
        whole_seconds += 1
        centiseconds = 0
    return f"{hours}:{minutes:02d}:{whole_seconds:02d}.{centiseconds:02d}"


def _ass_escape(value: str) -> str:
    return (
        str(value)
        .replace("\\", "\\\\")
        .replace("{", "\\{")
        .replace("}", "\\}")
        .replace("\r\n", "\\N")
        .replace("\n", "\\N")
    )


def _write_ass_caption_file(captions: list[dict], path: Path, width: int, height: int) -> None:
    font_size = max(28, min(52, round(height * 0.06)))
    margin_v = max(36, round(height * 0.075))
    lines = [
        "[Script Info]",
        "ScriptType: v4.00+",
        f"PlayResX: {width}",
        f"PlayResY: {height}",
        "ScaledBorderAndShadow: yes",
        "",
        "[V4+ Styles]",
        "Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding",
        f"Style: Default,Arial,{font_size},&H00FFFFFF,&H000000FF,&H00000000,&H99000000,1,0,0,0,100,100,0,0,1,3,1,2,48,48,{margin_v},1",
        "",
        "[Events]",
        "Format: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text",
    ]
    for caption in captions:
        lines.append(
            "Dialogue: 0,"
            f"{_ass_time(caption['startSeconds'])},"
            f"{_ass_time(caption['endSeconds'])},"
            f"Default,,0,0,0,,{_ass_escape(caption['text'])}"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _ffmpeg_ass_filter_path(path: Path) -> str:
    return str(path).replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")


def _ffmpeg_burn_subtitles_fallback(
    input_video_path: str,
    output_path: str,
    *,
    captions: list | None,
    width: int,
    height: int,
) -> ToolResponse:
    normalized = _normalize_remotion_captions(captions)
    if not normalized:
        return ToolResponse(success=False, error="FFmpeg subtitle fallback requires at least one valid caption cue.")
    ass_path = Path(output_path).with_suffix(".captions.ass")
    _write_ass_caption_file(normalized, ass_path, width, height)
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        input_video_path,
        "-vf",
        f"ass='{_ffmpeg_ass_filter_path(ass_path)}'",
        "-c:a",
        "copy",
        "-movflags",
        "+faststart",
        output_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0 or not Path(output_path).exists() or Path(output_path).stat().st_size == 0:
        stderr_tail = "\n".join((result.stderr or result.stdout or "").splitlines()[-20:])
        return ToolResponse(
            success=False,
            error=f"FFmpeg subtitle fallback failed with exit {result.returncode}: {stderr_tail}",
            content={"command": cmd, "ass_path": str(ass_path)},
        )
    return ToolResponse(
        success=True,
        output_path=str(Path(output_path).resolve()),
        message="FFmpeg subtitle fallback completed successfully.",
        content={
            "method": "ffmpeg_ass_subtitle_fallback",
            "input_video_path": str(Path(input_video_path).resolve()),
            "ass_path": str(ass_path),
            "command": cmd,
            "caption_count": len(normalized),
            "width": width,
            "height": height,
        },
    )


def _remotion_install_error(root: Path) -> str | None:
    if not root.exists() or not (root / "package.json").exists():
        return f"Remotion compose package not found: {root}"
    if not (root / "node_modules").exists() and not (root.parent.parent / "node_modules").exists():
        return f"Remotion dependencies are not installed. Run `bun install` from {UNIVA_ROOT.parent}."
    if not _remotion_command_prefix(root):
        return "No local Remotion binary, bunx, or npx is available to run Remotion."
    return None


def _caption_seconds(item: dict[str, Any]) -> tuple[float | None, float | None]:
    start = item.get("startSeconds", item.get("start_seconds", item.get("start")))
    end = item.get("endSeconds", item.get("end_seconds", item.get("end")))
    if start is None and item.get("startMs") is not None:
        start = float(item["startMs"]) / 1000
    if end is None and item.get("endMs") is not None:
        end = float(item["endMs"]) / 1000
    try:
        return float(start), float(end)
    except (TypeError, ValueError):
        return None, None


def _normalize_remotion_captions(captions: list | None) -> list[dict]:
    if not isinstance(captions, list):
        return []
    normalized: list[dict] = []
    for item in captions:
        if not isinstance(item, dict):
            continue
        words = item.get("words")
        if isinstance(words, list):
            normalized.extend(_normalize_remotion_captions(words))
            continue

        text = item.get("text") or item.get("word") or item.get("caption")
        if not text:
            continue
        start, end = _caption_seconds(item)
        if start is None:
            continue
        if end is None or end <= start:
            end = start + 1.6
        normalized.append(
            {
                "text": str(text).strip(),
                "startSeconds": max(0, round(start, 3)),
                "endSeconds": max(0.1, round(end, 3)),
            }
        )
    return sorted(normalized, key=lambda cue: cue["startSeconds"])


def _overlay_seconds(item: dict[str, Any]) -> tuple[float, float]:
    start = item.get("startSeconds", item.get("start_seconds", item.get("in_seconds", 0)))
    end = item.get("endSeconds", item.get("end_seconds", item.get("out_seconds")))
    try:
        start_value = max(0.0, float(start))
    except (TypeError, ValueError):
        start_value = 0.0
    try:
        end_value = float(end)
    except (TypeError, ValueError):
        end_value = start_value + 3.0
    if end_value <= start_value:
        end_value = start_value + 3.0
    return round(start_value, 3), round(end_value, 3)


def _normalize_remotion_overlays(overlays: list | None) -> list[dict]:
    if not isinstance(overlays, list):
        return []
    allowed_types = {"title_card", "lower_third", "callout", "badge", "cta", "stat"}
    allowed_positions = {"top_left", "top_right", "lower_left", "lower_right", "center", "bottom_center"}
    normalized: list[dict] = []
    for index, item in enumerate(overlays, start=1):
        if not isinstance(item, dict):
            continue
        overlay_type = str(item.get("type") or "lower_third").strip()
        if overlay_type not in allowed_types:
            overlay_type = "lower_third"
        text = item.get("text") or item.get("title") or item.get("label")
        if not text:
            continue
        start, end = _overlay_seconds(item)
        position = str(item.get("position") or "lower_left").strip()
        if position not in allowed_positions:
            position = "lower_left"
        normalized.append(
            {
                "id": str(item.get("id") or f"overlay_{index:02d}"),
                "type": overlay_type,
                "text": str(text).strip(),
                "startSeconds": start,
                "endSeconds": end,
                "position": position,
                "eyebrow": item.get("eyebrow"),
                "value": item.get("value") or item.get("stat"),
                "accentColor": item.get("accentColor") or item.get("accent_color"),
            }
        )
    return normalized


def _copy_optional_remotion_asset(value: str | None, job_dir: Path, public_prefix: str) -> str | None:
    if not value:
        return None
    path = Path(value)
    if not path.exists():
        return value
    target = job_dir / path.name
    shutil.copy2(path, target)
    return f"{public_prefix}/{path.name}"


def _remotion_render(
    input_video_path: str,
    output_path: str,
    *,
    title: str | None = None,
    subtitle: str | None = None,
    captions: list | None = None,
    overlays: list | None = None,
    brand: dict | None = None,
    theme: dict | None = None,
    width: int | None = None,
    height: int | None = None,
    fps: int | None = None,
    show_progress: bool = True,
    fit: str = "cover",
    browser_executable_path: str | None = None,
    remotion_binaries_directory: str | None = None,
    remotion_timeout_ms: int | None = None,
    fallback_to_ffmpeg_subtitles: bool | None = None,
) -> ToolResponse:
    source = Path(input_video_path)
    if not source.exists():
        return ToolResponse(success=False, error=f"Input video not found: {input_video_path}")

    root = _remotion_package_root()
    install_error = _remotion_install_error(root)
    if install_error:
        return ToolResponse(success=False, error=install_error)

    duration_seconds = _probe_video_duration(str(source))
    if not duration_seconds:
        return ToolResponse(success=False, error=f"Could not probe input video duration: {input_video_path}")

    dimensions = _probe_video_dimensions(str(source)) or (1920, 1080)
    render_width = int(width or dimensions[0])
    render_height = int(height or dimensions[1])
    render_fps = int(fps or _remotion_config().get("default_fps") or 30)
    duration_frames = max(1, math.ceil(duration_seconds * render_fps))

    job_id = f"{datetime.now().strftime('%Y%m%d%H%M%S')}_{uuid.uuid4().hex[:8]}"
    public_prefix = f"jobs/{job_id}"
    job_dir = root / "public" / public_prefix
    job_dir.mkdir(parents=True, exist_ok=True)

    media_target = job_dir / source.name
    shutil.copy2(source, media_target)

    resolved_brand = dict(brand or {}) if isinstance(brand, dict) else {}
    logo_src = resolved_brand.get("logoSrc") or resolved_brand.get("logo_path")
    copied_logo = _copy_optional_remotion_asset(logo_src, job_dir, public_prefix)
    if copied_logo:
        resolved_brand["logoSrc"] = copied_logo

    props = {
        "videoSrc": f"{public_prefix}/{source.name}",
        "title": title,
        "subtitle": subtitle,
        "durationSeconds": round(duration_seconds, 3),
        "captions": _normalize_remotion_captions(captions),
        "overlays": _normalize_remotion_overlays(overlays),
        "brand": resolved_brand,
        "theme": {
            **(_remotion_config().get("theme") or {}),
            **(theme if isinstance(theme, dict) else {}),
        },
        "showProgress": bool(show_progress),
        "fit": fit if fit in {"cover", "contain"} else "cover",
    }
    props_path = job_dir / "props.json"
    props_path.write_text(json.dumps(props, ensure_ascii=False, indent=2), encoding="utf-8")

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    timeout_seconds = 600
    timeout_flag: list[str] = []
    if remotion_timeout_ms is not None:
        try:
            timeout_ms = max(1000, int(remotion_timeout_ms))
            timeout_flag = [f"--timeout={timeout_ms}"]
            timeout_seconds = max(timeout_seconds, int(timeout_ms / 1000) + 60)
        except (TypeError, ValueError):
            pass

    command_prefix = _remotion_command_prefix(root)
    if not command_prefix:
        return ToolResponse(success=False, error="No Remotion command is available.")
    browser_executable = _remotion_browser_executable(browser_executable_path)
    browser_flag = [f"--browser-executable={browser_executable}"] if browser_executable else []
    binaries_directory = _remotion_binaries_directory(root, remotion_binaries_directory)
    binaries_flag = [f"--binaries-directory={binaries_directory}"] if binaries_directory else []
    cmd = [
        *command_prefix,
        "render",
        "src/index.tsx",
        "UniVACompose",
        str(Path(output_path).resolve()),
        f"--props={props_path.relative_to(root)}",
        f"--width={render_width}",
        f"--height={render_height}",
        f"--fps={render_fps}",
        f"--duration={duration_frames}",
        "--codec=h264",
        "--crf=18",
        *browser_flag,
        *binaries_flag,
        *timeout_flag,
    ]
    try:
        result = subprocess.run(
            cmd,
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            env=_remotion_subprocess_env(binaries_directory),
        )
    except subprocess.TimeoutExpired as exc:
        return ToolResponse(
            success=False,
            error=f"Remotion render timed out after {exc.timeout}s. Raise remotion_timeout_ms or simplify overlays.",
            content={"command": cmd, "props_path": str(props_path)},
        )

    if result.returncode != 0:
        stderr_tail = "\n".join((result.stderr or result.stdout or "").splitlines()[-20:])
        hint = _remotion_failure_hint(stderr_tail)
        remotion_error = f"Remotion render failed with exit {result.returncode}: {stderr_tail}{hint}"
        fallback_result = None
        if _remotion_fallback_enabled(fallback_to_ffmpeg_subtitles) and props["captions"]:
            fallback_result = _ffmpeg_burn_subtitles_fallback(
                str(source),
                str(Path(output_path).resolve()),
                captions=props["captions"],
                width=render_width,
                height=render_height,
            )
        if fallback_result and fallback_result.success:
            fallback_content = dict(fallback_result.content or {})
            fallback_content.update(
                {
                    "remotion_attempted": True,
                    "remotion_error": remotion_error,
                    "remotion_command": cmd,
                    "props_path": str(props_path),
                    "browser_executable_path": browser_executable,
                    "binaries_directory": binaries_directory,
                }
            )
            return ToolResponse(
                success=True,
                output_path=fallback_result.output_path,
                message="Remotion render failed; FFmpeg subtitle fallback produced the packaged video.",
                content=fallback_content,
            )
        return ToolResponse(
            success=False,
            error=remotion_error,
            content={
                "command": cmd,
                "props_path": str(props_path),
                "browser_executable_path": browser_executable,
                "binaries_directory": binaries_directory,
                "fallback_attempt": getattr(fallback_result, "content", None),
                "fallback_error": getattr(fallback_result, "error", None),
            },
        )
    if not Path(output_path).exists() or Path(output_path).stat().st_size == 0:
        return ToolResponse(
            success=False,
            error="Remotion render completed but produced no output file.",
            content={"command": cmd, "props_path": str(props_path)},
        )

    return ToolResponse(
        success=True,
        output_path=str(Path(output_path).resolve()),
        message="Remotion compose completed successfully.",
        content={
            "method": "remotion",
            "input_video_path": str(source.resolve()),
            "props_path": str(props_path),
            "duration_seconds": round(duration_seconds, 3),
            "duration_frames": duration_frames,
            "fps": render_fps,
            "width": render_width,
            "height": render_height,
            "caption_count": len(props["captions"]),
            "overlay_count": len(props["overlays"]),
            "browser_executable_path": browser_executable,
            "binaries_directory": binaries_directory,
        },
    )

def _duration_from_shot(shot: dict | None) -> int | None:
    shot = shot or {}
    timing = shot.get("timing") if isinstance(shot.get("timing"), dict) else {}
    for key in ("duration_seconds", "duration_sec", "duration"):
        if shot.get(key) is not None:
            return _resolve_duration(shot.get(key))
        if timing.get(key) is not None:
            return _resolve_duration(timing.get(key))
    return None


def _merge_settings(transition: str | None = None, transition_duration_seconds: float | None = None) -> tuple[str, float, str]:
    merge_cfg = video_gen_config.get("merge") or {}
    resolved_transition = transition or merge_cfg.get("transition") or "hard_cut"
    try:
        resolved_duration = float(
            transition_duration_seconds
            if transition_duration_seconds is not None
            else merge_cfg.get("transition_duration_seconds", 0.4)
        )
    except (TypeError, ValueError):
        resolved_duration = 0.4
    output_size = str(merge_cfg.get("output_size") or "1280x720")
    return resolved_transition, resolved_duration, output_size


def _transition_name_from_plan_item(item: object) -> str:
    if isinstance(item, str):
        return item
    if not isinstance(item, dict):
        return "crossfade"
    explicit = item.get("merge_transition") or item.get("transition") or item.get("transition_name")
    if explicit:
        return str(explicit)
    transition_type = str(item.get("transition_type") or item.get("type") or "").lower()
    mapping = {
        "hard_cut": "hard_cut",
        "match_cut": "hard_cut",
        "cut": "hard_cut",
        "crossfade": "crossfade",
        "dissolve": "crossfade",
        "fade": "crossfade",
        "smooth": "crossfade",
        "seamless": "crossfade",
        "morph": "crossfade",
        "bridge_clip": "crossfade",
        "whip_pan": "smoothleft",
        "object_wipe": "wipeleft",
        "wipe": "wipeleft",
        "fadeblack": "fadeblack",
        "fadewhite": "fadewhite",
    }
    return mapping.get(transition_type, transition_type or "crossfade")


def _transitions_from_plan(transition_plan: list | None) -> list[str] | None:
    if not isinstance(transition_plan, list) or not transition_plan:
        return None
    return [_transition_name_from_plan_item(item) for item in transition_plan]


def _merge_generated_videos(
    video_paths: list[str],
    output_file: str,
    transition: str | list[str] | None = None,
    transition_duration_seconds: float | None = None,
    transition_plan: list | None = None,
) -> str | None:
    planned_transitions = _transitions_from_plan(transition_plan)
    transition_input = transition if transition is not None else planned_transitions
    resolved_transition, resolved_duration, output_size = _merge_settings(transition if isinstance(transition, str) else None, transition_duration_seconds)
    executable_transition = resolve_merge_transition(resolved_transition if transition_input is None or isinstance(transition_input, str) else transition_input[0])
    all_hard_cuts = (
        all(resolve_merge_transition(item).lower() in {"hard_cut", "cut", "none", "off"} for item in transition_input)
        if isinstance(transition_input, list)
        else executable_transition.lower() in {"hard_cut", "cut", "none", "off"}
    )
    if all_hard_cuts or resolved_duration <= 0:
        return merge_videos(video_paths, output_file=output_file)
    return merge_videos_with_transitions(
        video_paths,
        output_file=output_file,
        transition=transition_input or resolved_transition,
        transition_duration=resolved_duration,
        output_size=output_size,
        preserve_audio=True,
    )


def _get_video_provider():
    """Return (provider_name, api_key, t2v_model, i2v_model, base_url, provider_config)."""
    provider = video_gen_config.get("provider", "wavespeed")

    if provider == "volcengine_ark":
        ark_cfg = video_gen_config.get("volcengine_ark", {})
        return (
            provider,
            ark_cfg.get("api_key", ""),
            ark_cfg.get("text_to_video_model"),
            ark_cfg.get("image_to_video_model"),
            ark_cfg.get("base_url"),
            ark_cfg,
        )

    wavespeed_cfg = get_wavespeed_config(video_gen_config)
    return (
        "wavespeed",
        wavespeed_cfg.get("api_key", ""),
        wavespeed_cfg.get("text_to_video_model"),
        wavespeed_cfg.get("image_to_video_model"),
        wavespeed_cfg.get("base_url"),
        wavespeed_cfg,
    )


def _planned_duration_bounds() -> tuple[float, float]:
    min_duration = max(
        MIN_GENERATED_SHOT_DURATION_SECONDS,
        _config_float("min_duration_seconds", MIN_GENERATED_SHOT_DURATION_SECONDS),
    )
    return min_duration, max(min_duration, _config_float("max_duration_seconds", 10))


@mcp.tool()
async def plan_video_shots(
    prompt: str,
    target_duration_seconds: int | float | None = None,
    aspect_ratio: str | None = None,
) -> dict:
    """
    Plans a video before generation: dynamic shot durations, visual anchors,
    scene continuity, transitions, bridge clips, and recommended tool calls.
    This tool does not generate media.
    """
    min_duration, max_duration = _planned_duration_bounds()
    requested_duration = (
        f"User requested total duration: {target_duration_seconds} seconds."
        if target_duration_seconds is not None
        else "Infer the total duration from content complexity; do not use a fixed default."
    )
    resolved_aspect_ratio = aspect_ratio or video_gen_config.get("default_aspect_ratio", "16:9")
    planning_prompt = f"""
You are UniVA's video director and continuity planner.

User request:
{prompt}

Constraints:
- {requested_duration}
- Aspect ratio: {resolved_aspect_ratio}.
- The configured provider can request single generated clips in roughly {min_duration:g}-{max_duration:g} second ranges. If a narrative beat needs more time, split it into multiple connected shots; do not assign every shot the same duration.
- Every generated shot must be at least {min_duration:g} seconds. If the user requested a total duration that cannot fit the requested or necessary shot count, first reduce or merge adjacent beats into fewer continuous generation units when the combined action fits within {max_duration:g} seconds. Only increase the final planned total, and explain the provider-limit exception, when the beats cannot be merged without breaking the creative intent.
- Treat a shot as a provider generation unit. Continuous motion, a single transformation, or one subject acting in one unchanged scene should stay in one shot whenever it fits within {max_duration:g} seconds. Example: a football morphing into a basketball and then a billiard ball is one continuous morph shot, not three clips.
- Split only on a real semantic boundary: new location, new time, new subject focus, new narrative beat, or required duration above {max_duration:g} seconds.
- Adjacent shots must not repeat the same composition and action. If shot N ends with a person walking on a path, shot N+1 should change viewpoint, location, action result, or narrative information instead of regenerating the same person walking on the same path.
- Do not create a default 5-second-per-shot plan. Decide shot count and duration from narrative beats, action complexity, readability, camera motion, and transition needs.
- For transformations or repeated subjects, define shared visual anchors that every related shot must reuse: object identity, color/material details, size, screen position, lighting, camera lens, rotation direction, background palette, and start/end states.
- Prefer a single continuous shot when the full transformation can fit inside the provider duration limit. If multiple clips are required, the end state of shot N must exactly match the start state of shot N+1.
- When continuity is at risk, add a bridge clip plan using frame2frame_video_gen or video_extension.
- Select transitions by visual relationship, not by habit: use hard_cut for direct informational continuity, match_cut when action/shape/composition aligns, morph or bridge_clip when one subject must transform across shots, object_wipe when a foreground object can naturally cover the frame, whip_pan/smoothleft when camera motion direction is strong, and crossfade/dissolve for smooth emotional or temporal transitions. If the user asks for smooth/seamless, prefer crossfade or a bridge clip; do not use black/white dips unless explicitly requested.
- For tail-to-head continuity, every transition must explain how shot N end_state flows into shot N+1 start_state through shared subject, screen position, motion direction, color/lighting, or an explicit bridge prompt.
- Treat the user's request as the first-pass creative brief only. After deciding the global shot plan, expand every shot into a standalone generation prompt that can be sent directly to text2video_gen/image2video_gen.
- Each expanded_generation_prompt must preserve the original meaning, share the same style anchors, and include concrete subject details, environment, foreground/midground/background composition, action timing, camera movement, atmosphere, transition context, continuity anchor, duplicate guard, and negative constraints.
- Do not let later shot prompts contradict earlier shots. Later prompts may add detail, but they must not change the established visual style, subject identity, scene chronology, lighting logic, or final message.
- If the prompt contains research context, use it to anchor factual details, locations, event details, production design, uniforms/objects, safety/legal exclusions, and current references. If research context is missing, mark research_summary.status as "missing" instead of fabricating facts.
- First write preliminary_video_info and initial_storyboard, then write final shots. The initial_storyboard can be concise, but final shots must be fully expanded.
- Expansion is descriptive, not additive: adding visual detail must not increase total duration unless provider minimums or user revision explicitly require it. Rebalance duration after expansion.
- Each shot must include visual_logic, explaining how it visually connects to the previous and next shot through composition, motion, object continuity, camera direction, color/lighting, energy, or deliberate contrast.
- The final expanded_generation_prompt must be detailed enough to send directly to the model and must be the exact prompt used by execution tools.

Return strict JSON only. Use this valid JSON shape; replace every example value with concrete plan values. Do not output type names, comments, markdown fences, or enum pipes. Enum fields must use these values: generation_tool is "text2video_gen" or "image2video_gen"; transition_type is one of "hard_cut", "crossfade", "dissolve", "match_cut", "morph", "whip_pan", "object_wipe", "bridge_clip", "fadeblack", "fadewhite"; bridge_tool is "frame2frame_video_gen", "video_extension", "merge2videos", or null. Use fadeblack/fadewhite only for explicit black/white transition requests.
{{
  "target_duration_seconds": 15,
  "aspect_ratio": "{resolved_aspect_ratio}",
  "research_summary": {{
    "status": "provided",
    "source_notes_used": ["short factual or visual reference notes used in the plan"],
    "visual_reference_anchors": ["concrete location, object, clothing, event, or design anchors"],
    "avoid_due_to_research": ["logos, protected marks, incorrect facts, unsafe or outdated visual claims"]
  }},
  "preliminary_video_info": {{
    "objective": "what the video should accomplish",
    "audience_or_use": "where/how it will be used",
    "core_message": "single sentence message",
    "hard_constraints": ["duration, aspect ratio, audio/caption restrictions, required subjects"],
    "style_direction": "shared visual direction before shot expansion"
  }},
  "initial_storyboard": [
    {{
      "shot_id": "shot_01",
      "rough_beat": "initial narrative/camera idea before detail expansion",
      "tentative_duration_seconds": 5,
      "reason": "why this beat exists"
    }}
  ],
  "style_anchors": {{
    "visual_style": "cinematic sports promo",
    "lighting": "stadium floodlights and city night glow",
    "color_palette": "red, white, green, blue, and gold accents",
    "camera_language": "fast push-ins, whip pans, match cuts, slow-motion impact shots",
    "atmosphere": "electric, celebratory, premium tournament energy",
    "shared_subject_anchors": ["same tournament identity", "football/soccer ball as recurring visual motif"]
  }},
  "shots": [
    {{
      "id": "shot_01",
      "duration_seconds": 5,
      "generation_unit_id": "unit_01",
      "scene_id": "scene_01",
      "single_take_preferred": false,
      "narrative_role": "opening hook",
      "scene_blueprint": "packed stadium and host-city energy",
      "visual_prompt": "wide stadium crowd with flags and dramatic lights",
      "camera_motion": "fast crane push-in",
      "background": "illuminated stadium architecture and cheering fans",
      "start_state": "dark pre-match anticipation",
      "end_state": "crowd erupts under bright lights",
      "continuity_anchor": "recurring football, tournament colors, premium cinematic look",
      "duplicate_guard": "next shot must change location, scale, or subject focus",
      "visual_logic": {{
        "link_from_previous": "opening visual premise or explicit handoff from the previous shot",
        "composition_change": "how framing, camera, scale, or subject focus differs from adjacent shots",
        "link_to_next": "object motion, camera direction, color/lighting, match cut, or deliberate contrast to the next shot"
      }},
      "duration_reason": "why this shot receives this length based on action, readability, camera movement, and continuity",
      "prompt_components": {{
        "subject": "football fans and tournament atmosphere",
        "subject_motion": "flags wave, lights flare, crowd rises",
        "scene": "large modern stadium at night",
        "spatial": "foreground scarves, midground fans, background pitch lights",
        "camera": "wide cinematic crane move",
        "atmosphere": "high-energy celebration",
        "stylization": "premium sports broadcast commercial",
        "transition_context": "match cut into the next host-city or player action",
        "negative_constraints": "no malformed text, no official logo replication, no watermark"
      }},
      "expanded_generation_prompt": "Standalone detailed generation prompt for this shot, including subject, scene, motion, camera, atmosphere, style anchors, continuity anchor, duplicate guard, and negative constraints.",
      "generation_tool": "text2video_gen",
      "transition_out": "match_cut"
    }}
  ],
  "expansion_audit": [
    {{
      "shot_id": "shot_01",
      "what_was_expanded": ["subject detail", "environment detail", "motion timing", "camera and spatial layers"],
      "duration_changed_by_expansion": false,
      "duration_decision": "kept or rebalanced after expansion; detail alone did not increase runtime"
    }}
  ],
  "duration_adjustment_audit": {{
    "principle": "expanded detail does not automatically increase runtime",
    "requested_total_duration": 15,
    "planned_total_duration_after_rebalance": 15,
    "shot_duration_reasoning": ["dynamic per-shot timing, not fixed defaults"]
  }},
  "transitions": [
    {{
      "from_shot": "shot_01",
      "to_shot": "shot_02",
      "transition_type": "match_cut",
      "duration_seconds": 0.4,
      "merge_transition": "hard_cut",
      "bridge_required": false,
      "bridge_tool": null,
      "bridge_prompt": "",
      "continuity_requirements": ["carry forward tournament color palette", "avoid repeating the same crowd composition"],
      "tail_to_head_handoff": "the final object/camera/color state of shot_01 that becomes the first visible state of shot_02"
    }}
  ],
  "execution_plan": [
    {{"step": 1, "tool": "text2video_gen", "shot_id": "shot_01", "duration_seconds": 5, "prompt_field": "shots[*].expanded_generation_prompt", "notes": "Generate this complete generation unit in one provider call."}}
  ],
  "quality_checks": ["research summary was considered before planning", "initial storyboard was expanded into final detailed shots", "expansion did not inflate runtime by itself", "all shots are at least minimum duration", "expanded_generation_prompt is present for every shot and is the exact generation prompt", "adjacent shots have narrative and visual logic, not repeated composition", "each transition has a concrete tail_to_head_handoff and uses black/white dips only when explicitly requested"]
}}

""".strip()

    response = query_openai(
        api_key=llm_config.get("openai_api_key", None),
        model=llm_config.get("model", "gpt-5-2025-08-07"),
        base_url=llm_config.get("base_url"),
        messages=[{"role": "user", "content": planning_prompt}],
        max_completion_tokens=8192,
    )
    plan = extract_dict(response["content"])
    if not isinstance(plan, dict):
        return ToolResponse(success=False, message="Failed to parse video shot plan.", content=response["content"])

    plan = _normalize_video_plan_durations(plan, requested_total_duration=target_duration_seconds)

    return ToolResponse(
        success=True,
        content=plan,
        message="Video shot plan generated successfully. Use each shot's expanded_generation_prompt, normalized duration, continuity anchor, and transition plan during generation.",
    )


def _get_story_image_provider():
    provider = image_gen_config.get("provider", "wavespeed")
    if provider == "volcengine_ark":
        ark_cfg = image_gen_config.get("volcengine_ark", {})
        return provider, ark_cfg.get("api_key", ""), ark_cfg

    wavespeed_cfg = get_wavespeed_config(image_gen_config)
    return "wavespeed", wavespeed_cfg.get("api_key", ""), wavespeed_cfg


def _story_text_to_image_url(prompt: str, aspect_ratio: str = "16:9"):
    provider, api_key, provider_cfg = _get_story_image_provider()
    if provider == "volcengine_ark":
        return ark_text_to_image(
            api_key,
            prompt,
            model=provider_cfg.get("text_to_image_model"),
            base_url=provider_cfg.get("base_url"),
            aspect_ratio=aspect_ratio,
        )
    return ws_text_to_image(
        api_key,
        prompt,
        model=provider_cfg.get("text_to_image_model"),
        provider=provider_cfg.get("text_to_image_provider"),
        base_url=provider_cfg.get("base_url"),
        aspect_ratio=aspect_ratio,
    )


def _story_image_to_image_url(prompt: str, image_paths: list[str], aspect_ratio: str = "16:9"):
    provider, api_key, provider_cfg = _get_story_image_provider()
    if provider == "volcengine_ark":
        result = ark_image_to_image(
            api_key,
            prompt,
            image_paths,
            model=provider_cfg.get("image_to_image_model"),
            base_url=provider_cfg.get("base_url"),
            aspect_ratio=aspect_ratio,
        )
        return result.get("output_path") if isinstance(result, dict) and result.get("success") else result
    return ws_image_to_image(
        api_key,
        prompt,
        image_paths,
        model=provider_cfg.get("image_to_image_model"),
        provider=provider_cfg.get("image_to_image_provider"),
        base_url=provider_cfg.get("base_url"),
        aspect_ratio=aspect_ratio,
    )


@mcp.tool()
async def text2video_gen(
    prompt: str,
    duration_seconds: int | float | None = None,
    aspect_ratio: str | None = None,
    auto_audio: bool | None = None,
    include_voiceover: bool | None = None,
    audio_prompt: str | None = None,
) -> dict:
    """
    Generates a video from a text description using the configured provider.
    The requested duration is optional and is clamped by video_gen duration settings.

    Args:
        prompt (str): The prompt to generate the video.
        duration_seconds (int | float | None): Planned shot duration in seconds.
        aspect_ratio (str | None): Approved shot aspect ratio; defaults to config only when omitted.
        auto_audio (bool | None): Whether to automatically add BGM/SFX/ambient audio. Defaults to config.
        include_voiceover (bool | None): Generate narration/dubbing only when explicitly requested.
        audio_prompt (str | None): Optional sound-design prompt; defaults to the video prompt.

    Returns:
        dict: A dictionary containing the success status, output video path, and a message.
              - 'success' (bool): True if the video was generated successfully, False otherwise.
              - 'output_path' (str, optional): The path to the generated video if successful.
              - 'message' (str, optional): A success message.
              - 'error' (str, optional): An error message if the generation failed.
    """
    model = video_gen_config.get("text_to_video")

    if model == "seedance":
        provider, api_key, t2v_model, i2v_model, base_url, ark_cfg = _get_video_provider()
        duration = _resolve_duration(duration_seconds)
        resolved_aspect_ratio = aspect_ratio or video_gen_config.get("default_aspect_ratio", "16:9")
        save_dir = _univa_path(f"results/{datetime.now().strftime('%Y%m%d%H%M%S')}_{prompt[:30].replace(' ', '_')}")
        os.makedirs(save_dir, exist_ok=True)
        _time = datetime.now().strftime("%m%d%H%M%S")
        save_path = f"{save_dir}/{_time}.mp4"

        if provider == "volcengine_ark":
            return_dict = ark_text_to_video(
                api_key,
                prompt,
                save_path=save_path,
                model=t2v_model,
                base_url=base_url,
                duration=duration,
                aspect_ratio=resolved_aspect_ratio,
            )
        else:
            return_dict = ws_text_to_video(
                api_key,
                prompt,
                save_path=save_path,
                model=t2v_model,
                provider=ark_cfg.get("text_to_video_provider"),
                duration=duration,
                base_url=base_url,
                aspect_ratio=resolved_aspect_ratio,
            )
        if isinstance(return_dict, dict):
            return_dict["generation_request"] = {
                "prompt": prompt,
                "prompt_sha256": _sha256_text(prompt),
                "duration_seconds": duration,
                "aspect_ratio": resolved_aspect_ratio,
                "provider": provider,
                "model": t2v_model,
            }

        if return_dict and return_dict.get("success"):
            audio_path, audio_meta = _attach_auto_audio(
                return_dict.get("output_path"),
                audio_prompt or prompt,
                auto_audio=auto_audio,
                include_voiceover=include_voiceover,
                target_duration_seconds=duration,
            )
            if audio_path:
                return_dict["output_path"] = audio_path
            if audio_meta:
                return_dict.update(audio_meta)
        return return_dict


@mcp.tool()
async def storyvideo_gen(
    prompt: str,
    save_dir: str = None,
    auto_audio: bool | None = None,
    include_voiceover: bool | None = None,
    audio_prompt: str | None = None,
) -> ToolResponse:
    """
    Generates a story-based video from a text prompt by creating a storyboard, generating character images,
    creating keyframes, generating video segments, and merging them into a final video.

    This function follows these steps:
    1. Generates a storyboard based on the input prompt
    2. Extracts character descriptions from the storyboard and generates character images
    3. For each shot in the storyboard:
       - Generates keyframe images based on shot descriptions and characters
       - Converts keyframes to video segments
    4. Merges all video segments into a final video

    Args:
        prompt (str): A text description of the story or video content to generate.
        save_dir (str, optional): Directory for intermediate assets and final output.

    Returns:
        dict: A dictionary containing the success status, output video path, and a message.
              - 'success' (bool): True if the video was generated successfully, False otherwise.
              - 'output_path' (str, optional): The path to the generated video if successful.
              - 'message' (str, optional): A success message.
              - 'error' (str, optional): An error message if the generation failed.
    """

    model = video_gen_config.get("text_to_video")
    if model == "seedance":
        if save_dir is None:
            save_dir = _univa_path(f"infer/v2v/{datetime.now().strftime('%Y%m%d%H%M%S')}_{prompt[:30].replace(' ', '_')}")
        else:
            save_dir = os.path.abspath(save_dir)
        os.makedirs(save_dir, exist_ok=True)

        # 1.generate a storyboard first
        user_prompt = prompt
        storyboard = _normalize_storyboard_durations(await storyboard_generate(prompt))
        time = datetime.now().strftime("%m%d%H%M%S")
        storyboard_path = os.path.join(save_dir, f"{time}_storyboard.json")
        with open(storyboard_path, "w", encoding="utf-8") as f:
            json.dump(storyboard, f, indent=4, ensure_ascii=False)
        # 2.generate character images
        characters = storyboard.get("characters") or []
        characters_image_path = dict()

        # TODO: style
        style = storyboard.get("style")

        for character in characters:
            char_id = character.get("id")
            char_description = character.get("description")
            refined_char_description = refine_gen_prompt(char_description, media_type="character")

            image_url = _story_text_to_image_url(refined_char_description, aspect_ratio="1:1")
            time = datetime.now().strftime("%m%d%H%M%S")
            image_save_path = f"{save_dir}/{time}_{char_id}.jpg"
            characters_image_path[char_id] = image_save_path
            download_image(image_url, save_path=image_save_path)

        # 3.key frame generation
        shots = storyboard.get("shots") or []
        shots_image_path = dict()
        for shot in shots:
            shot_id = shot.get("id")
            setting_description = shot.get("setting_description")
            plot_correspondence = shot.get("plot_correspondence")
            static_shot_description = shot.get("static_shot_description")
            onstage_characters = shot.get("onstage_characters") or []
            onstage_characters_image_path_list = [characters_image_path.get(char_id) for char_id in onstage_characters]

            keyframe_prompt = _storyboard_shot_prompt(shot, style=style)
            # refined_keyframe_prompt = refine_gen_prompt(keyframe_prompt, media_type="image")

            if len(onstage_characters_image_path_list) == 0:
                image_url = _story_text_to_image_url(keyframe_prompt, aspect_ratio="4:3")
            else:
                image_url = _story_image_to_image_url(keyframe_prompt, onstage_characters_image_path_list, aspect_ratio="4:3")
            time = datetime.now().strftime("%m%d%H%M%S")
            image_save_path = f"{save_dir}/{time}_{shot_id}.jpg"
            shots_image_path[shot_id] = image_save_path
            download_image(image_url, save_path=image_save_path)

        # 4.generate video segments based on keyframes
        video_segment_list = []
        provider, vg_api_key, t2v_model, i2v_model, base_url, ark_cfg = _get_video_provider()
        for idx, (keyframe_id, keyframe) in enumerate(shots_image_path.items()):
            setting_description = shots[idx].get("setting_description")
            plot_correspondence = shots[idx].get("plot_correspondence")
            static_shot_description = shots[idx].get("static_shot_description")

            keyframe_prompt = _storyboard_shot_prompt(shots[idx], style=style)

            time = datetime.now().strftime("%m%d%H%M%S")
            save_path = f"{save_dir}/{time}_{keyframe_id}.mp4"
            shot_duration = _duration_from_shot(shots[idx])
            if provider == "volcengine_ark":
                return_dict = ark_image_to_video(
                    vg_api_key,
                    keyframe_prompt,
                    keyframe,
                    save_path=save_path,
                    model=i2v_model,
                    base_url=base_url,
                    duration=shot_duration,
                )
            else:
                return_dict = ws_image_to_video(
                    vg_api_key,
                    keyframe_prompt,
                    keyframe,
                    save_path=save_path,
                    model=i2v_model,
                    provider=ark_cfg.get("image_to_video_provider"),
                    duration=shot_duration,
                    base_url=base_url,
                )

            if return_dict.get("success"):
                video_segment_list.append(return_dict.get("output_path"))
        # TODO: 5.audio integration
        # audio_list = []
        # for idx, shot in enumerate(shots):
        #     # audio_description = shot.get("audio_description")
            
        #     video_path = video_segment_list[idx]
        #     audio_description = audio_prompt_gen(video_path)
        #     time = datetime.now().strftime("%m%d%H%M%S")
        #     save_path = f"{save_dir}/{time}_{idx+1}.mp4"
        #     return_dict = audio_gen(
        #         api_key=api,
        #         prompt=audio_description,
        #         video_url=video_path,
        #         save_path=save_path,
        #     )

        #     if return_dict.get("success"):
        #         audio_list.append(return_dict.get("output_path"))
            

        # 6.concatenate video segments
        time = datetime.now().strftime("%m%d%H%M%S")
        prompt_name = user_prompt.replace(" ", "_")[:50]
        movie_save_path = f"{save_dir}/{time}_{prompt_name}.mp4"
        video_path = _merge_generated_videos(video_segment_list, output_file=movie_save_path)
        final_path, audio_meta = _attach_auto_audio(
            video_path,
            audio_prompt or user_prompt,
            auto_audio=auto_audio,
            include_voiceover=include_voiceover,
            video_plan=storyboard,
            target_duration_seconds=sum((_duration_from_shot(s) or 0) for s in shots) or None,
        )
        
        return ToolResponse(
            success=True,
            output_path=final_path or video_path,
            content=audio_meta,
            message="Video generated successfully." if not audio_meta or not audio_meta.get("audio_output_path") else "Video generated successfully with audio."
        )



@mcp.tool()
async def entity2video(
    prompt: str,
    images: List[str],
    auto_audio: bool | None = None,
    include_voiceover: bool | None = None,
    audio_prompt: str | None = None,
) -> dict:
    """
    Generates a story-based video from a text prompt and a list of character images by creating a storyboard,
    using the provided images for characters, generating keyframes, creating video segments, and merging them
    into a final video.

    This function is similar to storyvideo_gen but allows users to provide their own character images instead
    of generating them from descriptions. It follows these steps:
    1. Generates a storyboard based on the input prompt
    2. Uses the provided images as character images
    3. For each shot in the storyboard:
       - Generates keyframe images based on shot descriptions and characters
       - Converts keyframes to video segments
    4. Merges all video segments into a final video

    Args:
        prompt (str): A text description of the story or video content to generate.
        save_dir (str, optional): Directory for intermediate assets and final output.
        images (List[str]): A list of file paths to character images that should be used in the video.

    Returns:
        dict: A dictionary containing the success status, output video path, and a message.
              - 'success' (bool): True if the video was generated successfully, False otherwise.
              - 'output_path' (str, optional): The path to the generated video if successful.
              - 'message' (str, optional): A success message.
              - 'error' (str, optional): An error message if the generation failed.
    """

    model = video_gen_config.get("text_to_video")
    if model == "seedance":
        user_prompt = prompt
        save_dir = _univa_path(f"infer/v2v/{datetime.now().strftime('%Y%m%d%H%M%S')}_{prompt[:30].replace(' ', '_')}")
        os.makedirs(save_dir, exist_ok=True)

        prompt = f"{prompt}\nsource images path: {str(images)}"
        storyboard = _normalize_storyboard_durations(await storyboard_generate(prompt, gentype="entity2video"))
        characters_image_path = dict()

        # TODO: style
        style = storyboard.get("style")

        characters = storyboard.get("characters")
        for idx, character in enumerate(characters):
            char_id = f"char_{idx+1}"
            character_path = character.get("path")
            characters_image_path[char_id] = character_path

        shots = storyboard.get("shots") or []
        shots_image_path = dict()
        for shot in shots:
            shot_id = shot.get("id")
            setting_description = shot.get("setting_description")
            plot_correspondence = shot.get("plot_correspondence")
            static_shot_description = shot.get("static_shot_description")
            onstage_characters = shot.get("onstage_characters") or []
            onstage_characters_image_path_list = [characters_image_path.get(char_id) for char_id in onstage_characters]

            keyframe_prompt = _storyboard_shot_prompt(shot, style=style)
            if len(onstage_characters_image_path_list) == 0:
                image_url = _story_text_to_image_url(keyframe_prompt)
            else:
                image_url = _story_image_to_image_url(keyframe_prompt, onstage_characters_image_path_list)
            # sleep(3)
            time = datetime.now().strftime("%m%d%H%M%S")
            image_save_path = f"{save_dir}/{time}_{shot_id}.jpg"
            shots_image_path[shot_id] = image_save_path
            download_image(image_url, save_path=image_save_path)

        video_segment_list = []
        provider, vg_api_key, t2v_model, i2v_model, base_url, ark_cfg = _get_video_provider()
        for idx, (keyframe_id, keyframe) in enumerate(shots_image_path.items()):

            setting_description = shots[idx].get("setting_description")
            plot_correspondence = shots[idx].get("plot_correspondence")
            static_shot_description = shots[idx].get("static_shot_description")

            keyframe_prompt = _storyboard_shot_prompt(shots[idx], style=style)

            time = datetime.now().strftime("%m%d%H%M%S")
            save_path = f"{save_dir}/{time}_{keyframe_id}.mp4"
            shot_duration = _duration_from_shot(shots[idx])
            if provider == "volcengine_ark":
                return_dict = ark_image_to_video(
                    vg_api_key,
                    keyframe_prompt,
                    keyframe,
                    save_path=save_path,
                    model=i2v_model,
                    base_url=base_url,
                    duration=shot_duration,
                )
            else:
                return_dict = ws_image_to_video(
                    vg_api_key,
                    keyframe_prompt,
                    keyframe,
                    save_path=save_path,
                    model=i2v_model,
                    provider=ark_cfg.get("image_to_video_provider"),
                    duration=shot_duration,
                    base_url=base_url,
                )

            if return_dict.get("success"):
                video_segment_list.append(return_dict.get("output_path"))

        time = datetime.now().strftime("%m%d%H%M%S")
        prompt_name = user_prompt.replace(" ", "_")[:50]
        movie_save_path = f"{save_dir}/{time}_{prompt_name}.mp4"
        video_path = _merge_generated_videos(video_segment_list, output_file=movie_save_path)
        final_path, audio_meta = _attach_auto_audio(
            video_path,
            audio_prompt or user_prompt,
            auto_audio=auto_audio,
            include_voiceover=include_voiceover,
            video_plan=storyboard,
            target_duration_seconds=sum((_duration_from_shot(s) or 0) for s in shots) or None,
        )
        
        return ToolResponse(
            success=True,
            output_path=final_path or video_path,
            content=audio_meta,
            message="Video generated successfully." if not audio_meta or not audio_meta.get("audio_output_path") else "Video generated successfully with audio."
        )




@mcp.tool()
async def image2video_gen(
    prompt: str,
    image_path: str,
    duration_seconds: int | float | None = None,
    aspect_ratio: str | None = None,
    auto_audio: bool | None = None,
    include_voiceover: bool | None = None,
    audio_prompt: str | None = None,
) -> dict:
    """
    Generates a video from a prompt and an input image using the configured provider.
    The requested duration is optional and is clamped by video_gen duration settings.

    Args:
        prompt (str): The prompt to generate the video.
        image_path (str): Input image path for use as video content reference, supporting common formats (.jpg/.png/.bmp, etc.).
        duration_seconds (int | float | None): Planned shot duration in seconds.
        aspect_ratio (str | None): Approved shot aspect ratio; source-image providers may treat it as advisory.
        auto_audio (bool | None): Whether to automatically add BGM/SFX/ambient audio. Defaults to config.
        include_voiceover (bool | None): Generate narration/dubbing only when explicitly requested.
        audio_prompt (str | None): Optional sound-design prompt; defaults to the video prompt.

    Returns:
        dict: A dictionary containing the success status, output video path, and a message.
              - 'success' (bool): True if the video was generated successfully, False otherwise.
              - 'output_path' (str, optional): The path to the generated video if successful.
              - 'message' (str, optional): A success message.
              - 'error' (str, optional): An error message if the generation failed.
    """
    model = video_gen_config.get("image_to_video")

    if model == "seedance":
        provider, api_key, t2v_model, i2v_model, base_url, ark_cfg = _get_video_provider()
        duration = _resolve_duration(duration_seconds)
        resolved_aspect_ratio = aspect_ratio or video_gen_config.get("default_aspect_ratio", "16:9")
        save_dir = _univa_path(f"results/{datetime.now().strftime('%Y%m%d%H%M%S')}_{prompt[:30].replace(' ', '_')}")
        os.makedirs(save_dir, exist_ok=True)
        _time = datetime.now().strftime("%m%d%H%M%S")
        save_path = f"{save_dir}/{_time}.mp4"

        if provider == "volcengine_ark":
            return_dict = ark_image_to_video(
                api_key,
                prompt,
                image_path,
                save_path=save_path,
                model=i2v_model,
                base_url=base_url,
                duration=duration,
                aspect_ratio=resolved_aspect_ratio,
            )
        else:
            return_dict = ws_image_to_video(
                api_key,
                prompt,
                image_path,
                save_path=save_path,
                model=i2v_model,
                provider=ark_cfg.get("image_to_video_provider"),
                duration=duration,
                base_url=base_url,
                aspect_ratio=resolved_aspect_ratio,
            )
        if isinstance(return_dict, dict):
            return_dict["generation_request"] = {
                "prompt": prompt,
                "prompt_sha256": _sha256_text(prompt),
                "duration_seconds": duration,
                "aspect_ratio": resolved_aspect_ratio,
                "provider": provider,
                "model": i2v_model,
                "image_path": image_path,
            }

        if return_dict and return_dict.get("success"):
            audio_path, audio_meta = _attach_auto_audio(
                return_dict.get("output_path"),
                audio_prompt or prompt,
                auto_audio=auto_audio,
                include_voiceover=include_voiceover,
                target_duration_seconds=duration,
            )
            if audio_path:
                return_dict["output_path"] = audio_path
            if audio_meta:
                return_dict.update(audio_meta)
        return return_dict


@mcp.tool()
async def video_extension(
    prompt: str,
    video_path: str,
    duration_seconds: int | float | None = None,
    auto_audio: bool | None = None,
    include_voiceover: bool | None = None,
    audio_prompt: str | None = None,
) -> Dict:
    """
    Extends an existing video by generating new content based on a text prompt and the last frame of the input video.
    If segment_id is provided, it updates the corresponding segment in the server timeline.
    Otherwise, it generates a video without adding it to the timeline.

    Args:
        prompt (str): The prompt to generate the video.
        video_path (str): Input video path for use as video content reference, supporting common formats (.mp4/.avi, etc.).
        duration_seconds (int | float | None): Planned extension duration in seconds.

    Returns:
        dict: A dictionary containing the success status, output video path, and a message.
              - 'success' (bool): True if the video was extended successfully, False otherwise.
              - 'output_path' (str, optional): The path to the extended video if successful.
              - 'message' (str, optional): A success message.
              - 'error' (str, optional): An error message if the extension failed.
    """
    time_ = datetime.now().strftime("%m%d%H%M%S")
    last_frame_save_path = save_last_frame_decord(video_path, _univa_path(f"results/{time_}_last_frame.png"))
    # Pass segment_id to image2video_gen if it's meant to update a segment
    extend_result = await image2video_gen(
        prompt,
        last_frame_save_path,
        duration_seconds=duration_seconds,
        auto_audio=auto_audio,
        include_voiceover=include_voiceover,
        audio_prompt=audio_prompt,
    )
    if extend_result.get("success"):
        output_video_path = extend_result.get("output_path")

        return ToolResponse(
            success=True,
            output_path=output_video_path,
            message="Video extended and merged successfully."
        )


    else:
        return ToolResponse(
            success=False,
            message="Video extension failed at image2video generation step.",
        )


@mcp.tool()
async def frame2frame_video_gen(
    prompt: str,
    first_frame_path: str,
    last_frame_path: str,
    duration_seconds: int | float | None = None,
    auto_audio: bool | None = None,
    include_voiceover: bool | None = None,
    audio_prompt: str | None = None,
) -> dict:
    """
    Generates a transition video between a specified first frame and a last frame, guided by a text prompt.
    This tool is effective for creating dynamic action sequences or smooth transitions between two distinct visual states.

    Args:
        prompt (str): The prompt to generate the video.
        first_frame_path (str): The path to the first frame.
        last_frame_path (str): The path to the last frame.
        duration_seconds (int | float | None): Planned bridge duration in seconds when supported by the provider.

    Returns:
        dict: A dictionary containing the success status and a message.
              - 'success' (bool): True if the video was generated successfully, False otherwise.
              - 'message' (str, optional): A success message.
              - 'error' (str, optional): An error message if the generation failed.
    """
    model = video_gen_config.get("frame_to_frame_video")
    
    if model == "wan_api":
        provider, api_key, t2v_model, i2v_model, base_url, provider_cfg = _get_video_provider()
        if provider != "wavespeed":
            return ToolResponse(success=False, error="frame2frame_video_gen is configured for wan_api, which requires the wavespeed provider.")
        duration = _resolve_duration(duration_seconds)
        save_dir = _univa_path(f"results/{datetime.now().strftime('%Y%m%d%H%M%S')}_{prompt[:30].replace(' ', '_')}")
        os.makedirs(save_dir, exist_ok=True)
        _time = datetime.now().strftime("%m%d%H%M%S")
        save_path = f"{save_dir}/{_time}.mp4"
        bridge_prompt = f"{prompt} Target bridge duration: {duration} seconds."
        return_dict = hailuo_i2v_pro(
            api_key,
            bridge_prompt,
            first_frame_path,
            last_frame_path,
            save_path=save_path,
            model=provider_cfg.get("frame_to_frame_model"),
            provider=provider_cfg.get("frame_to_frame_provider"),
            base_url=base_url,
        )

        if return_dict and return_dict.get("success"):
            audio_path, audio_meta = _attach_auto_audio(
                return_dict.get("output_path"),
                audio_prompt or prompt,
                auto_audio=auto_audio,
                include_voiceover=include_voiceover,
                target_duration_seconds=duration,
            )
            if audio_path:
                return_dict["output_path"] = audio_path
            if audio_meta:
                return_dict.update(audio_meta)
        return return_dict



@mcp.tool()
def remotion_compose_video(
    input_video_path: str,
    output_path: str | None = None,
    title: str | None = None,
    subtitle: str | None = None,
    captions: list | None = None,
    overlays: list | None = None,
    brand: dict | None = None,
    theme: dict | None = None,
    width: int | None = None,
    height: int | None = None,
    fps: int | None = None,
    show_progress: bool = True,
    fit: str = "cover",
    browser_executable_path: str | None = None,
    remotion_binaries_directory: str | None = None,
    remotion_timeout_ms: int | None = None,
    fallback_to_ffmpeg_subtitles: bool | None = None,
) -> ToolResponse:
    """
    Adds a Remotion-rendered final packaging layer to an approved video.

    This tool is a deterministic compose step for subtitles, title cards,
    lower-thirds, CTA badges, brand bugs, and progress bars. It does not
    generate or alter the underlying video content.
    """
    if output_path is None:
        save_dir = _univa_path(f"results/{datetime.now().strftime('%Y%m%d%H%M%S')}_remotion_compose")
        os.makedirs(save_dir, exist_ok=True)
        output_path = os.path.join(save_dir, f"{datetime.now().strftime('%m%d%H%M%S')}_remotion.mp4")

    return _remotion_render(
        input_video_path,
        output_path,
        title=title,
        subtitle=subtitle,
        captions=captions,
        overlays=overlays,
        brand=brand,
        theme=theme,
        width=width,
        height=height,
        fps=fps,
        show_progress=show_progress,
        fit=fit,
        browser_executable_path=browser_executable_path,
        remotion_binaries_directory=remotion_binaries_directory,
        remotion_timeout_ms=remotion_timeout_ms,
        fallback_to_ffmpeg_subtitles=fallback_to_ffmpeg_subtitles,
    )


@mcp.tool()
async def merge2videos(
    video_paths: list[str],
    transition: str | None = None,
    transition_duration_seconds: int | float | None = None,
    transition_plan: list | None = None,
    auto_audio: bool | None = None,
    include_voiceover: bool | None = None,
    include_bgm: bool | None = None,
    include_sfx: bool | None = None,
    audio_prompt: str | None = None,
    remotion_compose: bool | None = None,
    remotion_title: str | None = None,
    remotion_subtitle: str | None = None,
    caption_plan: list | None = None,
    visual_overlays: list | None = None,
    brand: dict | None = None,
    remotion_theme: dict | None = None,
    remotion_browser_executable_path: str | None = None,
    remotion_binaries_directory: str | None = None,
    remotion_timeout_ms: int | None = None,
    remotion_fallback_to_ffmpeg_subtitles: bool | None = None,
):
    """
    Merges multiple video files into a single video file.
    By default it uses the configured transition strategy instead of a hard concat.

    Args:
        video_paths (list[str]): Ordered paths to the video files to merge.
        transition (str | None): Optional transition name or raw user phrase, e.g. smooth/seamless/whip_pan/hard_cut.
        transition_duration_seconds (int | float | None): Optional transition duration.
        transition_plan (list | None): Optional per-edge transition list or plan dicts from plan_video_shots; ignored when transition is explicitly set.
        auto_audio (bool | None): Whether to automatically add BGM/SFX/ambient audio to the merged deliverable. Defaults to config.
        include_voiceover (bool | None): Generate narration/dubbing only when explicitly requested.
        include_bgm (bool | None): Include BGM only when allowed by the approved plan.
        include_sfx (bool | None): Include ambience/action SFX only when allowed by the approved plan.
        audio_prompt (str | None): Optional sound-design prompt for the final merged video.
        remotion_compose (bool | None): Enable optional Remotion final packaging after merge/audio.
        remotion_title/remotion_subtitle: Optional intro title treatment.
        caption_plan (list | None): Timed captions using {text,start_seconds,end_seconds} or word timings.
        visual_overlays (list | None): Timed cards/lower-thirds/CTA overlays for Remotion.
        brand/remotion_theme: Optional brand and theme config for final packaging.
        remotion_browser_executable_path (str | None): Optional Chrome/Chromium executable path for offline Remotion rendering.
        remotion_binaries_directory (str | None): Optional Remotion compositor/ffmpeg directory for Linux compatibility.
        remotion_timeout_ms (int | None): Passed through to Remotion CLI --timeout.
        remotion_fallback_to_ffmpeg_subtitles (bool | None): Fall back to FFmpeg ASS burned captions when Remotion cannot run.

    Returns:
        dict: A dictionary containing the success status and a message.
              - 'success' (bool): True if the video was generated successfully, False otherwise.
              - 'output_path' (str): The path to the merged video.
              - 'message' (str): A success message.
    """
    save_dir = _univa_path(f"results/{datetime.now().strftime('%Y%m%d%H%M%S')}")
    os.makedirs(save_dir, exist_ok=True)
    _time = datetime.now().strftime("%m%d%H%M%S")
    save_path = f"{save_dir}/{_time}.mp4"
    planned_transitions = _transitions_from_plan(transition_plan)
    transition_input = transition if transition is not None else planned_transitions
    resolved_transition, resolved_duration, output_size = _merge_settings(transition, transition_duration_seconds)
    executable_transition = resolve_merge_transition(resolved_transition if transition_input is None or isinstance(transition_input, str) else transition_input[0])
    transition_capabilities = supported_merge_transitions()
    video_path = _merge_generated_videos(
        video_paths,
        output_file=save_path,
        transition=transition,
        transition_duration_seconds=transition_duration_seconds,
        transition_plan=transition_plan,
    )
    final_path, audio_meta = _attach_auto_audio(
        video_path,
        audio_prompt or "Final merged video with cohesive BGM, environment ambience, action-synced sound effects, and transition sound effects. Do not include narration unless explicitly requested.",
        auto_audio=auto_audio,
        include_voiceover=include_voiceover,
        include_bgm=include_bgm,
        include_sfx=include_sfx,
        target_duration_seconds=_probe_video_duration(video_path),
    )

    merge_meta = {
        "requested_transition": transition,
        "transition_plan_used": planned_transitions,
        "configured_or_default_transition": resolved_transition,
        "resolved_transition": executable_transition,
        "resolved_transition_plan": [resolve_merge_transition(item) for item in transition_input] if isinstance(transition_input, list) else None,
        "transition_duration_seconds": resolved_duration,
        "output_size": output_size,
        "supported_transitions": transition_capabilities,
        "source_audio_preserved_when_present": True,
    }
    if audio_meta:
        merge_meta.update(audio_meta)

    delivered_path = final_path or video_path
    remotion_result = None
    if delivered_path and _remotion_enabled(remotion_compose):
        remotion_dir = os.path.dirname(delivered_path) or save_dir
        remotion_output = os.path.join(
            remotion_dir,
            f"{Path(delivered_path).stem}_remotion.mp4",
        )
        remotion_result = _remotion_render(
            delivered_path,
            remotion_output,
            title=remotion_title,
            subtitle=remotion_subtitle,
            captions=caption_plan,
            overlays=visual_overlays,
            brand=brand,
            theme=remotion_theme,
            browser_executable_path=remotion_browser_executable_path,
            remotion_binaries_directory=remotion_binaries_directory,
            remotion_timeout_ms=remotion_timeout_ms,
            fallback_to_ffmpeg_subtitles=remotion_fallback_to_ffmpeg_subtitles,
        )
        merge_meta["remotion_compose"] = {
            "requested": True,
            "success": bool(getattr(remotion_result, "success", False)),
            "output_path": getattr(remotion_result, "output_path", None),
            "error": getattr(remotion_result, "error", None),
            "content": getattr(remotion_result, "content", None),
        }
        if getattr(remotion_result, "success", False) and getattr(remotion_result, "output_path", None):
            delivered_path = remotion_result.output_path
    else:
        merge_meta["remotion_compose"] = {"requested": bool(_remotion_enabled(remotion_compose)), "success": False}

    message = "Video merge failed."
    if video_path:
        if remotion_result and getattr(remotion_result, "success", False):
            remotion_method = ((getattr(remotion_result, "content", None) or {}).get("method"))
            if remotion_method == "ffmpeg_ass_subtitle_fallback":
                message = "Videos merged successfully with FFmpeg subtitle fallback after Remotion failure."
            else:
                message = "Videos merged successfully with Remotion compose."
        elif audio_meta and audio_meta.get("audio_output_path"):
            message = "Videos merged successfully with audio."
        else:
            message = "Videos merged successfully."

    return ToolResponse(
        success=bool(video_path),
        output_path=delivered_path,
        content=merge_meta,
        message=message,
    )


if __name__ == "__main__":
    mcp.run(transport="stdio")
