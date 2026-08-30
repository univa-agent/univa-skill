from typing import Callable, Dict, List, Optional, Tuple, Union
import cv2
from PIL import Image
import math
import numpy as np
import os
import re

# Type alias for the VLM generator: (images, prompt) -> str
VLMGenerator = Callable[[List[Image.Image], str], str]


def _open_video(video: Union[str, cv2.VideoCapture]) -> Tuple[cv2.VideoCapture, bool]:
    """Open a video path or reuse an existing capture. Returns (cap, need_release)."""
    if isinstance(video, cv2.VideoCapture):
        if not video.isOpened():
            raise ValueError("Provided cv2.VideoCapture is not opened.")
        return video, False
    if not os.path.exists(video):
        raise FileNotFoundError(f"Video path not found: {video}")
    cap = cv2.VideoCapture(video)
    if not cap.isOpened():
        raise RuntimeError(f"Failed to open video: {video}")
    return cap, True


def _get_meta(cap: cv2.VideoCapture) -> Dict:
    """Fetch FPS, frame count, duration, width, height."""
    fps = cap.get(cv2.CAP_PROP_FPS) or 0.0
    frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
    if fps <= 0.0:
        fps = 25.0
    duration_s = frame_count / fps if frame_count > 0 else 0.0
    return {
        "fps": fps,
        "frame_count": frame_count,
        "duration_s": duration_s,
        "width": width,
        "height": height,
    }


def _grab_frame_as_pil(cap: cv2.VideoCapture, frame_idx: int) -> Optional[Image.Image]:
    """Seek to a specific frame index and return it as a PIL Image (RGB)."""
    max_idx = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) - 1
    if max_idx < 0:
        return None
    frame_idx = max(0, min(frame_idx, max_idx))
    cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
    ok, frame = cap.read()
    if not ok or frame is None:
        return None
    frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    return Image.fromarray(frame_rgb)


def _collect_keyframes(
    cap: cv2.VideoCapture,
    fps: float,
    start_s: float,
    end_s: float,
    frames_strategy: str = "first_mid_last"
) -> List[Image.Image]:
    """Collect frames according to strategy."""
    frames: List[Image.Image] = []
    start_idx = int(math.floor(start_s * fps))
    end_idx = int(math.floor(end_s * fps)) - 1
    if end_idx < start_idx:
        end_idx = start_idx

    if frames_strategy == "first_mid_last":
        mid_idx = start_idx + (end_idx - start_idx) // 2
        indices = [start_idx, mid_idx, end_idx]

    elif frames_strategy.startswith("uniform_"):
        try:
            n = int(frames_strategy.split("_")[1])
        except Exception:
            n = 3
        if n <= 1:
            indices = [start_idx]
        else:
            step = max((end_idx - start_idx) / float(n - 1), 1.0)
            indices = [int(start_idx + i * step) for i in range(n)]

    elif frames_strategy.startswith("every_") and frames_strategy.endswith("_sec"):
        try:
            sec = float(frames_strategy.split("_")[1])
        except Exception:
            sec = 1.0
        n = max(1, int((end_s - start_s) / sec))
        indices = [int(start_idx + i * sec * fps) for i in range(n)]
        indices.append(end_idx)
        indices = sorted(set(indices))

    else:
        # fallback to default
        mid_idx = start_idx + (end_idx - start_idx) // 2
        indices = [start_idx, mid_idx, end_idx]

    for idx in indices:
        img = _grab_frame_as_pil(cap, idx)
        if img is None:
            img = Image.fromarray(np.zeros((2, 2, 3), dtype=np.uint8))
        frames.append(img)
    return frames


def _build_probe_prompt(user_prompt: str) -> str:
    """Construct the textual prompt to feed into the VLM."""
    return f"""
You are given several keyframes from a video clip.
Task: Determine whether this clip matches the following request:

<User Request>:
"{user_prompt}"

Answer ONLY in one of these forms:
- "YES" if it clearly matches.
- "NO" if it does not match.
- "UNCERTAIN" if unclear.
Or provide a relevance score as a single number 0–10 (0=irrelevant, 10=perfect match).
    """.strip()


def _parse_vlm_output(output: str) -> float:
    """Convert VLM textual output to a numeric score for ranking/filtering."""
    text = output.strip().upper()
    if text == "YES":
        return 1.0
    if text == "NO":
        return 0.0
    if "UNCERTAIN" in text:
        return 0.5
    match = re.search(r"(\d+)", text)
    if match:
        val = int(match.group(1))
        return max(0.0, min(val / 10.0, 1.0))
    return 0.0


