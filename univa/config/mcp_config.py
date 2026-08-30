import os
from copy import deepcopy
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[2]
UNIVA_ROOT = PROJECT_ROOT / "univa"
MCP_CONFIG_PATH = UNIVA_ROOT / "config" / "mcp_tools_config" / "config.yaml"
ENV_PATH = PROJECT_ROOT / ".env"


def load_runtime_env() -> None:
    """Load the real runtime .env file. Never load .env.example."""
    if ENV_PATH.exists():
        load_dotenv(dotenv_path=ENV_PATH, override=False)


def _env(name: str) -> str | None:
    value = os.getenv(name)
    if value is None:
        return None
    value = value.strip()
    return value if value else None


def _set_path(config: dict[str, Any], path: tuple[str, ...], value: Any) -> None:
    if value is None:
        return
    cursor = config
    for key in path[:-1]:
        cursor = cursor.setdefault(key, {})
    cursor[path[-1]] = value


def _get_path(config: dict[str, Any], path: tuple[str, ...]) -> Any:
    cursor: Any = config
    for key in path:
        if not isinstance(cursor, dict) or key not in cursor:
            return None
        cursor = cursor[key]
    return cursor


def _coerce_env_value(value: str, reference: Any) -> Any:
    if isinstance(reference, bool):
        lowered = value.strip().lower()
        if lowered in {"1", "true", "yes", "on"}:
            return True
        if lowered in {"0", "false", "no", "off"}:
            return False
        return reference

    if isinstance(reference, int) and not isinstance(reference, bool):
        try:
            return int(value)
        except ValueError:
            return reference

    if isinstance(reference, float):
        try:
            return float(value)
        except ValueError:
            return reference

    return value


def _copy_key(config: dict[str, Any], env_name: str, path: tuple[str, ...]) -> None:
    value = _env(env_name)
    if value is None:
        return
    _set_path(config, path, _coerce_env_value(value, _get_path(config, path)))


def _mirror_provider_key(config: dict[str, Any], env_name: str, sections: list[str]) -> None:
    value = _env(env_name)
    if not value:
        return
    for section in sections:
        _set_path(config, (section, "provider"), value)


def _mirror_wavespeed_key(config: dict[str, Any]) -> None:
    api_key = _env("WAVESPEED_API_KEY")
    if not api_key:
        return
    for section in ("image_gen", "video_gen", "video_editing", "audio_gen"):
        _set_path(config, (section, "wavespeed_api"), api_key)
        _set_path(config, (section, "wavespeed", "api_key"), api_key)


def _mirror_ark_key(config: dict[str, Any]) -> None:
    api_key = _env("ARK_API_KEY")
    if not api_key:
        return
    for section in ("image_gen", "video_gen", "video_editing"):
        _set_path(config, (section, "volcengine_ark", "api_key"), api_key)


def _mirror_ark_base_url(config: dict[str, Any]) -> None:
    base_url = _env("ARK_BASE_URL")
    if not base_url:
        return
    for section in ("image_gen", "video_gen", "video_editing"):
        _set_path(config, (section, "volcengine_ark", "base_url"), base_url)


