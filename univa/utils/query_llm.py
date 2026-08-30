import os
import logging
import requests
import time
from decord import VideoReader, cpu
import base64
import cv2
from typing import List, Optional, Tuple, Union, Dict
import json
import numpy as np
from univa.utils.text_process import extract_dict


from univa.config.mcp_config import UNIVA_ROOT, get_mcp_section


def _prompt_path(relative_path: str):
    return UNIVA_ROOT / relative_path


llm_config = get_mcp_section("llm")
logger = logging.getLogger(__name__)

_RETRYABLE_HTTP_STATUS = {408, 409, 425, 429, 500, 502, 503, 504}
_TRANSIENT_ERROR_MARKERS = (
    "temporary failure in name resolution",
    "failed to resolve",
    "nameresolutionerror",
    "name or service not known",
    "max retries exceeded",
    "connection aborted",
    "connection reset",
    "connection refused",
    "connection timed out",
    "read timed out",
    "connect timeout",
    "readtimeout",
    "connecttimeout",
    "httpsconnectionpool",
    "temporary failure",
)


def _is_transient_request_error(error: Exception) -> bool:
    if isinstance(
        error,
        (
            requests.exceptions.ConnectionError,
            requests.exceptions.Timeout,
            requests.exceptions.ChunkedEncodingError,
        ),
    ):
        return True

    text = f"{type(error).__name__}: {error}".lower()
    return any(marker in text for marker in _TRANSIENT_ERROR_MARKERS)


def _post_json_with_retry(
    url: str,
    headers: Dict,
    payload: Dict,
    attempts: int = 3,
    timeout: Tuple[int, int] = (10, 300),
) -> requests.Response:
    last_error: Optional[Exception] = None

    for attempt in range(1, attempts + 1):
        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=timeout)
            if resp.status_code in _RETRYABLE_HTTP_STATUS and attempt < attempts:
                delay = min(2 ** (attempt - 1), 5)
                logger.warning(
                    "Transient LLM HTTP status %s from %s; retrying %s/%s in %ss",
                    resp.status_code,
                    url,
                    attempt,
                    attempts,
                    delay,
                )
                time.sleep(delay)
                continue
            return resp
        except requests.exceptions.RequestException as exc:
            last_error = exc
            if attempt >= attempts or not _is_transient_request_error(exc):
                raise

            delay = min(2 ** (attempt - 1), 5)
            logger.warning(
                "Transient LLM request error from %s; retrying %s/%s in %ss: %s",
                url,
                attempt,
                attempts,
                delay,
                exc,
            )
            time.sleep(delay)

    if last_error:
        raise last_error
    raise RuntimeError("LLM request failed without a response")


def _encode_image_to_base64(image_path: str) -> str:
    """
    encode image file to base64 data URI
    """
    try:
        ext = os.path.splitext(image_path)[1].lower()
        mime_types = {
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png": "image/png",
            ".gif": "image/gif",
            ".webp": "image/webp",
        }
        mime_type = mime_types.get(ext)
        if not mime_type:
            raise ValueError(f"not support: {ext}")

        with open(image_path, "rb") as image_file:
            encoded_string = base64.b64encode(image_file.read()).decode("utf-8")
        return f"data:{mime_type};base64,{encoded_string}"
    except FileNotFoundError:
        raise FileNotFoundError(f"image file not found: {image_path}")
    except Exception as e:
        raise RuntimeError(f"encode image failed {image_path}: {e}")

