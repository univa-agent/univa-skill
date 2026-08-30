"""
Volcengine Ark API wrapper for video generation (Seedance).

Provides the same function signatures as wavespeed_api.py so MCP tools
can swap providers by changing a single config key.

Key design: file-based task state persistence prevents duplicate tasks
when the agent framework retries a tool call after a timeout.  If a task
is already running, subsequent calls will *resume polling the same task*
instead of creating a new one.

API flow for Volcengine Ark content generation:
  1. POST {base_url}/contents/generations/tasks  ->  task_id
  2. GET  {base_url}/contents/generations/tasks/{task_id}  (poll)
  3. Download video from result URL, save to disk

Reference: https://www.volcengine.com/docs/82379/1520757
"""

import base64
import contextlib
import functools
import hashlib
import http.server
import json
import logging
import os
from pathlib import Path
import re
import selectors
import shutil
import socketserver
import subprocess
import tempfile
import threading
import time
from datetime import datetime
from urllib.parse import quote, urlparse

import requests

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger()


def _ark_base_url(base_url: str | None = None) -> str:
    return (base_url or os.getenv("ARK_BASE_URL") or "https://ark.cn-beijing.volces.com/api/v3").rstrip("/")

# ---------------------------------------------------------------------------
# File-based task state — survives agent retries / MCP process restarts
# ---------------------------------------------------------------------------

_PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _state_dir() -> str:
    configured = os.getenv("UNIVA_CACHE_DIR")
    if configured:
        path = Path(os.path.expandvars(os.path.expanduser(configured)))
        if not path.is_absolute():
            path = _PROJECT_ROOT / path
        return str(path)
    return str(_PROJECT_ROOT / "results" / "cache" / "univa")


def _state_file() -> str:
    return os.path.join(_state_dir(), "ark_video_task.json")


def _read_state() -> dict | None:
    """Read persisted task state. Returns None if no task is running."""
    try:
        state_file = _state_file()
        if os.path.exists(state_file):
            with open(state_file, "r") as f:
                return json.load(f)
    except Exception:
        pass
    return None


def _write_state(state: dict) -> None:
    """Persist task state to disk."""
    state_dir = _state_dir()
    os.makedirs(state_dir, exist_ok=True)
    with open(_state_file(), "w") as f:
        json.dump(state, f)


def _clear_state() -> None:
    """Remove persisted task state (task completed or failed)."""
    try:
        state_file = _state_file()
        if os.path.exists(state_file):
            os.remove(state_file)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _cancel_task(base_url: str, api_key: str, task_id: str) -> bool:
    """Cancel a running content generation task. Returns True on success."""
    url = f"{base_url.rstrip('/')}/contents/generations/tasks/{task_id}"
    headers = {"Authorization": f"Bearer {api_key}"}
    try:
        response = requests.delete(url, headers=headers)
        if response.status_code in (200, 204):
            logger.info(f"Task {task_id} cancelled successfully.")
            return True
        else:
            logger.warning(
                f"Failed to cancel task {task_id}: HTTP {response.status_code}"
            )
            return False
    except Exception as e:
        logger.warning(f"Error cancelling task {task_id}: {e}")
        return False


def _submit_generation(
    base_url: str,
    api_key: str,
    payload: dict,
) -> tuple[str | None, dict | None]:
    """Submit a content generation task.

    Returns (task_id, error_details). error_details is safe to surface in
    result artifacts; it never contains the API key or request headers.
    Network errors (DNS, connection) are retried up to 3 times.
    """
    url = f"{base_url.rstrip('/')}/contents/generations/tasks"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }

    last_network_error: str | None = None
    for attempt in range(3):
        try:
            begin = time.time()
            response = requests.post(
                url, headers=headers, data=json.dumps(payload), timeout=30
            )

            if response.status_code == 200:
                data = response.json()
                task_id = data.get("id") or data.get("task_id")
                if not task_id:
                    return None, _submission_error(
                        "missing_task_id",
                        "Ark submission succeeded but no task id was returned.",
                        http_status=response.status_code,
                        response_text=response.text,
                        endpoint=url,
                    )
                logger.info(
                    f"Task submitted successfully. Task ID: {task_id} "
                    f"(elapsed {time.time() - begin:.1f}s)"
                )
                return task_id, None
            else:
                logger.error(
                    f"Submission failed: HTTP {response.status_code}, "
                    f"body: {response.text[:300]}"
                )
                return None, _submission_error(
                    "http_error",
                    "Ark submission failed.",
                    http_status=response.status_code,
                    response_text=response.text,
                    endpoint=url,
                )

        except (requests.exceptions.ConnectionError,
                requests.exceptions.Timeout) as e:
            last_network_error = str(e)
            logger.warning(
                f"Network error submitting task (attempt {attempt + 1}/3): {e}"
            )
            if attempt < 2:
                time.sleep(2.0)

    logger.error("Submission failed after 3 network retries")
    return None, _submission_error(
        "network_error",
        "Ark submission failed after 3 network retries.",
        network_error=last_network_error,
        endpoint=url,
    )