def _apply_env_overrides(config: dict[str, Any]) -> dict[str, Any]:
    config = deepcopy(config)

    _mirror_wavespeed_key(config)
    _mirror_ark_key(config)
    _mirror_ark_base_url(config)

    _mirror_provider_key(config, "IMAGE_GEN_PROVIDER", ["image_gen"])
    _mirror_provider_key(config, "VIDEO_GEN_PROVIDER", ["video_gen"])
    _mirror_provider_key(config, "VIDEO_EDITING_PROVIDER", ["video_editing"])
    _mirror_provider_key(config, "AUDIO_GEN_PROVIDER", ["audio_gen"])

    for section in ("image_gen", "video_gen", "video_editing", "audio_gen"):
        _copy_key(config, "WAVESPEED_BASE_URL", (section, "wavespeed", "base_url"))

    _copy_key(config, "ARK_IMAGE_BASE_URL", ("image_gen", "volcengine_ark", "base_url"))
    _copy_key(config, "ARK_VIDEO_BASE_URL", ("video_gen", "volcengine_ark", "base_url"))
    _copy_key(config, "ARK_VIDEO_EDITING_BASE_URL", ("video_editing", "volcengine_ark", "base_url"))

    _copy_key(config, "IMAGE_BASE_OUTPUT_PATH", ("image_gen", "base_output_path"))
    _copy_key(config, "VIDEO_BASE_OUTPUT_PATH", ("video_gen", "base_output_path"))
    _copy_key(config, "AUDIO_BASE_OUTPUT_PATH", ("audio_gen", "base_output_path"))

    _copy_key(config, "ARK_TEXT_TO_IMAGE_MODEL", ("image_gen", "volcengine_ark", "text_to_image_model"))
    _copy_key(config, "ARK_IMAGE_TO_IMAGE_MODEL", ("image_gen", "volcengine_ark", "image_to_image_model"))
    _copy_key(config, "ARK_TEXT_TO_VIDEO_MODEL", ("video_gen", "volcengine_ark", "text_to_video_model"))
    _copy_key(config, "ARK_IMAGE_TO_VIDEO_MODEL", ("video_gen", "volcengine_ark", "image_to_video_model"))
    _copy_key(config, "ARK_STYLE_TRANSFER_MODEL", ("video_editing", "volcengine_ark", "style_transfer_model"))
    _copy_key(config, "ARK_REPAINTING_MODEL", ("video_editing", "volcengine_ark", "repainting_model"))

    _copy_key(config, "WAVESPEED_TEXT_TO_IMAGE_PROVIDER", ("image_gen", "wavespeed", "text_to_image_provider"))
    _copy_key(config, "WAVESPEED_TEXT_TO_IMAGE_MODEL", ("image_gen", "wavespeed", "text_to_image_model"))
    _copy_key(config, "WAVESPEED_IMAGE_TO_IMAGE_PROVIDER", ("image_gen", "wavespeed", "image_to_image_provider"))
    _copy_key(config, "WAVESPEED_IMAGE_TO_IMAGE_MODEL", ("image_gen", "wavespeed", "image_to_image_model"))
    _copy_key(config, "WAVESPEED_SEQUENTIAL_IMAGE_PROVIDER", ("image_gen", "wavespeed", "sequential_image_provider"))
    _copy_key(config, "WAVESPEED_SEQUENTIAL_IMAGE_MODEL", ("image_gen", "wavespeed", "sequential_image_model"))

    _copy_key(config, "WAVESPEED_TEXT_TO_VIDEO_PROVIDER", ("video_gen", "wavespeed", "text_to_video_provider"))
    _copy_key(config, "WAVESPEED_TEXT_TO_VIDEO_MODEL", ("video_gen", "wavespeed", "text_to_video_model"))
    _copy_key(config, "WAVESPEED_IMAGE_TO_VIDEO_PROVIDER", ("video_gen", "wavespeed", "image_to_video_provider"))
    _copy_key(config, "WAVESPEED_IMAGE_TO_VIDEO_MODEL", ("video_gen", "wavespeed", "image_to_video_model"))
    _copy_key(config, "WAVESPEED_FRAME_TO_FRAME_PROVIDER", ("video_gen", "wavespeed", "frame_to_frame_provider"))
    _copy_key(config, "WAVESPEED_FRAME_TO_FRAME_MODEL", ("video_gen", "wavespeed", "frame_to_frame_model"))
    _copy_key(config, "VIDEO_MIN_DURATION_SECONDS", ("video_gen", "min_duration_seconds"))
    _copy_key(config, "VIDEO_MAX_DURATION_SECONDS", ("video_gen", "max_duration_seconds"))
    _copy_key(config, "VIDEO_DEFAULT_ASPECT_RATIO", ("video_gen", "default_aspect_ratio"))
    _copy_key(config, "VIDEO_AUTO_AUDIO", ("video_gen", "auto_audio"))
    _copy_key(config, "VIDEO_AUTO_AUDIO_INCLUDE_BGM", ("video_gen", "auto_audio_include_bgm"))
    _copy_key(config, "VIDEO_AUTO_AUDIO_INCLUDE_SFX", ("video_gen", "auto_audio_include_sfx"))
    _copy_key(config, "VIDEO_AUTO_AUDIO_INCLUDE_VOICEOVER", ("video_gen", "auto_audio_include_voiceover"))
    _copy_key(config, "VIDEO_MERGE_TRANSITION", ("video_gen", "merge", "transition"))
    _copy_key(config, "VIDEO_MERGE_TRANSITION_DURATION_SECONDS", ("video_gen", "merge", "transition_duration_seconds"))
    _copy_key(config, "VIDEO_MERGE_OUTPUT_SIZE", ("video_gen", "merge", "output_size"))

    _copy_key(config, "WAVESPEED_AUDIO_PROVIDER", ("audio_gen", "wavespeed", "audio_provider"))
    _copy_key(config, "WAVESPEED_AUDIO_MODEL", ("audio_gen", "wavespeed", "audio_model"))
    _copy_key(config, "WAVESPEED_SPEECH_PROVIDER", ("audio_gen", "wavespeed", "speech_provider"))
    _copy_key(config, "WAVESPEED_SPEECH_MODEL", ("audio_gen", "wavespeed", "speech_model"))
    _copy_key(config, "AUDIO_DEFAULT_DURATION_SECONDS", ("audio_gen", "duration"))
    _copy_key(config, "AUDIO_BGM_VOLUME", ("audio_gen", "bgm_volume"))
    _copy_key(config, "AUDIO_BGM_FADE_IN_SECONDS", ("audio_gen", "bgm_fade_in_seconds"))
    _copy_key(config, "AUDIO_BGM_FADE_OUT_SECONDS", ("audio_gen", "bgm_fade_out_seconds"))
    _copy_key(config, "AUDIO_SFX_DEFAULT_VOLUME", ("audio_gen", "sfx_default_volume"))
    _copy_key(config, "AUDIO_VOICEOVER_VOLUME", ("audio_gen", "voiceover_volume"))
    _copy_key(config, "AUDIO_ORIGINAL_VOLUME", ("audio_gen", "original_audio_volume"))
    _copy_key(config, "SPEECH_SPEED", ("audio_gen", "speech_speed"))
    _copy_key(config, "SPEECH_PITCH", ("audio_gen", "speech_pitch"))
    _copy_key(config, "SPEECH_VOLUME", ("audio_gen", "speech_volume"))

    _copy_key(config, "WAVESPEED_VIDEO_EDIT_PROVIDER", ("video_editing", "wavespeed", "style_transfer_provider"))
    _copy_key(config, "WAVESPEED_VIDEO_EDIT_MODEL", ("video_editing", "wavespeed", "style_transfer_model"))
    _copy_key(config, "WAVESPEED_REPAINTING_PROVIDER", ("video_editing", "wavespeed", "repainting_provider"))
    _copy_key(config, "WAVESPEED_REPAINTING_MODEL", ("video_editing", "wavespeed", "repainting_model"))
    _copy_key(config, "WAVESPEED_POSE_PROVIDER", ("video_editing", "wavespeed", "pose_provider"))
    _copy_key(config, "WAVESPEED_POSE_MODEL", ("video_editing", "wavespeed", "pose_model"))

    _copy_key(config, "VIDEO_EDIT_MODEL_PATH", ("video_editing", "model_path"))
    _copy_key(config, "VACE_PYTHON", ("video_editing", "local_vace", "python"))
    _copy_key(config, "VACE_WORKDIR", ("video_editing", "local_vace", "workdir"))
    _copy_key(config, "VACE_TEMP_DIR", ("video_editing", "local_vace", "temp_dir"))
    _copy_key(config, "VACE_RESULTS_DIR", ("video_editing", "local_vace", "results_dir"))

    _copy_key(config, "VIDEO_UNDERSTAND_MODEL_PATH", ("video_understanding", "model_path"))
    _copy_key(config, "VIDEO_RETRIEVER_MODEL_PATH", ("video_understanding", "retriever_model_path"))
    _copy_key(config, "VIDEO_TRACK_SA2VA_PATH", ("video_tracking", "sa2va_model_path"))
    _copy_key(config, "VIDEO_TRACK_SAM_PATH", ("video_tracking", "sam_model_path"))
    _copy_key(config, "VIDEO_TRACK_CUDA_VISIBLE_DEVICES", ("video_tracking", "cuda_visible_devices"))

    _copy_key(config, "LLM_MODEL", ("llm", "model"))
    _copy_key(config, "LLM_OPENAI_API_KEY", ("llm", "openai_api_key"))
    _copy_key(config, "LLM_BASE_URL", ("llm", "base_url"))

    _copy_key(config, "IMAGE_UPLOAD_URL", ("image_upload", "url"))
    _copy_key(config, "IMAGE_UPLOAD_API_KEY", ("image_upload", "api_key"))
    _copy_key(config, "IMAGE_UPLOAD_MODEL", ("image_upload", "model"))
    _copy_key(config, "IMAGE_UPLOAD_FILE_TYPE", ("image_upload", "file_type"))
    _copy_key(config, "IMAGE_UPLOAD_FILENAME", ("image_upload", "filename"))
    _copy_key(config, "IMAGE_UPLOAD_MIME_TYPE", ("image_upload", "mime_type"))
    _copy_key(config, "IMAGE_UPLOAD_ORIGIN", ("image_upload", "origin"))
    _copy_key(config, "IMAGE_UPLOAD_REFERER", ("image_upload", "referer"))
    _copy_key(config, "IMAGE_UPLOAD_USER_AGENT", ("image_upload", "user_agent"))

    _copy_key(config, "VIDEO_UPLOAD_PROVIDER", ("video_upload", "provider"))
    _copy_key(config, "VIDEO_UPLOAD_LOCAL_PORT", ("video_upload", "local_port"))
    _copy_key(config, "VIDEO_UPLOAD_VERIFY_URL", ("video_upload", "verify_url"))
    _copy_key(config, "VIDEO_UPLOAD_READY_DELAY_SECONDS", ("video_upload", "ready_delay_seconds"))
    _copy_key(config, "VIDEO_UPLOAD_TUNNEL_START_ATTEMPTS", ("video_upload", "tunnel_start_attempts"))
    _copy_key(config, "VIDEO_UPLOAD_CLOUDFLARED_BIN", ("video_upload", "cloudflared_bin"))
    _copy_key(config, "VIDEO_UPLOAD_URL", ("video_upload", "url"))
    _copy_key(config, "VIDEO_UPLOAD_API_KEY", ("video_upload", "api_key"))
    _copy_key(config, "VIDEO_UPLOAD_MODEL", ("video_upload", "model"))
    _copy_key(config, "VIDEO_UPLOAD_FILE_TYPE", ("video_upload", "file_type"))
    _copy_key(config, "VIDEO_UPLOAD_FILENAME", ("video_upload", "filename"))
    _copy_key(config, "VIDEO_UPLOAD_MIME_TYPE", ("video_upload", "mime_type"))
    _copy_key(config, "VIDEO_UPLOAD_ORIGIN", ("video_upload", "origin"))
    _copy_key(config, "VIDEO_UPLOAD_REFERER", ("video_upload", "referer"))
    _copy_key(config, "VIDEO_UPLOAD_USER_AGENT", ("video_upload", "user_agent"))

    return config


def load_mcp_config() -> dict[str, Any]:
    load_runtime_env()
    if not MCP_CONFIG_PATH.exists():
        return {}
    with MCP_CONFIG_PATH.open("r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}
    return _apply_env_overrides(raw)


def get_mcp_section(section: str) -> dict[str, Any]:
    return load_mcp_config().get(section, {})


def get_wavespeed_config(section_config: dict[str, Any]) -> dict[str, Any]:
    wavespeed = dict(section_config.get("wavespeed") or {})
    if section_config.get("wavespeed_api") and not wavespeed.get("api_key"):
        wavespeed["api_key"] = section_config.get("wavespeed_api")
    return wavespeed
