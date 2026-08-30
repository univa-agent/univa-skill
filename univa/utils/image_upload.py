import json
import logging
import mimetypes
import os

import requests

from univa.config.mcp_config import get_mcp_section


logger = logging.getLogger(__name__)


def _uploaded_url_from_payload(payload):
    if not isinstance(payload, dict):
        return None
    for key in ("fileUrl", "file_url", "url", "downloadUrl", "download_url"):
        value = payload.get(key)
        if isinstance(value, str) and value:
            return value
    data = payload.get("data")
    if isinstance(data, dict):
        for key in ("fileUrl", "file_url", "url", "downloadUrl", "download_url"):
            value = data.get(key)
            if isinstance(value, str) and value:
                return value
    return None


def _upload_config(config_section):
    upload_config = get_mcp_section(config_section)
    if config_section != "image_upload" and not (upload_config.get("url") and upload_config.get("api_key")):
        fallback = get_mcp_section("image_upload")
        if fallback.get("url") and fallback.get("api_key"):
            logger.info("%s is not fully configured; falling back to image_upload", config_section)
            return fallback, "image_upload"
    return upload_config, config_section


def upload_file(file_path, *, filename=None, mime_type=None, file_type=None, config_section="image_upload"):
    """Upload a local asset and return a web URL usable by remote media APIs.

    ``image_upload`` is retained for backward compatibility.  New video callers
    should pass ``config_section="video_upload"`` so deployments can use a
    dedicated video-capable upload endpoint while still falling back to legacy
    image_upload settings when no video-specific endpoint is configured.
    """
    upload_config, resolved_section = _upload_config(config_section)
    url = upload_config.get("url")
    api_key = upload_config.get("api_key")
    if not url or not api_key:
        raise RuntimeError(
            f"upload_file requires {config_section}.url and {config_section}.api_key "
            "in .env or config.yaml so local media can be exposed as a web URL"
        )

    if not os.path.exists(file_path):
        raise FileNotFoundError(file_path)

    resolved_filename = filename or os.path.basename(file_path) or upload_config.get("filename", "upload.bin")
    guessed_mime, _ = mimetypes.guess_type(file_path)
    resolved_mime = mime_type or guessed_mime or upload_config.get("mime_type") or "application/octet-stream"

    params = {"fileType": file_type or upload_config.get("file_type", "file")}
    origin = upload_config.get("origin", "")
    referer = upload_config.get("referer", origin)

    headers = {
        "Accept": "application/json",
        "Accept-Language": upload_config.get("accept_language", "zh-CN,zh;q=0.9,zh-TW;q=0.8"),
        "Authorization": f"Bearer {api_key}",
        "model": upload_config.get("model", ""),
        "User-Agent": upload_config.get("user_agent", "UniVA/1.0"),
    }
    if origin:
        headers["Origin"] = origin
    if referer:
        headers["Referer"] = referer

    with open(file_path, "rb") as f:
        files = {"file": (resolved_filename, f, resolved_mime)}
        response = requests.post(url, params=params, headers=headers, files=files, timeout=120)

    try:
        response.raise_for_status()
    except requests.exceptions.HTTPError as exc:
        body = (response.text or "")[:500]
        raise RuntimeError(
            f"{resolved_section} upload failed with HTTP {response.status_code}: {body}"
        ) from exc
    try:
        payload = response.json()
    except requests.exceptions.JSONDecodeError:
        logger.info("upload response content: %s", response.text[:500])
        payload = json.loads(response.text)

    uploaded_url = _uploaded_url_from_payload(payload)
    if not uploaded_url:
        raise RuntimeError("upload response did not include a file URL")

    logger.info("uploaded %s via %s as %s (%s)", file_path, resolved_section, resolved_filename, resolved_mime)
    return uploaded_url


def image_upload(file_path):
    """Backward-compatible wrapper for existing image upload callers."""
    upload_config = get_mcp_section("image_upload")
    return upload_file(
        file_path,
        filename=upload_config.get("filename") or None,
        mime_type=upload_config.get("mime_type") or None,
        file_type=upload_config.get("file_type") or None,
    )