def _extract_and_encode_video_frames(
    video_path: str, 
    frames_to_extract: int = 10,
    target_resolution: Optional[Union[Tuple[int, int], int]] = None,
    maintain_aspect_ratio: bool = True
) -> List[str]:
    """    
    use decord for video processing for better performance
    
    Args:
        video_path: video path
        frames_to_extract: number of frames to extract
        target_resolution: target resolution for each frame
            - None: keep original resolution
            - (width, height): specify width and height
            - int: specify the length of the shorter side, keep aspect ratio
        maintain_aspect_ratio: whether to maintain aspect ratio when target_resolution is (width, height)
    
    Returns:
        List of base64 encoded frames
    """
    try:
        vr = VideoReader(video_path, ctx=cpu(0))
        total_frames = len(vr)
        if total_frames <= 0:
            raise ValueError("Video has no frames")
        
        num_frames = min(frames_to_extract, total_frames)
        base64_frames = []
        
        if num_frames == 1:
            indices = [0]
        else:
            indices = np.linspace(0, total_frames - 1, num_frames, dtype=int).tolist()
        
        frames = vr.get_batch(indices).asnumpy()
        
        for frame in frames:
            frame_bgr = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
            
            if target_resolution is not None:
                frame_bgr = _resize_frame(frame_bgr, target_resolution, maintain_aspect_ratio)
            
            _, buffer = cv2.imencode(".jpg", frame_bgr)
            encoded_string = base64.b64encode(buffer).decode("utf-8")
            base64_frames.append(f"data:image/jpeg;base64,{encoded_string}")
        
        return base64_frames
        
    except Exception as e:
        raise RuntimeError(f"process video failed {video_path}: {e}")


def _resize_frame(
    frame: np.ndarray, 
    target_resolution: Union[Tuple[int, int], int], 
    maintain_aspect_ratio: bool = True
) -> np.ndarray:
    """
    resize frame to target resolution
    """
    if isinstance(target_resolution, int):
        h, w = frame.shape[:2]
        if w < h:
            new_w = target_resolution
            new_h = int(h * target_resolution / w)
        else:
            new_h = target_resolution
            new_w = int(w * target_resolution / h)
        return cv2.resize(frame, (new_w, new_h), interpolation=cv2.INTER_LANCZOS4)
    
    elif isinstance(target_resolution, tuple):
        target_w, target_h = target_resolution
        
        if not maintain_aspect_ratio:
            return cv2.resize(frame, (target_w, target_h), interpolation=cv2.INTER_LANCZOS4)
        else:
            h, w = frame.shape[:2]
            
            scale = min(target_w / w, target_h / h)
            new_w = int(w * scale)
            new_h = int(h * scale)
            
            resized = cv2.resize(frame, (new_w, new_h), interpolation=cv2.INTER_LANCZOS4)
            
            result = np.zeros((target_h, target_w, 3), dtype=np.uint8)
            
            y_offset = (target_h - new_h) // 2
            x_offset = (target_w - new_w) // 2
            
            result[y_offset:y_offset+new_h, x_offset:x_offset+new_w] = resized
            
            return result


def prepare_multimodal_messages_openai_format(
    prompt_text: str,
    image_paths: Optional[List[str]] = None,
    video_paths: Optional[List[str]] = None,
    video_frames_to_extract: int = 10,
    existing_messages: Optional[List[Dict]] = None,
) -> List[Dict]:
    messages = list(existing_messages) if existing_messages else []
    
    content_parts = []

    content_parts.append({"type": "text", "text": prompt_text})

    if image_paths:
        for path in image_paths:
            base64_image = _encode_image_to_base64(path)
            content_parts.append({
                "type": "image_url",
                "image_url": {"url": base64_image}
            })

    if video_paths:
        for path in video_paths:
            base64_frames = _extract_and_encode_video_frames(path, video_frames_to_extract, (360, 420))
            for frame_data in base64_frames:
                content_parts.append({
                    "type": "image_url",
                    "image_url": {"url": frame_data}
                })

    messages.append({
        "role": "user",
        "content": content_parts
    })

    return messages



def query_openrouter(
    api_key: str,
    model: str,
    messages: list[dict],
    max_tokens: int = 1024,
    temperature: float = 0.7,
    base_url: str = "https://openrouter.ai/api/v1"
) -> dict:
    url = f"{base_url}/chat/completions"
    
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
        "HTTP-Referer": "https://your-app-url.com",
        "X-Title": "Your App Name"
    }
    
    payload = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature
    }
    
    try:
        resp = _post_json_with_retry(url, headers, payload)
        resp.raise_for_status()
        
        data = resp.json()
        
        if "choices" in data and len(data["choices"]) > 0:
            return {
                "content": data["choices"][0]["message"]["content"],
                "response": data,
                "usage": data.get("usage", {}),
                "model": data.get("model", model)
            }
        else:
            raise ValueError("Invalid response format from OpenRouter")
            
    except requests.exceptions.RequestException as e:
        if hasattr(e, 'response') and e.response is not None:
            error_detail = e.response.text
            try:
                error_data = json.loads(error_detail)
                raise Exception(f"OpenRouter error: {error_data}")
            except json.JSONDecodeError:
                raise Exception(f"HTTP error: {e.response.status_code}, {error_detail}")
        raise
    except Exception as e:
        raise Exception(f"Error occurred during OpenRouter call: {str(e)}")