def _probe(
    cap: cv2.VideoCapture,
    meta: Dict,
    clip_granularity_s: float,
    vlm: VLMGenerator,
    user_prompt: str,
    frames_strategy: str,
    *,
    step_ratio: float = 0.5,
    score_threshold: Optional[float] = None,
    top_k: Optional[int] = None,
    max_windows: Optional[int] = None
) -> List[Dict]:
    """Run sliding-window probing using the VLM generator model."""
    win_len = max(clip_granularity_s, 1e-3)
    step = max(clip_granularity_s * step_ratio, 1e-3)

    windows: List[Tuple[float, float]] = []
    t = 0.0
    while t < meta["duration_s"]:
        start_s = t
        end_s = min(t + win_len, meta["duration_s"])
        if end_s - start_s >= 0.1:
            windows.append((start_s, end_s))
        t += step
        if max_windows is not None and len(windows) >= max_windows:
            break

    results: List[Dict] = []
    for (start_s, end_s) in windows:
        frames = _collect_keyframes(cap, meta["fps"], start_s, end_s, frames_strategy)
        constructed_prompt = _build_probe_prompt(user_prompt)
        raw_output = vlm(frames, constructed_prompt)
        score = _parse_vlm_output(raw_output)

        if (score_threshold is None) or (score >= score_threshold):
            results.append({
                "time": (start_s, end_s),
                "score": score,
                "raw_output": raw_output,
                "frames": frames
            })

    results.sort(key=lambda r: r["score"], reverse=True)
    if top_k is not None:
        results = results[:top_k]
    return results


def _uniform_segments(duration_s: float, granularity_s: float) -> List[Tuple[float, float]]:
    """Split [0, duration_s] into uniform segments of size granularity_s (last one may be shorter)."""
    granularity_s = max(granularity_s, 1e-3)
    segments = []
    t = 0.0
    while t < duration_s:
        start_s = t
        end_s = min(t + granularity_s, duration_s)
        if end_s > start_s:
            segments.append((start_s, end_s))
        t += granularity_s
    return segments


def _sample_segments(
    cap: cv2.VideoCapture,
    meta: Dict,
    segments: List[Tuple[float, float]],
    frames_strategy: str
) -> List[Dict]:
    """For each segment, return dict with time and frames."""
    output: List[Dict] = []
    for (start_s, end_s) in segments:
        frames = _collect_keyframes(cap, meta["fps"], start_s, end_s, frames_strategy)
        output.append({
            "time": (start_s, end_s),
            "frames": frames
        })
    return output


def find_or_sample_clips(
    video: Union[str, cv2.VideoCapture],
    clip_granularity_s: float,
    vlm: Optional[VLMGenerator],
    prompt: str,
    mode: str,
    *,
    frames_strategy: str = "first_mid_last",
    step_ratio: float = 0.5,
    score_threshold: Optional[float] = None,
    top_k: Optional[int] = None,
    max_windows: Optional[int] = None
) -> List[Dict]:
    """
    Do probing (to find relevant clips with a VLM) and/or sampling frames for clips.

    frames_strategy: control frame sampling method
        - "first_mid_last" (default)
        - "uniform_N"  e.g. "uniform_5"
        - "every_N_sec" e.g. "every_2_sec"

    Returns a list of dicts:
      [
        {"time": (start, end), "score": score, "raw_output": "...", "frames": [...]},
        ...
      ]
    - In 'probe' or 'both' mode: entries include score + raw_output.
    - In 'sample' mode: entries only have time + frames (no score).
    """
    mode = mode.lower()
    if mode not in {"probe", "sample", "both"}:
        raise ValueError("mode must be one of {'probe','sample','both'}")

    cap, need_release = _open_video(video)
    try:
        meta = _get_meta(cap)

        if mode in {"probe", "both"}:
            if vlm is None:
                raise ValueError("VLM is required for 'probe' or 'both'.")
            results = _probe(
                cap=cap,
                meta=meta,
                clip_granularity_s=clip_granularity_s,
                vlm=vlm,
                user_prompt=prompt,
                frames_strategy=frames_strategy,
                step_ratio=step_ratio,
                score_threshold=score_threshold,
                top_k=top_k,
                max_windows=max_windows,
            )
            return results

        if mode == "sample":
            segments = _uniform_segments(meta["duration_s"], clip_granularity_s)
            samples = _sample_segments(cap, meta, segments, frames_strategy)
            return samples

    finally:
        if need_release:
            cap.release()


### The outputs are:

# [
#   {"time": (start1, end1), "score": 0.9, "raw_output": "YES", "frames": [...]},
#   {"time": (start2, end2), "score": 0.8, "raw_output": "7", "frames": [...]},
#   ...
# ]

### How to use
# res = find_or_sample_clips(
#     video="long.mp4",
#     clip_granularity_s=5.0,
#     vlm=my_vlm,
#     prompt="a person entering a red car",
#     mode="both",
#     frames_strategy="uniform_5",
#     top_k=3
# )

# for item in res:
#     print(item["time"], item.get("score"), item.get("raw_output"))
#     # item["frames"] = PIL images list
