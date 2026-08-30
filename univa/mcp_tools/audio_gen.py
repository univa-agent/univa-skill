import os
from datetime import datetime
from typing import Any
from mcp.server.fastmcp import FastMCP

from univa.config.mcp_config import get_mcp_section, get_wavespeed_config
from univa.utils.audio_timeline import mix_audio_timeline
from univa.utils.query_llm import query_openai
from univa.utils.text_process import extract_dict
from univa.mcp_tools.base import ToolResponse, redact_secrets, setup_logger
from univa.utils.wavespeed_api import audio_gen as wavespeed_audio_gen, speech_gen as wavespeed_speech_gen


audio_gen_config = get_mcp_section("audio_gen")
llm_config = get_mcp_section("llm")

logger = setup_logger(__name__, "logs/mcp_tools", "audio_gen.log")
logger.info("Loaded audio_gen_config: %s", redact_secrets(audio_gen_config))

mcp = FastMCP("Audio_Generation_Server")


def _get_audio_provider():
    provider = audio_gen_config.get("provider", "wavespeed")
    if provider != "wavespeed":
        return provider, "", {}
    wavespeed_cfg = get_wavespeed_config(audio_gen_config)
    return "wavespeed", wavespeed_cfg.get("api_key", ""), wavespeed_cfg


def _float_config(key: str, default: float) -> float:
    try:
        return float(audio_gen_config.get(key, default))
    except (TypeError, ValueError):
        return float(default)


def _resolve_audio_duration(duration_seconds: int | float | None = None) -> int:
    requested = duration_seconds if duration_seconds is not None else audio_gen_config.get("duration", 5)
    try:
        duration = float(requested)
    except (TypeError, ValueError):
        duration = _float_config("duration", 5)
    return max(1, int(round(duration)))


def _safe_name(text: str, limit: int = 30) -> str:
    return "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in text[:limit]).strip("_") or "audio"


def _audio_output_dir() -> str:
    base_output_path = audio_gen_config.get("base_output_path", "results/audio")
    base_dir = os.path.abspath(os.path.join(os.path.dirname(os.path.dirname(__file__)), base_output_path))
    os.makedirs(base_dir, exist_ok=True)
    return base_dir


def _audio_save_path(prefix: str, text: str, suffix: str = "mp3") -> str:
    _time = datetime.now().strftime("%m%d%H%M%S")
    return os.path.join(_audio_output_dir(), f"{_time}_{prefix}_{_safe_name(text)}.{suffix}")