def query_gemini(
    api_key: str,
    model: str,
    messages: list[dict],
    max_tokens: int = 1024,
    base_url: str = "https://generativelanguage.googleapis.com/v1beta"
) -> dict:
    url = f"{base_url}/models/{model}:generateContent"
    headers = {
        "Content-Type": "application/json",
        "X-goog-api-key": api_key
    }

    contents = []
    for message in messages:
        parts = []
        if isinstance(message["content"], str):
            parts.append({"text": message["content"]})
        elif isinstance(message["content"], list):
            for content in message["content"]:
                if content["type"] == "text":
                    parts.append({"text": content["text"]})
                elif content["type"] == "image":
                    parts.append({
                        "inline_data": {
                            "mime_type": content["source"]["media_type"],
                            "data": content["source"]["data"]
                        }
                    })
                elif content["type"] == "image_url":
                    data_uri = content["image_url"]["url"]
                    if data_uri.startswith("data:"):
                        mime_type_and_data = data_uri[5:]
                        if "," in mime_type_and_data:
                            mime_type, data = mime_type_and_data.split(",", 1)
                            if ";base64" in mime_type:
                                mime_type = mime_type.replace(";base64", "")
                            parts.append({
                                "inline_data": {
                                    "mime_type": mime_type,
                                    "data": data
                                }
                            })
        
        contents.append({"parts": parts})

    payload = {
        "contents": contents,
        "generationConfig": {
            "maxOutputTokens": max_tokens
        }
    }

    resp = _post_json_with_retry(url, headers, payload)
    resp.raise_for_status()
    res = resp.json()
    res = res['candidates'][0]['content']['parts'][0]['text']
    return res

def prepare_video_messages(
    video_path: str,
    text_prompt: str,
    fps: float = 1.0
) -> List[Dict]:
    try:
        vr = VideoReader(video_path)
        frame_indices = range(0, len(vr), int(vr.get_avg_fps() / fps))
        frames = vr.get_batch(frame_indices).asnumpy()

        content = []
        for frame in frames:
            _, buffer = cv2.imencode('.jpg', frame)
            frame_b64 = base64.b64encode(buffer).decode('utf-8')
            
            content.append({
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": "image/jpeg",
                    "data": frame_b64
                }
            })

        content.append({
            "type": "text",
            "text": text_prompt
        })

        return [{
            "role": "user",
            "content": content
        }]

    except Exception as e:
        raise ValueError(f"error: {str(e)}")

def query_claude(
    api_key: str,
    model: str,
    messages: list[dict],
    max_tokens: int = 1024,
    endpoint_id: str = None,
    base_url: str = "https://api.anthropic.com"
) -> dict:
    # url = f"{base_url}/{endpoint_id}/claude/anthropic/v1/messages"
    # url = f"{base_url}/v1/chat/completions"
    url = f"{base_url}/v1/messages"
    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "Content-Type": "application/json"
    }
    payload = {
        "model": model,
        "max_tokens": max_tokens,
        "messages": messages
    }

    resp = _post_json_with_retry(url, headers, payload)
    resp.raise_for_status()
    return resp.json()


def query_openai(
    api_key: str,
    model: str,
    messages: list[dict],
    max_completion_tokens: int = 1024,
    temperature: float = 1.0,
    base_url: str = "https://api.openai.com/v1"
) -> dict:
    url = f"{base_url}/chat/completions"
    
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }
    
    payload = {
        "model": model,
        "messages": messages,
        "max_completion_tokens": max_completion_tokens,
        "temperature": temperature
    }
    
    try:
        resp = _post_json_with_retry(url, headers, payload)
        resp.raise_for_status()
        
        data = resp.json()
        
        if "choices" in data and len(data["choices"]) > 0:
            return {
                "content": data["choices"][0]["message"]["content"],
                "response": data,
                "usage": data.get("usage", {}),
                "model": data.get("model", model)
            }
        else:
            raise ValueError("Invalid response format from OpenAI")
            
    except requests.exceptions.RequestException as e:
        if hasattr(e, 'response') and e.response is not None:
            error_detail = e.response.text
            try:
                error_data = json.loads(error_detail)
                raise Exception(f"OpenAI error: {error_data}")
            except json.JSONDecodeError:
                raise Exception(f"HTTP error: {e.response.status_code}, {error_detail}")
        raise
    except Exception as e:
        raise Exception(f"Error occurred during OpenAI call: {str(e)}")