def _submission_error(
    reason: str,
    message: str,
    http_status: int | None = None,
    response_text: str | None = None,
    network_error: str | None = None,
    endpoint: str | None = None,
) -> dict:
    error: dict = {
        "provider": "volcengine_ark",
        "stage": "submit_generation",
        "reason": reason,
        "message": message,
    }
    if endpoint:
        error["endpoint"] = endpoint
    if http_status is not None:
        error["http_status"] = http_status
    if network_error:
        error["network_error"] = network_error[:500]

    parsed = None
    if response_text:
        error["response_body"] = response_text[:1000]
        try:
            parsed = json.loads(response_text)
        except (TypeError, ValueError):
            parsed = None

    provider_error = parsed.get("error") if isinstance(parsed, dict) else None
    if isinstance(provider_error, dict):
        error["provider_code"] = provider_error.get("code")
        error["provider_message"] = provider_error.get("message")
        error["provider_type"] = provider_error.get("type")
        error["provider_param"] = provider_error.get("param")
    elif isinstance(parsed, dict):
        for key in ("code", "message", "type", "request_id"):
            if key in parsed:
                error[f"provider_{key}"] = parsed.get(key)
    return error


def _submission_error_text(prefix: str, details: dict | None) -> str:
    if not details:
        return prefix
    parts = [prefix]
    if details.get("http_status") is not None:
        parts.append(f"HTTP {details['http_status']}")
    provider_code = details.get("provider_code")
    provider_type = details.get("provider_type")
    provider_message = details.get("provider_message")
    if provider_code:
        parts.append(str(provider_code))
    if provider_type:
        parts.append(str(provider_type))
    if provider_message:
        parts.append(str(provider_message))
    elif details.get("network_error"):
        parts.append(str(details["network_error"]))
    return ": ".join(parts)


def _poll_generation(
    base_url: str,
    api_key: str,
    task_id: str,
    max_wait: int = 600,
    poll_interval: float = 3.0,
) -> dict | None:
    """
    Poll a content generation task until completion or timeout.
    Returns the full result data dict on success, None on timeout.

    Network errors (DNS, connection, timeout) are retried with exponential
    backoff — they slow down polling but never abort the loop on their own.
    Only ``max_wait`` (total wall-clock time) can terminate polling.

    The returned dict always contains a ``status`` key from the server.
    When the task itself failed (status = failed/error/cancelled/expired),
    the dict will have ``_task_failed: True`` set so callers can distinguish
    a server-side failure from a client-side timeout.
    """
    url = f"{base_url.rstrip('/')}/contents/generations/tasks/{task_id}"
    headers = {"Authorization": f"Bearer {api_key}"}

    begin = time.time()
    consecutive_failures = 0
    current_interval = poll_interval

    while True:
        elapsed = time.time() - begin
        if elapsed > max_wait:
            logger.error(
                f"Task {task_id} timed out after {max_wait:.0f}s "
                f"(elapsed {elapsed:.1f}s)"
            )
            return None

        try:
            response = requests.get(url, headers=headers, timeout=30)
        except (requests.exceptions.ConnectionError,
                requests.exceptions.Timeout) as e:
            consecutive_failures += 1
            # Exponential backoff: base → base*2 → base*4 → ... capped at 30s
            current_interval = min(
                poll_interval * (2 ** (consecutive_failures - 1)), 30.0
            )
            logger.warning(
                f"Network error polling task {task_id} "
                f"(consecutive failure #{consecutive_failures}, "
                f"elapsed {elapsed:.1f}s/{max_wait:.0f}s): {e}. "
                f"Retrying in {current_interval:.1f}s"
            )
            time.sleep(current_interval)
            continue

        # Successful connection — reset backoff
        consecutive_failures = 0
        current_interval = poll_interval

        if response.status_code != 200:
            logger.error(
                f"Poll failed: HTTP {response.status_code}, "
                f"body: {response.text[:200]}"
            )
            time.sleep(current_interval)
            continue

        data = response.json()
        status = data.get("status", "").lower()

        if status in ("succeeded", "completed", "done"):
            logger.info(f"Task {task_id} completed in {elapsed:.1f}s")
            return data
        elif status in ("failed", "error", "cancelled", "expired"):
            error_msg = data.get("error") or data.get("message") or "Unknown error"
            logger.error(f"Task {task_id} failed: {error_msg}")
            # Mark as server-side task failure so callers can distinguish
            # from a client-side timeout (None).
            data["_task_failed"] = True
            return data
        else:
            # Status: queued / running
            logger.info(
                f"Task {task_id} status: {status} (elapsed {elapsed:.1f}s)"
            )

        time.sleep(current_interval)