@mcp.tool()
def plan_audio_for_video(
    video_prompt: str,
    video_plan: dict[str, Any] | None = None,
    target_duration_seconds: int | float | None = None,
    include_voiceover: bool = False,
    include_bgm: bool = True,
    include_sfx: bool = True,
) -> ToolResponse:
    """Plan BGM, SFX, and voiceover against the video shot timeline. Does not generate media."""
    duration_text = (
        f"Target total duration: {target_duration_seconds} seconds."
        if target_duration_seconds is not None
        else "Infer total duration from the provided video plan or prompt."
    )
    planning_prompt = f"""
You are UniVA's sound designer. Create a production-ready audio plan for an AI-generated video.

Video request:
{video_prompt}

Video plan JSON, if available:
{video_plan or {}}

Constraints:
- {duration_text}
- include_voiceover={include_voiceover}, include_bgm={include_bgm}, include_sfx={include_sfx}. Voiceover/narration must remain disabled unless include_voiceover=true or the user explicitly asks for narration, dubbing, dialogue, or spoken commentary.
- Follow a declarative timeline like Video-ShotCraft: BGM sets the energy bed, SFX are pinned relative to shot start, and voiceover uses one stable voice/personality across the whole video.
- Do not scatter generic sounds. Choose sound vocabulary by genre and scene: sports uses crowd/ball impact/shoe squeak/whistles; product promo uses whoosh/impact/riser/sparkle; nature uses ambience/foley; cinematic story uses ambience + sparse motivated effects.
- Use relative timing: shot_id + offset_seconds. Do not use unexplained absolute timestamps when shot timing is available.
- Avoid machine-gun repetition: for repeated events use alternating prompts, descending volume, or merge dense hits into one swoosh/riser.
- Keep BGM under voiceover; reserve headroom for major SFX.

Return strict JSON only:
{{
  "audio_style": {{
    "genre": string,
    "bgm_mood": string,
    "sfx_vocabulary": [string],
    "voice_profile": {{"voice": string, "emotion": string, "pace": string, "personality": string}}
  }},
  "bgm": {{
    "enabled": boolean,
    "prompt": string,
    "start_seconds": number,
    "duration_seconds": number,
    "volume": number,
    "fade_in_seconds": number,
    "fade_out_seconds": number
  }},
  "sfx_events": [
    {{
      "id": string,
      "shot_id": string,
      "offset_seconds": number,
      "start_seconds": number,
      "duration_seconds": number,
      "prompt": string,
      "volume": number,
      "fade_in_seconds": number,
      "fade_out_seconds": number,
      "reason": string
    }}
  ],
  "voiceover_segments": [
    {{
      "id": string,
      "shot_id": string,
      "start_seconds": number,
      "duration_seconds": number,
      "text": string,
      "voice": string,
      "emotion": string,
      "speed": number,
      "volume": number,
      "reason": string
    }}
  ],
  "mixing": {{
    "original_audio_volume": number,
    "bgm_volume": number,
    "sfx_peak_volume": number,
    "voiceover_volume": number,
    "duck_bgm_under_voiceover": boolean
  }},
  "quality_checks": [string]
}}
""".strip()
    response = query_openai(
        api_key=llm_config.get("openai_api_key", None),
        model=llm_config.get("model", "gpt-5-2025-08-07"),
        base_url=llm_config.get("base_url"),
        messages=[{"role": "user", "content": planning_prompt}],
        max_completion_tokens=8192,
    )
    plan = extract_dict(response.get("content", ""))
    if not isinstance(plan, dict):
        return ToolResponse(success=False, message="Failed to parse audio plan.", content=response.get("content", ""))
    return ToolResponse(success=True, content=plan, message="Audio plan generated successfully.")


@mcp.tool()
def audio_gen(prompt: str, video_path: str = None, duration_seconds: int | float | None = None, audio_role: str = "sfx") -> ToolResponse:
    """Generates BGM/SFX/ambient audio based on a text prompt, optionally synchronized to video."""
    provider, api_key, provider_cfg = _get_audio_provider()
    if provider != "wavespeed":
        return ToolResponse(success=False, error=f"Unsupported audio_gen provider: {provider}")

    model = provider_cfg.get("audio_model") or audio_gen_config.get("default_model", "mmaudio-v2")
    duration = _resolve_audio_duration(duration_seconds)
    guidance_scale = audio_gen_config.get("guidance_scale", 4.5)
    num_inference_steps = audio_gen_config.get("num_inference_steps", 25)
    save_path = _audio_save_path(audio_role, prompt, 'mp4' if video_path else 'mp3')

    result = wavespeed_audio_gen(
        api_key=api_key,
        prompt=prompt,
        video_url=video_path if video_path else "",
        model=model,
        provider=provider_cfg.get("audio_provider"),
        base_url=provider_cfg.get("base_url"),
        save_path=save_path,
        duration=duration,
        guidance_scale=guidance_scale,
        num_inference_steps=num_inference_steps,
    )

    if result and result.get("success"):
        logger.info(f"Audio generated successfully: {result.get('output_path')}")
        return ToolResponse(success=True, output_path=result.get("output_path", save_path), message="Audio generated successfully.")

    logger.error(f"Audio generation failed: {result.get('error') if isinstance(result, dict) else result}")
    return ToolResponse(success=False, error=(result or {}).get("error", "Unknown error during audio generation."))