def refine_gen_prompt(prompt: str, media_type: str = "image") -> str:
    if media_type == "image":
        with open(_prompt_path("prompts/generation/keyframe_refine.txt"), "r") as f:
            ins_prompt = f.read()
    elif media_type == "video":
        with open(_prompt_path("prompts/generation/t2v_refine_prompt.txt"), "r") as f:
            ins_prompt = f.read()
    elif media_type == "character":
        with open(_prompt_path("prompts/generation/character_prompt_refine.txt"), "r") as f:
            ins_prompt = f.read()
    text = f"{ins_prompt}\n\n{prompt}"
    message = prepare_multimodal_messages_openai_format(text)
    response = query_openai(
                        api_key=llm_config.get('openai_api_key', None),
                        model=llm_config.get('model', 'gpt-5'),
                        base_url=llm_config.get('base_url', 'https://api.openai.com/v1'),
                        messages=message,
                        max_completion_tokens=8192
                    )
    return_content = response.get("content", "")
    context_json = extract_dict(return_content)
    refined_prompt = context_json.get("prompt", "")

    return refined_prompt


def audio_prompt_gen(video_path: str) -> str:
    with open(_prompt_path("prompts/generation/audio_prompt.txt"), "r") as f:
        ins_prompt = f.read()
    
    message = prepare_multimodal_messages_openai_format(ins_prompt, video_paths=[video_path], video_frames_to_extract=64)
    response = query_openai(
        api_key=llm_config.get('openai_api_key', None),
        model=llm_config.get('model', 'gpt-5'),
        base_url=llm_config.get('base_url', 'https://api.openai.com/v1'),
        messages=message,
        max_completion_tokens=8192
    )

    content = response.get("content")
    context_json = extract_dict(content)
    audio_prompt = context_json.get("description", "")

    return audio_prompt


def speech_prompt_gen(video_path: str) -> str:
    """Generate speech content for video narration/dubbing based on video content."""
    with open(_prompt_path("prompts/generation/speech_prompt.txt"), "r") as f:
        ins_prompt = f.read()
    
    message = prepare_multimodal_messages_openai_format(ins_prompt, video_paths=[video_path], video_frames_to_extract=64)
    response = query_openai(
        api_key=llm_config.get('openai_api_key', None),
        model=llm_config.get('model', 'gpt-5'),
        base_url=llm_config.get('base_url', 'https://api.openai.com/v1'),
        messages=message,
        max_completion_tokens=8192
    )

    content = response.get("content")
    context_json = extract_dict(content)
    speech_text = context_json.get("speech_text", "")

    return speech_text


def multimodal_query(prompt: str, image_path: str=None , video_path: str=None, video_frames_to_extract: int=16):
    multimodal_messages = prepare_multimodal_messages_openai_format(
                            prompt_text=prompt,
                            image_paths=[image_path] if image_path else None,
                            video_paths=[video_path] if video_path else None,
                            video_frames_to_extract=video_frames_to_extract if video_path else None,
                        )

    if video_path:
        response = query_openai(
                        api_key=llm_config.get('openai_api_key', None),
                        model=llm_config.get('model', 'gpt-5'),
                        base_url=llm_config.get('base_url', 'https://api.openai.com/v1'),
                        messages=multimodal_messages,
                        max_completion_tokens=16384
                    )

    else:
        response = query_openai(
                        api_key=llm_config.get('openai_api_key', None),
                        model=llm_config.get('model', 'gpt-5'),
                        base_url=llm_config.get('base_url', 'https://api.openai.com/v1'),
                        messages=multimodal_messages,
                        max_completion_tokens=16384
                    )

    content = response["content"]

    return content

    