def _download_video(url: str, save_path: str) -> bool:
    """Download generated video from url to save_path. Returns True on success."""
    try:
        resp = requests.get(url, stream=True)
        resp.raise_for_status()
        os.makedirs(os.path.dirname(save_path) or ".", exist_ok=True)
        with open(save_path, "wb") as f:
            for chunk in resp.iter_content(8192):
                f.write(chunk)
        logger.info(f"Video saved to: {save_path}")
        return True
    except Exception as e:
        logger.error(f"Download failed: {e}")
        return False


def _build_result(
    success: bool,
    output_path: str | None = None,
    message: str | None = None,
    error: str | None = None,
    details: dict | None = None,
) -> dict:
    """Build a standardized return dict (same shape as wavespeed_api)."""
    if success:
        result = {
            "success": True,
            "output_path": output_path,
            "message": message or "Video generated successfully.",
        }
        if details:
            result.update(details)
        return result
    else:
        result = {
            "success": False,
            "error": error or "Unknown error during video generation.",
        }
        if details:
            result.update(details)
        return result


def _extract_video_url(result: dict) -> str | None:
    """
    Extract video URL from a completed task result.
    Volcengine Ark returns: {"content": {"video_url": "https://..."}}
    """
    content = result.get("content", {})
    if isinstance(content, dict):
        video_url = content.get("video_url")
        if video_url:
            return video_url
    # Fallback: try top-level outputs
    outputs = result.get("outputs") or result.get("output") or []
    if isinstance(outputs, str):
        return outputs
    elif isinstance(outputs, list) and len(outputs) > 0:
        return outputs[0]
    elif isinstance(outputs, dict):
        return outputs.get("video_url") or outputs.get("url")
    return None


# ---------------------------------------------------------------------------
# Unified generate-or-resume flow
# ---------------------------------------------------------------------------


# Maximum age (seconds) for a persisted task state before it is considered
# stale and a new task is submitted instead of resuming the old one.
_STALE_STATE_MAX_AGE = 900  # 15 minutes