@mcp.tool()
def speech_gen(
    text: str,
    voice: str = None,
    emotion: str = None,
    speed: float | None = None,
    pitch: int | None = None,
    volume: float | None = None,
) -> ToolResponse:
    """Generates speech audio from text using TTS."""
    provider, api_key, provider_cfg = _get_audio_provider()
    if provider != "wavespeed":
        return ToolResponse(success=False, error=f"Unsupported speech_gen provider: {provider}")

    speech_model = provider_cfg.get("speech_model") or audio_gen_config.get("speech_model", "speech-2.5-turbo-preview")
    default_voice = voice or audio_gen_config.get("default_voice", "Wise_Woman")
    default_emotion = emotion or audio_gen_config.get("default_emotion", "surprised")
    resolved_speed = speed if speed is not None else _float_config("speech_speed", 1.0)
    resolved_pitch = pitch if pitch is not None else int(_float_config("speech_pitch", 0))
    resolved_volume = volume if volume is not None else _float_config("speech_volume", 1.0)
    save_path = _audio_save_path("speech", text, "mp3")

    result = wavespeed_speech_gen(
        api_key=api_key,
        prompt=text,
        voice_id=default_voice,
        emotion=default_emotion,
        model=speech_model,
        provider=provider_cfg.get("speech_provider"),
        base_url=provider_cfg.get("base_url"),
        save_path=save_path,
        speed=resolved_speed,
        pitch=resolved_pitch,
        volume=resolved_volume,
    )

    if result and result.get("success"):
        logger.info(f"Speech generated successfully: {result.get('output_path')}")
        return ToolResponse(success=True, output_path=result.get("output_path", save_path), message="Speech generated successfully.")

    logger.error(f"Speech generation failed: {result.get('error') if isinstance(result, dict) else result}")
    return ToolResponse(success=False, error=(result or {}).get("error", "Unknown error during speech generation."))


@mcp.tool()
def generate_audio_assets_from_plan(
    audio_plan: dict[str, Any],
    video_path: str = None,
    mux_output_path: str = None,
) -> ToolResponse:
    """Generate BGM, SFX, and voiceover assets from an audio plan, optionally muxing them into a video."""
    provider, api_key, provider_cfg = _get_audio_provider()
    if provider != "wavespeed":
        return ToolResponse(success=False, error=f"Unsupported audio_gen provider: {provider}")

    audio_model = provider_cfg.get("audio_model") or audio_gen_config.get("default_model", "mmaudio-v2")
    speech_model = provider_cfg.get("speech_model") or audio_gen_config.get("speech_model", "speech-2.5-turbo-preview")
    guidance_scale = audio_gen_config.get("guidance_scale", 4.5)
    num_inference_steps = audio_gen_config.get("num_inference_steps", 25)

    generated_assets: list[dict[str, Any]] = []
    timeline_events: list[dict[str, Any]] = []

    bgm = audio_plan.get("bgm") or {}
    if bgm.get("enabled") and bgm.get("prompt"):
        save_path = _audio_save_path("bgm", bgm.get("prompt", "bgm"), "mp3")
        result = wavespeed_audio_gen(
            api_key=api_key,
            prompt=bgm["prompt"],
            video_url="",
            model=audio_model,
            provider=provider_cfg.get("audio_provider"),
            base_url=provider_cfg.get("base_url"),
            save_path=save_path,
            duration=_resolve_audio_duration(bgm.get("duration_seconds")),
            guidance_scale=guidance_scale,
            num_inference_steps=num_inference_steps,
        )
        if result and result.get("success"):
            path = result.get("output_path", save_path)
            generated_assets.append({"type": "bgm", "path": path, "prompt": bgm["prompt"]})
            timeline_events.append({
                "role": "bgm",
                "path": path,
                "start_seconds": bgm.get("start_seconds", 0),
                "duration_seconds": bgm.get("duration_seconds"),
                "volume": bgm.get("volume", audio_gen_config.get("bgm_volume", 0.32)),
                "fade_in_seconds": bgm.get("fade_in_seconds", audio_gen_config.get("bgm_fade_in_seconds", 1.0)),
                "fade_out_seconds": bgm.get("fade_out_seconds", audio_gen_config.get("bgm_fade_out_seconds", 1.5)),
            })

    for event in audio_plan.get("sfx_events") or []:
        prompt = event.get("prompt")
        if not prompt:
            continue
        save_path = _audio_save_path("sfx", prompt, "mp3")
        result = wavespeed_audio_gen(
            api_key=api_key,
            prompt=prompt,
            video_url="",
            model=audio_model,
            provider=provider_cfg.get("audio_provider"),
            base_url=provider_cfg.get("base_url"),
            save_path=save_path,
            duration=_resolve_audio_duration(event.get("duration_seconds")),
            guidance_scale=guidance_scale,
            num_inference_steps=num_inference_steps,
        )
        if result and result.get("success"):
            path = result.get("output_path", save_path)
            asset = {"type": "sfx", "id": event.get("id"), "shot_id": event.get("shot_id"), "path": path, "prompt": prompt}
            generated_assets.append(asset)
            timeline_events.append({
                "role": "sfx",
                "path": path,
                "start_seconds": event.get("start_seconds", 0),
                "duration_seconds": event.get("duration_seconds"),
                "volume": event.get("volume", audio_gen_config.get("sfx_default_volume", 0.45)),
                "fade_in_seconds": event.get("fade_in_seconds", 0),
                "fade_out_seconds": event.get("fade_out_seconds", 0.05),
                "note": event.get("reason"),
            })

    for segment in audio_plan.get("voiceover_segments") or []:
        speech_text = segment.get("text")
        if not speech_text:
            continue
        save_path = _audio_save_path("voice", speech_text, "mp3")
        result = wavespeed_speech_gen(
            api_key=api_key,
            prompt=speech_text,
            voice_id=segment.get("voice") or audio_gen_config.get("default_voice", "Wise_Woman"),
            emotion=segment.get("emotion") or audio_gen_config.get("default_emotion", "neutral"),
            model=speech_model,
            provider=provider_cfg.get("speech_provider"),
            base_url=provider_cfg.get("base_url"),
            save_path=save_path,
            speed=segment.get("speed", audio_gen_config.get("speech_speed", 1.0)),
            volume=segment.get("volume", audio_gen_config.get("speech_volume", 1.0)),
            pitch=segment.get("pitch", audio_gen_config.get("speech_pitch", 0)),
        )
        if result and result.get("success"):
            path = result.get("output_path", save_path)
            generated_assets.append({"type": "voiceover", "id": segment.get("id"), "shot_id": segment.get("shot_id"), "path": path, "text": speech_text})
            timeline_events.append({
                "role": "voiceover",
                "path": path,
                "start_seconds": segment.get("start_seconds", 0),
                "duration_seconds": segment.get("duration_seconds"),
                "volume": segment.get("volume", audio_gen_config.get("voiceover_volume", 0.9)),
                "fade_in_seconds": segment.get("fade_in_seconds", 0.02),
                "fade_out_seconds": segment.get("fade_out_seconds", 0.05),
                "note": segment.get("reason"),
            })

    final_output = None
    if video_path and timeline_events:
        final_output = mix_audio_timeline(
            video_path=video_path,
            audio_events=timeline_events,
            output_path=mux_output_path or _audio_save_path("with_audio", "final", "mp4"),
            keep_original_audio=True,
            original_audio_volume=audio_plan.get("mixing", {}).get("original_audio_volume", audio_gen_config.get("original_audio_volume", 0.25)),
            default_event_volume=audio_gen_config.get("sfx_default_volume", 0.45),
        )

    return ToolResponse(
        success=True,
        content={"assets": generated_assets, "timeline_events": timeline_events, "final_output": final_output},
        output_path=final_output,
        message="Audio assets generated from plan." if not final_output else "Audio assets generated and mixed into video.",
    )


@mcp.tool()
def mux_audio_timeline(
    video_path: str,
    audio_events: list[dict[str, Any]],
    output_path: str = None,
    keep_original_audio: bool = True,
    original_audio_volume: float | None = None,
) -> ToolResponse:
    """Mix declarative BGM/SFX/voiceover events onto a video timeline."""
    if output_path is None:
        output_path = _audio_save_path("with_audio", "final", "mp4")
    try:
        mixed_path = mix_audio_timeline(
            video_path=video_path,
            audio_events=audio_events,
            output_path=output_path,
            keep_original_audio=keep_original_audio,
            original_audio_volume=(
                original_audio_volume
                if original_audio_volume is not None
                else _float_config("original_audio_volume", 0.25)
            ),
            default_event_volume=_float_config("sfx_default_volume", 0.45),
        )
    except Exception as exc:
        logger.error(f"Audio timeline mux failed: {exc}")
        return ToolResponse(success=False, error=str(exc))

    return ToolResponse(success=True, output_path=mixed_path, message="Audio timeline mixed into video successfully.")


if __name__ == "__main__":
    mcp.run(transport="stdio")