def _generate_or_resume(
    api_key: str,
    prompt: str,
    image: str | None,
    save_path: str | None,
    model: str,
    base_url: str,
    duration: int | None,
    aspect_ratio: str = "16:9",
) -> dict:
    """
    Core logic shared by t2v and i2v.

    If a task is already running (state file exists *and* is younger than
    ``_STALE_STATE_MAX_AGE``), resume polling it.  Otherwise submit a new
    task, persist state, and poll.

    State file lifecycle
    --------------------
    - **submitted** → written to disk immediately after the API returns a
      ``task_id``.
    - **server-side failure** → cleared (task is definitively dead).
    - **client-side timeout** (DNS flaky / network down for extended period)
      → *preserved* so a subsequent call can resume polling.  The task may
      have completed on the server in the meantime.
    - **success** → cleared after the video is downloaded locally.
    - **stale** (> 15 min since submission) → treated as expired; a new
      task is created.
    """
    request_fingerprint = hashlib.sha256(
        json.dumps(
            {
                "base_url": base_url,
                "model": model,
                "prompt": prompt,
                "image_path": os.path.abspath(image) if image else None,
                "duration": duration,
                "aspect_ratio": aspect_ratio,
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    # --- Check for existing task first ---
    existing = _read_state()
    if existing and existing.get("request_sha256") != request_fingerprint:
        logger.warning(
            "Ignoring persisted Ark task because it belongs to a different generation prompt or parameter set."
        )
        existing = None
    if existing:
        task_id = existing.get("task_id")
        submitted_at = existing.get("submitted_at", "")
        is_stale = False
        if submitted_at:
            try:
                submitted_ts = datetime.fromisoformat(submitted_at)
                age = (datetime.now() - submitted_ts).total_seconds()
                if age > _STALE_STATE_MAX_AGE:
                    logger.warning(
                        f"Existing task {task_id} is {age:.0f}s old "
                        f"(> {_STALE_STATE_MAX_AGE}s), treating as stale — "
                        f"will submit a new task"
                    )
                    is_stale = True
            except (ValueError, TypeError):
                pass

        if is_stale:
            # Clean up stale state before submitting a new task
            _clear_state()
            logger.info(
                f"Cleared stale state for task {task_id} — will submit new task"
            )
        else:
            logger.info(
                f"Found existing task {task_id} — resuming poll "
                f"(agent retry detected, no new task created)"
            )
            # Continue polling the existing task
            result = _poll_generation(base_url, api_key, task_id)

            # --- Timeout: task may still be running on server, preserve state ---
            if result is None:
                logger.warning(
                    f"Polling for task {task_id} timed out (network unstable?). "
                    f"State file preserved — a future call can resume polling."
                )
                return _build_result(
                    False,
                    error=(
                        f"Task {task_id} polling timed out due to network "
                        f"instability. The task may still be running on the "
                        f"server — retrying the request will resume polling."
                    ),
                )

            # --- Server-side task failure: clear state, task is dead ---
            if result.get("_task_failed"):
                error_msg = result.get("error") or "Unknown error"
                _clear_state()
                return _build_result(
                    False,
                    error=f"Task {task_id} failed on server: {error_msg}",
                )

            # --- Success: download + clear ---
            video_url = _extract_video_url(result)
            if not video_url:
                _clear_state()
                return _build_result(
                    False, error="No video_url in completed task result."
                )

            output_filename = os.path.abspath(
                save_path if save_path
                else f"results/{datetime.now().strftime('%m%d%H%M%S')}_video.mp4"
            )
            if not _download_video(video_url, output_filename):
                _clear_state()
                return _build_result(
                    False, error="Failed to download generated video."
                )

            _clear_state()
            return _build_result(True, output_path=output_filename)

    # --- No existing (or stale) task: submit new one ---

    # Build payload
    seed = int(datetime.now().timestamp())
    content = [{"type": "text", "text": prompt}]

    if image:
        # Encode image to base64 data URI
        with open(image, "rb") as f:
            img_bytes = f.read()
        b64 = base64.b64encode(img_bytes).decode("utf-8")
        ext = os.path.splitext(image)[1].lower()
        mime = "jpeg" if ext in (".jpg", ".jpeg") else ext.lstrip(".")
        image_data_uri = f"data:image/{mime};base64,{b64}"
        content.append({"type": "image_url", "image_url": {"url": image_data_uri}})

    payload: dict = {
        "model": model,
        "content": content,
        "seed": seed,
    }
    if duration is not None:
        payload["duration"] = duration

    # Only add ratio for t2v (not needed for i2v)
    if not image:
        payload["ratio"] = aspect_ratio

    # 1. Submit
    task_id, submit_error = _submit_generation(base_url, api_key, payload)
    if not task_id:
        return _build_result(
            False,
            error=_submission_error_text("Failed to submit video generation task", submit_error),
            details={"provider_error": submit_error} if submit_error else None,
        )

    # Persist state so retries resume this task
    _write_state({
        "task_id": task_id,
        "base_url": base_url,
        "api_key": api_key,
        "request_sha256": request_fingerprint,
        "submitted_at": datetime.now().isoformat(),
    })
    logger.info(f"Task {task_id} state persisted to {_state_file()}")

    # 2. Poll
    result = _poll_generation(base_url, api_key, task_id)

    # --- Timeout: preserve state so future calls can resume ---
    if result is None:
        logger.warning(
            f"Polling for task {task_id} timed out (network unstable?). "
            f"State file preserved at {_state_file()} — "
            f"a future call with the same parameters will resume polling."
        )
        return _build_result(
            False,
            error=(
                f"Task {task_id} polling timed out due to network "
                f"instability. The task may still be running on the "
                f"server — retrying the request will resume polling."
            ),
        )

    # --- Server-side task failure ---
    if result.get("_task_failed"):
        error_msg = result.get("error") or "Unknown error"
        _clear_state()
        return _build_result(
            False,
            error=f"Task {task_id} failed on server: {error_msg}",
        )

    # 3. Extract output URL
    video_url = _extract_video_url(result)
    if not video_url:
        _clear_state()
        return _build_result(False, error="No video_url in completed task result.")

    # 4. Download
    time_ft = datetime.now().strftime("%m%d%H%M%S")
    url_name = video_url.split("/")[-1].split("?")[0] or "video.mp4"
    output_filename = os.path.abspath(
        save_path if save_path else f"results/{time_ft}_{url_name}"
    )

    if not _download_video(video_url, output_filename):
        _clear_state()
        return _build_result(False, error="Failed to download generated video.")

    _clear_state()
    return _build_result(True, output_path=output_filename)


# ---------------------------------------------------------------------------
# Public API — mirror wavespeed_api.py function signatures
# ---------------------------------------------------------------------------


def text_to_video_generate(
    api_key: str,
    prompt: str,
    save_path: str = None,
    model: str = "doubao-seedance-2-0-260128",
    base_url: str = "https://ark.cn-beijing.volces.com/api/v3",
    duration: int | None = None,
    aspect_ratio: str = "16:9",
) -> dict:
    """
    Generate a video from a text prompt using Volcengine Ark Seedance.

    Safe for agent retries: if called again while a task is running, it will
    resume polling the existing task instead of creating a duplicate.
    """
    model = model or "doubao-seedance-2-0-260128"
    base_url = _ark_base_url(base_url)
    return _generate_or_resume(
        api_key=api_key,
        prompt=prompt,
        image=None,
        save_path=save_path,
        model=model,
        base_url=base_url,
        duration=duration,
        aspect_ratio=aspect_ratio,
    )


def image_to_video_generate(
    api_key: str,
    prompt: str,
    image: str,
    save_path: str = None,
    model: str = "doubao-seedance-2-0-260128",
    base_url: str = "https://ark.cn-beijing.volces.com/api/v3",
    duration: int | None = None,
    aspect_ratio: str = "16:9",
) -> dict:
    """
    Generate a video from an image and text prompt using Volcengine Ark Seedance.

    Safe for agent retries: if called again while a task is running, it will
    resume polling the existing task instead of creating a duplicate.
    """
    logger.info("Hello from Volcengine Ark (Seedance) I2V!")
    model = model or "doubao-seedance-2-0-260128"
    base_url = _ark_base_url(base_url)
    return _generate_or_resume(
        api_key=api_key,
        prompt=prompt,
        image=image,
        save_path=save_path,
        model=model,
        base_url=base_url,
        duration=duration,
        aspect_ratio=aspect_ratio,
    )


# ---------------------------------------------------------------------------
# Image generation (Seedream via Volcengine Ark)
# ---------------------------------------------------------------------------


def _extract_image_url(result: dict) -> str | None:
    """Extract image URL from a completed content generation task result."""
    content = result.get("content", {})
    if isinstance(content, dict):
        image_url = content.get("image_url") or content.get("video_url")
        if image_url:
            return image_url
    # Fallback: try top-level
    outputs = result.get("outputs") or result.get("output") or []
    if isinstance(outputs, str):
        return outputs
    elif isinstance(outputs, list) and len(outputs) > 0:
        return outputs[0]
    elif isinstance(outputs, dict):
        return outputs.get("image_url") or outputs.get("url")
    return None


def _download_image(url: str, save_path: str) -> bool:
    """Download generated image to save_path."""
    try:
        resp = requests.get(url, stream=True)
        resp.raise_for_status()
        os.makedirs(os.path.dirname(save_path) or ".", exist_ok=True)
        with open(save_path, "wb") as f:
            for chunk in resp.iter_content(8192):
                f.write(chunk)
        logger.info(f"Image saved to: {save_path}")
        return True
    except Exception as e:
        logger.error(f"Image download failed: {e}")
        return False


def text_to_image_generate(
    api_key: str,
    prompt: str,
    model: str = "doubao-seedream-4-0-260628",
    base_url: str = "https://ark.cn-beijing.volces.com/api/v3",
    aspect_ratio: str = "16:9",
    guidance_scale: float = 3.5,
    num_images: int = 1,
) -> str | dict | None:
    """
    Generate an image from a text prompt using Volcengine Ark Seedream.

    Returns image URL string on success, or error dict on failure.
    (Matches wavespeed_api.text_to_image_generate return convention.)
    """
    model = model or "doubao-seedream-4-0-260628"
    base_url = _ark_base_url(base_url)
    seed = int(datetime.now().timestamp())
    payload = {
        "model": model,
        "content": [{"type": "text", "text": prompt}],
        "ratio": aspect_ratio,
        "seed": seed,
    }

    # Submit
    task_id, submit_error = _submit_generation(base_url, api_key, payload)
    if not task_id:
        result = {
            "success": False,
            "error": _submission_error_text("Failed to submit image generation task", submit_error),
        }
        if submit_error:
            result["provider_error"] = submit_error
        return result

    # Poll
    result = _poll_generation(base_url, api_key, task_id)
    if result is None:
        return {
            "success": False,
            "error": f"Task {task_id} polling timed out due to network instability. "
                     f"The task may still be running on the server.",
        }
    if result.get("_task_failed"):
        error_msg = result.get("error") or "Unknown error"
        return {
            "success": False,
            "error": f"Task {task_id} failed on server: {error_msg}",
        }

    # Extract URL
    image_url = _extract_image_url(result)
    if not image_url:
        return {
            "success": False,
            "error": "No image URL in completed task result.",
        }

    logger.info(f"Image generated. URL: {image_url}")
    return image_url


def image_to_image_generate(
    api_key: str,
    prompt: str,
    images: str | list[str],
    model: str = "doubao-seedream-4-0-260628",
    base_url: str = "https://ark.cn-beijing.volces.com/api/v3",
    aspect_ratio: str = "16:9",
    guidance_scale: float = 3.5,
    safety_tolerance: str = "5",
) -> str | dict | None:
    """
    Edit/generate images based on reference image(s) via Volcengine Ark Seedream.
    Supports single image path or list of paths.

    Returns dict with output_path URL on success, or error dict on failure.
    (Matches wavespeed_api.seedream_v4_edit return convention.)
    """
    logger.info("Hello from Volcengine Ark (Seedream) I2I!")
    model = model or "doubao-seedream-4-0-260628"
    base_url = _ark_base_url(base_url)

    if isinstance(images, str):
        images = [images]

    # Encode images to base64
    b64_list = []
    for image in images:
        if image and os.path.exists(image):
            with open(image, "rb") as f:
                img_bytes = f.read()
            b64 = base64.b64encode(img_bytes).decode("utf-8")
            ext = os.path.splitext(image)[1].lower()
            mime = "jpeg" if ext in (".jpg", ".jpeg") else ext.lstrip(".")
            b64_list.append(f"data:image/{mime};base64,{b64}")
        elif image:
            b64_list.append(image)

    seed = int(datetime.now().timestamp())
    content = [{"type": "text", "text": prompt}]
    for img_uri in b64_list:
        content.append({"type": "image_url", "image_url": {"url": img_uri}})

    payload = {
        "model": model,
        "content": content,
        "ratio": aspect_ratio,
        "seed": seed,
    }

    # Submit
    task_id, submit_error = _submit_generation(base_url, api_key, payload)
    if not task_id:
        result = {
            "success": False,
            "error": _submission_error_text("Failed to submit image-to-image task", submit_error),
        }
        if submit_error:
            result["provider_error"] = submit_error
        return result

    # Poll
    result = _poll_generation(base_url, api_key, task_id)
    if result is None:
        return {
            "success": False,
            "error": f"Task {task_id} polling timed out due to network instability. "
                     f"The task may still be running on the server.",
        }
    if result.get("_task_failed"):
        error_msg = result.get("error") or "Unknown error"
        return {
            "success": False,
            "error": f"Task {task_id} failed on server: {error_msg}",
        }

    # Extract URL
    image_url = _extract_image_url(result)
    if not image_url:
        return {
            "success": False,
            "error": "No image URL in completed task result.",
        }

    logger.info(f"Image editing completed. URL: {image_url}")
    return {
        "success": True,
        "output_path": image_url,
        "message": "Image editing completed successfully.",
    }


# ---------------------------------------------------------------------------
# Video editing (style transfer / repainting via Volcengine Ark)
# ---------------------------------------------------------------------------


def _is_http_url(value: str) -> bool:
    parsed = urlparse(value or "")
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _as_bool(value, default: bool = False) -> bool:
    if value is None or value == "":
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _configured_cloudflared_bin(upload_config: dict) -> str | None:
    configured = upload_config.get("cloudflared_bin") or os.getenv("CLOUDFLARED_BIN")
    if configured:
        configured_path = Path(str(configured)).expanduser()
        if configured_path.exists():
            return str(configured_path)
        return str(configured)
    found = shutil.which("cloudflared")
    if found:
        return found
    bundled = _project_root() / ".tools" / "cloudflared"
    if bundled.exists():
        return str(bundled)
    return None


class _QuietHTTPRequestHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, format: str, *args) -> None:  # noqa: A002 - inherited API name
        logger.debug("local tunnel http: " + format, *args)


def _read_cloudflared_url(process: subprocess.Popen, timeout_seconds: float) -> tuple[str, list[str]]:
    if process.stdout is None:
        raise RuntimeError("cloudflared stdout was not captured")
    pattern = re.compile(r"https://[-a-zA-Z0-9.]+\.trycloudflare\.com")
    log_lines: list[str] = []
    selector = selectors.DefaultSelector()
    selector.register(process.stdout, selectors.EVENT_READ)
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        if process.poll() is not None:
            remaining = process.stdout.read() or ""
            if remaining:
                log_lines.extend(remaining.splitlines())
            raise RuntimeError(
                f"cloudflared exited before tunnel URL was ready with code {process.returncode}: "
                + "\n".join(log_lines[-20:])
            )
        events = selector.select(timeout=0.5)
        for key, _ in events:
            line = key.fileobj.readline()
            if not line:
                continue
            log_lines.append(line.rstrip())
            match = pattern.search(line)
            if match:
                candidate = match.group(0)
                host = urlparse(candidate).netloc.lower()
                if host not in {"api.trycloudflare.com", "www.trycloudflare.com"}:
                    return candidate, log_lines
    raise RuntimeError("timed out waiting for cloudflared quick tunnel URL: " + "\n".join(log_lines[-20:]))


def _drain_process_output(process: subprocess.Popen) -> None:
    if process.stdout is None:
        return
    try:
        for line in process.stdout:
            logger.debug("cloudflared: %s", line.rstrip())
    except Exception:
        return


def _wait_for_public_reference_url(url: str, timeout_seconds: float = 90) -> None:
    deadline = time.time() + timeout_seconds
    last_error = None
    while time.time() < deadline:
        try:
            response = requests.head(url, timeout=10, allow_redirects=True)
            if response.status_code < 400:
                return
            last_error = f"HTTP {response.status_code}"
        except requests.RequestException as exc:
            last_error = str(exc)
        time.sleep(2.0)
    raise RuntimeError(f"public reference video URL was not reachable before timeout: {last_error}")


@contextlib.contextmanager
def _cloudflare_tunnel_reference_video_url(video_path: str, upload_config: dict):
    source = Path(video_path).resolve()
    if not source.exists():
        raise FileNotFoundError(f"Reference video path does not exist: {source}")
    cloudflared_bin = _configured_cloudflared_bin(upload_config)
    if not cloudflared_bin:
        raise RuntimeError(
            "VIDEO_UPLOAD_PROVIDER=cloudflare_tunnel requires cloudflared on PATH, "
            "CLOUDFLARED_BIN, or .tools/cloudflared"
        )
    local_port = int(upload_config.get("local_port") or os.getenv("VIDEO_UPLOAD_LOCAL_PORT") or 8765)
    startup_timeout = float(upload_config.get("tunnel_startup_timeout_seconds") or 90)

    tmpdir = tempfile.TemporaryDirectory(prefix="univa_ark_video_")
    httpd = None
    tunnel = None
    try:
        exposed_name = source.name
        exposed_path = Path(tmpdir.name) / exposed_name
        try:
            os.symlink(source, exposed_path)
        except OSError:
            shutil.copy2(source, exposed_path)

        handler = functools.partial(_QuietHTTPRequestHandler, directory=tmpdir.name)
        socketserver.TCPServer.allow_reuse_address = True
        httpd = http.server.ThreadingHTTPServer(("127.0.0.1", local_port), handler)
        server_thread = threading.Thread(target=httpd.serve_forever, name="univa-video-upload-http", daemon=True)
        server_thread.start()
        local_url = f"http://127.0.0.1:{local_port}/{quote(exposed_name)}"
        local_check = requests.head(local_url, timeout=5)
        if local_check.status_code >= 400:
            raise RuntimeError(f"local video server returned HTTP {local_check.status_code} for {local_url}")

        cmd = [cloudflared_bin, "tunnel", "--url", f"http://127.0.0.1:{local_port}", "--no-autoupdate"]
        start_attempts = int(upload_config.get("tunnel_start_attempts") or os.getenv("VIDEO_UPLOAD_TUNNEL_START_ATTEMPTS") or 3)
        last_start_error = None
        base_url = None
        for attempt in range(1, start_attempts + 1):
            tunnel = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )
            try:
                base_url, _startup_logs = _read_cloudflared_url(tunnel, startup_timeout)
                break
            except Exception as exc:
                last_start_error = exc
                if tunnel.poll() is None:
                    tunnel.terminate()
                    try:
                        tunnel.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        tunnel.kill()
                tunnel = None
                logger.warning("cloudflared quick tunnel start attempt %s/%s failed: %s", attempt, start_attempts, exc)
                if attempt < start_attempts:
                    time.sleep(3.0)
        if not base_url or not tunnel:
            raise RuntimeError(f"cloudflared quick tunnel failed after {start_attempts} attempts: {last_start_error}")
        threading.Thread(target=_drain_process_output, args=(tunnel,), name="univa-cloudflared-log", daemon=True).start()
        reference_url = f"{base_url.rstrip('/')}/{quote(exposed_name)}"
        verify_url = _as_bool(upload_config.get("verify_url") or os.getenv("VIDEO_UPLOAD_VERIFY_URL"), default=True)
        if verify_url:
            _wait_for_public_reference_url(reference_url, timeout_seconds=startup_timeout)
        else:
            logger.warning("Skipping local public URL verification for Cloudflare tunnel reference video.")
        ready_delay = float(upload_config.get("ready_delay_seconds") or os.getenv("VIDEO_UPLOAD_READY_DELAY_SECONDS") or 0)
        if ready_delay > 0:
            logger.info("Waiting %.1fs before handing Cloudflare tunnel URL to Ark.", ready_delay)
            time.sleep(ready_delay)
        logger.info("cloudflare quick tunnel ready for Ark reference video: %s", reference_url)
        yield reference_url
    finally:
        if tunnel and tunnel.poll() is None:
            tunnel.terminate()
            try:
                tunnel.wait(timeout=10)
            except subprocess.TimeoutExpired:
                tunnel.kill()
        if httpd:
            httpd.shutdown()
            httpd.server_close()
        tmpdir.cleanup()


def _prepare_ark_reference_video_url(video_path: str) -> str:
    """Return a web URL for Ark reference_video input using configured upload service."""
    if _is_http_url(video_path):
        return video_path
    if not os.path.exists(video_path):
        raise FileNotFoundError(f"Reference video path does not exist and is not a URL: {video_path}")

    from univa.utils.image_upload import upload_file

    reference_url = upload_file(video_path, config_section="video_upload")
    if not reference_url or not _is_http_url(reference_url):
        raise RuntimeError("Uploaded reference video did not produce an HTTP(S) URL usable by Ark.")
    return reference_url


@contextlib.contextmanager
def _ark_reference_video_url(video_path: str):
    """Yield an Ark-readable reference video URL and keep temporary transports alive."""
    if _is_http_url(video_path):
        yield video_path
        return
    if not os.path.exists(video_path):
        raise FileNotFoundError(f"Reference video path does not exist and is not a URL: {video_path}")

    from univa.config.mcp_config import get_mcp_section

    upload_config = get_mcp_section("video_upload")
    provider = str(upload_config.get("provider") or os.getenv("VIDEO_UPLOAD_PROVIDER") or "").strip().lower()
    if provider == "cloudflare_tunnel":
        with _cloudflare_tunnel_reference_video_url(video_path, upload_config) as reference_url:
            yield reference_url
    else:
        yield _prepare_ark_reference_video_url(video_path)


def video_edit_generate(
    api_key: str,
    prompt: str,
    video_path: str,
    save_path: str = None,
    model: str = "doubao-seedance-2-0-260128",
    base_url: str = "https://ark.cn-beijing.volces.com/api/v3",
) -> dict:
    """
    Edit a video (style transfer / repainting) via Volcengine Ark content
    generation API.  Ark requires ``reference_video`` to be a web URL, not a
    base64 data URI, so local files are uploaded through UniVA's configured
    upload service before task submission.

    Returns dict with output_path on success, or error on failure.
    (Matches wavespeed_api.runway_video_editing return convention.)
    """
    logger.info("Hello from Volcengine Ark video editing!")
    model = model or "doubao-seedance-2-0-260128"
    base_url = _ark_base_url(base_url)

    try:
        with _ark_reference_video_url(video_path) as reference_video_url:
            seed = int(datetime.now().timestamp())
            payload = {
                "model": model,
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "video_url", "role": "reference_video", "video_url": {"url": reference_video_url}},
                ],
                "seed": seed,
            }

            # Submit
            task_id, submit_error = _submit_generation(base_url, api_key, payload)
            if not task_id:
                return _build_result(
                    False,
                    error=_submission_error_text("Failed to submit video editing task", submit_error),
                    details={"provider_error": submit_error} if submit_error else None,
                )

            # Poll while any temporary reference-video transport remains alive.
            result = _poll_generation(base_url, api_key, task_id)
            if result is None:
                return _build_result(
                    False,
                    error=f"Task {task_id} polling timed out due to network instability. "
                          f"The task may still be running on the server.",
                )
            if result.get("_task_failed"):
                error_msg = result.get("error") or "Unknown error"
                return _build_result(
                    False,
                    error=f"Task {task_id} failed on server: {error_msg}",
                )

            # Extract URL
            video_url = _extract_video_url(result)
            if not video_url:
                return _build_result(False, error="No video_url in completed task result.")

            # Download
            time_ft = datetime.now().strftime("%m%d%H%M%S")
            url_name = video_url.split("/")[-1].split("?")[0] or "video.mp4"
            output_filename = os.path.abspath(
                save_path if save_path else f"results/{time_ft}_{url_name}"
            )

            if not _download_video(video_url, output_filename):
                return _build_result(False, error="Failed to download edited video.")

            return _build_result(True, output_path=output_filename)
    except Exception as exc:
        return _build_result(
            False,
            error=(
                "Failed to prepare or serve Ark reference video URL. "
                "Ark video editing requires a publicly reachable HTTP(S) URL; "
                f"local input was not exposed successfully: {exc}"
            ),
        )


