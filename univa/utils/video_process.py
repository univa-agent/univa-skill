import os
import subprocess
import base64
import io
import numpy as np
from PIL import Image
import imageio
from univa.utils.query_llm import query_openai
import logging
import json
import math
import tempfile

from typing import List, Union
from decord import VideoReader, cpu, DECORDError


from univa.config.mcp_config import UNIVA_ROOT, get_mcp_section


def _prompt_path(relative_path: str):
    return UNIVA_ROOT / relative_path


llm_config = get_mcp_section("llm")
logger = logging.getLogger(__name__)
_FFMPEG_FILTER_CACHE: dict[str, bool] = {}

_XFADE_TRANSITIONS = {
    "fade",
    "wipeleft",
    "wiperight",
    "wipeup",
    "wipedown",
    "slideleft",
    "slideright",
    "slideup",
    "slidedown",
    "smoothleft",
    "smoothright",
    "smoothup",
    "smoothdown",
    "circlecrop",
    "circleopen",
    "circleclose",
    "rectcrop",
    "distance",
    "fadeblack",
    "fadewhite",
    "radial",
}

_TRANSITION_ALIASES = {
    "": "crossfade",
    "auto": "crossfade",
    "default": "crossfade",
    "fade": "crossfade",
    "dissolve": "crossfade",
    "cross_dissolve": "crossfade",
    "crossfade": "crossfade",
    "smooth": "crossfade",
    "seamless": "crossfade",
    "silky": "crossfade",
    "hard_cut": "hard_cut",
    "hardcut": "hard_cut",
    "cut": "hard_cut",
    "none": "hard_cut",
    "off": "hard_cut",
    "black": "fadeblack",
    "fadeblack": "fadeblack",
    "dip_to_black": "fadeblack",
    "white": "fadewhite",
    "fadewhite": "fadewhite",
    "dip_to_white": "fadewhite",
    "whip": "smoothleft",
    "whip_pan": "smoothleft",
    "wipe": "wipeleft",
    "object_wipe": "wipeleft",
    "slide": "slideleft",
}


def supported_merge_transitions() -> dict[str, list[str]]:
    """Return transition names the local merge layer understands."""
    native = ["hard_cut", "crossfade"]
    if _ffmpeg_has_filter("xfade"):
        native.extend(sorted(_XFADE_TRANSITIONS))
    else:
        native.extend(["fadeblack", "fadewhite"])
    return {
        "always_available": ["hard_cut", "crossfade"],
        "available_in_this_ffmpeg": sorted(set(native)),
        "aliases": sorted(key for key in _TRANSITION_ALIASES if key),
    }


def _coerce_edge_transitions(transition: str | list[str] | None, edge_count: int) -> list[str]:
    if isinstance(transition, list):
        values = [resolve_merge_transition(item) for item in transition]
        if not values:
            values = ["crossfade"]
        while len(values) < edge_count:
            values.append(values[-1])
        return values[:edge_count]
    return [resolve_merge_transition(transition)] * max(0, edge_count)


def resolve_merge_transition(transition: str | None) -> str:
    """Resolve user-facing transition words to an executable transition name."""
    if transition is None:
        return "crossfade"
    raw = str(transition).strip()
    lowered = raw.lower().replace("-", "_").replace(" ", "_")
    if lowered in _TRANSITION_ALIASES:
        return _TRANSITION_ALIASES[lowered]
    compact = lowered.replace("_", "")
    if compact in _TRANSITION_ALIASES:
        return _TRANSITION_ALIASES[compact]
    if lowered in _XFADE_TRANSITIONS:
        return lowered

    text = raw.lower()
    if any(token in text for token in ("smooth", "seamless", "dissolve")):
        return "crossfade"
    if any(token in text for token in ("black",)):
        return "fadeblack"
    if any(token in text for token in ("white",)):
        return "fadewhite"
    if any(token in text for token in ("hard cut", "hard_cut")):
        return "hard_cut"
    if any(token in text for token in ("whip",)):
        return "smoothleft"
    if any(token in text for token in ("wipe",)):
        return "wipeleft"
    logger.info("Unknown transition %r; falling back to crossfade.", transition)
    return "crossfade"


def _ffmpeg_has_filter(filter_name: str) -> bool:
    if filter_name in _FFMPEG_FILTER_CACHE:
        return _FFMPEG_FILTER_CACHE[filter_name]
    result = subprocess.run(
        ["ffmpeg", "-hide_banner", "-filters"],
        capture_output=True,
        text=True,
    )
    available = result.returncode == 0 and filter_name in result.stdout
    _FFMPEG_FILTER_CACHE[filter_name] = available
    return available


def _video_has_audio(path: str) -> bool:
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "a:0",
            "-show_entries",
            "stream=index",
            "-of",
            "csv=p=0",
            path,
        ],
        capture_output=True,
        text=True,
    )
    return result.returncode == 0 and bool(result.stdout.strip())


def merge_videos(video_paths: list[str] | str, output_file="merged.mp4", audio_list: list[str] | None = None):
    """
    Merges multiple video files into a single video file.

    Args:
        video_paths (list[str] | str): A list of paths to the video files to merge, or a folder path containing videos.
        output_file (str): The path to save the merged video.
        audio_list (list[str] | None): A list of paths to the audio files to merge. If None, no audio is merged.

    Returns:
        str: The path to the merged video file if successful, None otherwise.
    """
    rank = int(os.getenv("RANK", 0))
    if rank != 0:
        return None

    if isinstance(video_paths, str):
        folder_path = video_paths
        video_files_to_merge = sorted(
            [os.path.join(folder_path, f) for f in os.listdir(folder_path) if f.lower().endswith((".mp4", ".mov", ".avi"))],
            key=lambda x: x.lower(),
        )
    elif isinstance(video_paths, list):
        # Preserve caller-provided order. Shot order is part of the edit plan.
        video_files_to_merge = [
            f for f in video_paths if f.lower().endswith((".mp4", ".mov", ".avi"))
        ]
    else:
        raise TypeError("video_paths must be a string (folder path) or a list of strings (file paths).")

    if not video_files_to_merge:
        print("No video files found to merge.")
        return None

    output_file = os.path.abspath(output_file)
    output_dir = os.path.dirname(output_file) or os.getcwd()
    os.makedirs(output_dir, exist_ok=True)

    def _write_concat_file(list_file: str, paths: list[str]) -> None:
        with open(list_file, "w", encoding="utf-8") as f:
            for file in paths:
                safe_file = os.path.abspath(file).replace("'", "'\\''")
                f.write(f"file '{safe_file}'\n")

    with tempfile.TemporaryDirectory(prefix="univa_merge_", dir=output_dir) as tmp_dir:
        list_file = os.path.join(tmp_dir, "concat_list.txt")
        _write_concat_file(list_file, video_files_to_merge)

        if audio_list is not None:
            temp_video_file = os.path.join(tmp_dir, "temp_merged_video.mp4")
            cmd = [
                "ffmpeg",
                "-f", "concat",
                "-safe", "0",
                "-i", list_file,
                "-c:v", "libx264",
                "-preset", "ultrafast",
                "-crf", "23",
                "-an",
                "-y",
                temp_video_file,
            ]
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode != 0:
                print(f"Video concatenation without audio failed: {result.stderr}")
                cmd = [
                    "ffmpeg",
                    "-f", "concat",
                    "-safe", "0",
                    "-i", list_file,
                    "-c", "copy",
                    "-an",
                    "-y",
                    temp_video_file,
                ]
                subprocess.run(cmd)

            if len(audio_list) == 1:
                cmd = [
                    "ffmpeg",
                    "-i", temp_video_file,
                    "-i", audio_list[0],
                    "-c:v", "copy",
                    "-c:a", "aac",
                    "-y",
                    output_file,
                ]
                result = subprocess.run(cmd, capture_output=True, text=True)
                if result.returncode != 0:
                    print(f"Failed to merge video and audio: {result.stderr}")
                    cmd = [
                        "ffmpeg",
                        "-i", temp_video_file,
                        "-i", audio_list[0],
                        "-c", "copy",
                        "-y",
                        output_file,
                    ]
                    subprocess.run(cmd)
            else:
                temp_audio_file = os.path.join(tmp_dir, "temp_merged_audio.wav")
                audio_list_file = os.path.join(tmp_dir, "audio_concat_list.txt")
                _write_concat_file(audio_list_file, audio_list)

                cmd = [
                    "ffmpeg",
                    "-f", "concat",
                    "-safe", "0",
                    "-i", audio_list_file,
                    "-c:a", "aac",
                    "-y",
                    temp_audio_file,
                ]
                result = subprocess.run(cmd, capture_output=True, text=True)
                if result.returncode != 0:
                    print(f"Audio concatenation failed: {result.stderr}")
                    cmd = [
                        "ffmpeg",
                        "-f", "concat",
                        "-safe", "0",
                        "-i", audio_list_file,
                        "-c:a", "pcm_s16le",
                        "-y",
                        temp_audio_file,
                    ]
                    result = subprocess.run(cmd, capture_output=True, text=True)
                    if result.returncode != 0:
                        print(f"Second audio concatenation attempt failed: {result.stderr}")
                        cmd = [
                            "ffmpeg",
                            "-f", "concat",
                            "-safe", "0",
                            "-i", audio_list_file,
                            "-c", "copy",
                            "-y",
                            temp_audio_file,
                        ]
                        subprocess.run(cmd)

                cmd = [
                    "ffmpeg",
                    "-i", temp_video_file,
                    "-i", temp_audio_file,
                    "-c:v", "copy",
                    "-c:a", "aac",
                    "-b:a", "192k",
                    "-y",
                    output_file,
                ]
                result = subprocess.run(cmd, capture_output=True, text=True)
                if result.returncode != 0:
                    print(f"Failed to merge video and audio: {result.stderr}")
                    cmd = [
                        "ffmpeg",
                        "-i", temp_video_file,
                        "-i", temp_audio_file,
                        "-c:v", "copy",
                        "-c:a", "aac",
                        "-ar", "44100",
                        "-y",
                        output_file,
                    ]
                    result = subprocess.run(cmd, capture_output=True, text=True)
                    if result.returncode != 0:
                        print(f"Second attempt to merge video and audio failed: {result.stderr}")
                        cmd = [
                            "ffmpeg",
                            "-i", temp_video_file,
                            "-c", "copy",
                            "-y",
                            output_file,
                        ]
                        subprocess.run(cmd)
        else:
            cmd = [
                "ffmpeg",
                "-f", "concat",
                "-safe", "0",
                "-i", list_file,
                "-c:v", "libx264",
                "-preset", "ultrafast",
                "-crf", "23",
                "-c:a", "aac",
                "-y",
                output_file,
            ]
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode != 0:
                print(f"Video concatenation failed: {result.stderr}")
                cmd = [
                    "ffmpeg",
                    "-f", "concat",
                    "-safe", "0",
                    "-i", list_file,
                    "-c", "copy",
                    "-y",
                    output_file,
                ]
                subprocess.run(cmd)

    return output_file

def _merge_videos_with_dip_fallback(
    video_files_to_merge: list[str],
    durations: list[float],
    output_file: str,
    transition_duration: float,
    output_size: str,
    color: str = "black",
) -> str | None:
    """Explicit dip-to-color transition for users who ask for black/white transitions."""
    try:
        width, height = output_size.lower().split("x", 1)
    except ValueError:
        width, height = "1280", "720"

    inputs: list[str] = []
    for path in video_files_to_merge:
        inputs.extend(["-i", path])

    filters: list[str] = []
    labels: list[str] = []
    for idx, duration in enumerate(durations):
        fade_duration = max(0.1, min(float(transition_duration), duration / 3))
        fade_out_start = max(0.0, duration - fade_duration)
        label = f"vf{idx}"
        fade_parts: list[str] = []
        if idx > 0:
            fade_parts.append(f"fade=t=in:st=0:d={fade_duration:.3f}:color={color}")
        if idx < len(durations) - 1:
            fade_parts.append(f"fade=t=out:st={fade_out_start:.3f}:d={fade_duration:.3f}:color={color}")
        fade_filter = ",".join(fade_parts)
        if fade_filter:
            fade_filter += ","
        filters.append(
            f"[{idx}:v]fps=24,scale={width}:{height}:force_original_aspect_ratio=decrease,"
            f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,format=yuv420p,"
            f"{fade_filter}setpts=PTS-STARTPTS[{label}]"
        )
        labels.append(f"[{label}]")

    filters.append(f"{''.join(labels)}concat=n={len(labels)}:v=1:a=0[outv]")
    cmd = [
        "ffmpeg",
        *inputs,
        "-filter_complex",
        ";".join(filters),
        "-map",
        "[outv]",
        "-an",
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "22",
        "-movflags",
        "+faststart",
        "-y",
        output_file,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        logger.warning("Dip-to-%s merge failed: %s", color, result.stderr[-1000:])
        return None
    return output_file


def _merge_pair_with_blend_transition(
    first_video: str,
    second_video: str,
    output_file: str,
    first_duration: float,
    second_duration: float,
    transition_duration: float,
    output_size: str,
    preserve_audio: bool,
) -> str | None:
    """Blend the tail of the first video into the head of the second video."""
    try:
        width, height = output_size.lower().split("x", 1)
    except ValueError:
        width, height = "1280", "720"

    safe_duration = max(0.1, min(float(transition_duration), first_duration / 2.5, second_duration / 2.5))
    first_main_end = max(0.0, first_duration - safe_duration)
    filters = [
        f"[0:v]fps=24,scale={width}:{height}:force_original_aspect_ratio=decrease,"
        f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,format=yuv420p,setpts=PTS-STARTPTS[v0]",
        f"[1:v]fps=24,scale={width}:{height}:force_original_aspect_ratio=decrease,"
        f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,format=yuv420p,setpts=PTS-STARTPTS[v1]",
        "[v0]split=2[v0a][v0b]",
        "[v1]split=2[v1a][v1b]",
        f"[v0a]trim=start=0:end={first_main_end:.3f},setpts=PTS-STARTPTS[v0main]",
        f"[v0b]trim=start={first_main_end:.3f}:end={first_duration:.3f},setpts=PTS-STARTPTS[v0tail]",
        f"[v1a]trim=start=0:end={safe_duration:.3f},setpts=PTS-STARTPTS[v1head]",
        f"[v1b]trim=start={safe_duration:.3f},setpts=PTS-STARTPTS[v1rest]",
        f"[v0tail][v1head]blend=all_expr='A*(1-T/{safe_duration:.3f})+B*(T/{safe_duration:.3f})',setpts=PTS-STARTPTS[vxfade]",
        "[v0main][vxfade][v1rest]concat=n=3:v=1:a=0[vout]",
    ]
    maps = ["-map", "[vout]"]
    audio_args = ["-an"]
    if preserve_audio and _video_has_audio(first_video) and _video_has_audio(second_video):
        filters.extend(
            [
                "[0:a]aresample=48000,asetpts=PTS-STARTPTS[a0]",
                "[1:a]aresample=48000,asetpts=PTS-STARTPTS[a1]",
                f"[a0][a1]acrossfade=d={safe_duration:.3f}:c1=tri:c2=tri[aout]",
            ]
        )
        maps.extend(["-map", "[aout]"])
        audio_args = ["-c:a", "aac", "-b:a", "192k"]

    cmd = [
        "ffmpeg",
        "-i",
        first_video,
        "-i",
        second_video,
        "-filter_complex",
        ";".join(filters),
        *maps,
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "22",
        *audio_args,
        "-movflags",
        "+faststart",
        "-y",
        output_file,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        logger.warning("Blend crossfade merge failed: %s", result.stderr[-1000:])
        return None
    return output_file


def _merge_videos_with_blend_fallback(
    video_files_to_merge: list[str],
    durations: list[float],
    output_file: str,
    transition_duration: float,
    output_size: str,
    preserve_audio: bool,
) -> str | None:
    """Fallback for ffmpeg builds without xfade: true tail-to-head crossfade."""
    if len(video_files_to_merge) == 2:
        return _merge_pair_with_blend_transition(
            video_files_to_merge[0],
            video_files_to_merge[1],
            output_file,
            durations[0],
            durations[1],
            transition_duration,
            output_size,
            preserve_audio,
        )

    with tempfile.TemporaryDirectory(prefix="univa_transition_") as tmp_dir:
        current_video = video_files_to_merge[0]
        current_duration = durations[0]
        for idx, next_video in enumerate(video_files_to_merge[1:], start=1):
            step_output = output_file if idx == len(video_files_to_merge) - 1 else os.path.join(tmp_dir, f"step_{idx}.mp4")
            merged = _merge_pair_with_blend_transition(
                current_video,
                next_video,
                step_output,
                current_duration,
                durations[idx],
                transition_duration,
                output_size,
                preserve_audio,
            )
            if not merged:
                return None
            current_video = merged
            current_duration = current_duration + durations[idx] - transition_duration
        return output_file


def merge_videos_with_transitions(
    video_paths: list[str] | str,
    output_file: str = "merged.mp4",
    transition: str | list[str] = "fade",
    transition_duration: float = 0.4,
    output_size: str = "1280x720",
    preserve_audio: bool = True,
) -> str | None:
    """
    Merge videos with visual transitions.

    Smooth/seamless/fade/dissolve requests are rendered as true overlapping
    tail-to-head crossfades. Black/white dips are used only when explicitly
    requested. Source audio is crossfaded when all inputs have audio.
    """
    if isinstance(video_paths, str):
        folder_path = video_paths
        video_files_to_merge = sorted(
            [
                os.path.join(folder_path, f)
                for f in os.listdir(folder_path)
                if f.lower().endswith((".mp4", ".mov", ".avi"))
            ],
            key=lambda x: x.lower(),
        )
    elif isinstance(video_paths, list):
        video_files_to_merge = [
            f for f in video_paths if f.lower().endswith((".mp4", ".mov", ".avi"))
        ]
    else:
        raise TypeError("video_paths must be a string folder path or a list of file paths.")

    if not video_files_to_merge:
        print("No video files found to merge.")
        return None
    if len(video_files_to_merge) == 1:
        return merge_videos(video_files_to_merge, output_file=output_file)

    edge_transitions = _coerce_edge_transitions(transition, len(video_files_to_merge) - 1)
    if edge_transitions and all(item in {"hard_cut", "cut", "none", "off"} for item in edge_transitions):
        return merge_videos(video_files_to_merge, output_file=output_file)

    output_dir = os.path.dirname(output_file)
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)

    durations: list[float] = []
    for path in video_files_to_merge:
        try:
            durations.append(get_video_duration_seconds(path))
        except Exception as exc:
            logger.warning("Failed to inspect duration for %s: %s", path, exc)
            return merge_videos(video_files_to_merge, output_file=output_file)

    shortest = min(durations)
    safe_transition_duration = max(0.1, min(float(transition_duration), shortest / 2.5))
    if safe_transition_duration <= 0:
        return merge_videos(video_files_to_merge, output_file=output_file)

    if all(item == "crossfade" for item in edge_transitions):
        return _merge_videos_with_blend_fallback(
            video_files_to_merge,
            durations,
            output_file,
            safe_transition_duration,
            output_size,
            preserve_audio,
        ) or merge_videos(video_files_to_merge, output_file=output_file)

    if not _ffmpeg_has_filter("xfade"):
        if len(set(edge_transitions)) == 1 and edge_transitions[0] in {"fadeblack", "fadewhite"}:
            color = "white" if edge_transitions[0] == "fadewhite" else "black"
            return _merge_videos_with_dip_fallback(
                video_files_to_merge,
                durations,
                output_file,
                safe_transition_duration,
                output_size,
                color=color,
            ) or merge_videos(video_files_to_merge, output_file=output_file)
        logger.info(
            "ffmpeg xfade filter is unavailable; using true crossfade fallback for edge transitions %s.",
            edge_transitions,
        )
        return _merge_videos_with_blend_fallback(
            video_files_to_merge,
            durations,
            output_file,
            safe_transition_duration,
            output_size,
            preserve_audio,
        ) or merge_videos(video_files_to_merge, output_file=output_file)

    try:
        width, height = output_size.lower().split("x", 1)
    except ValueError:
        width, height = "1280", "720"
    inputs: list[str] = []
    for path in video_files_to_merge:
        inputs.extend(["-i", path])

    filters: list[str] = []
    for idx in range(len(video_files_to_merge)):
        filters.append(
            f"[{idx}:v]fps=24,scale={width}:{height}:force_original_aspect_ratio=decrease,"
            f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,format=yuv420p,"
            f"settb=AVTB,setpts=PTS-STARTPTS[v{idx}]"
        )

    current_label = "v0"
    for idx in range(1, len(video_files_to_merge)):
        next_label = f"x{idx}"
        offset = sum(durations[:idx]) - safe_transition_duration * idx
        offset = max(0.0, offset)
        edge_transition = edge_transitions[idx - 1]
        xfade_transition = "fade" if edge_transition == "crossfade" else edge_transition
        filters.append(
            f"[{current_label}][v{idx}]xfade=transition={xfade_transition}:"
            f"duration={safe_transition_duration:.3f}:offset={offset:.3f}[{next_label}]"
        )
        current_label = next_label

    maps = ["-map", f"[{current_label}]"]
    audio_args = ["-an"]
    if preserve_audio and all(_video_has_audio(path) for path in video_files_to_merge):
        for idx in range(len(video_files_to_merge)):
            filters.append(f"[{idx}:a]aresample=48000,asetpts=PTS-STARTPTS[a{idx}]")
        audio_label = "a0"
        for idx in range(1, len(video_files_to_merge)):
            next_audio = f"ax{idx}"
            filters.append(f"[{audio_label}][a{idx}]acrossfade=d={safe_transition_duration:.3f}:c1=tri:c2=tri[{next_audio}]")
            audio_label = next_audio
        maps.extend(["-map", f"[{audio_label}]"])
        audio_args = ["-c:a", "aac", "-b:a", "192k"]

    cmd = [
        "ffmpeg",
        *inputs,
        "-filter_complex",
        ";".join(filters),
        *maps,
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "22",
        *audio_args,
        "-movflags",
        "+faststart",
        "-y",
        output_file,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        logger.warning("Transition merge failed, trying true crossfade fallback: %s", result.stderr[-1000:])
        blended = _merge_videos_with_blend_fallback(
            video_files_to_merge,
            durations,
            output_file,
            safe_transition_duration,
            output_size,
            preserve_audio,
        )
        if blended:
            return blended
        return merge_videos(video_files_to_merge, output_file=output_file)
    return output_file

def save_last_frame_decord(video_path, output_path=None):
    rank = int(os.getenv("RANK", 0))
    if rank == 0:
        if not os.path.isfile(video_path):
            raise FileNotFoundError(f"video file is not exist: {video_path}")

        try:
            vr = VideoReader(video_path, ctx=cpu(0))
            
            total_frames = len(vr)
            if total_frames == 0:
                raise ValueError("can not detect frame from video")

            last_frame = vr[-1].asnumpy()  # uint8 (H, W, 3)

        except DECORDError as e:
            raise RuntimeError(f"video decoded fail: {str(e)}")
        except IndexError:
            raise RuntimeError("index error")
        finally:
            if 'vr' in locals():
                del vr

        if output_path is None:
            dir_name = os.path.dirname(video_path)
            file_name = os.path.splitext(os.path.basename(video_path))[0]
            output_path = os.path.join(dir_name, f"{file_name}_last_frame.png")

        try:
            img = Image.fromarray(last_frame)
            img.save(output_path, format='PNG', compress_level=0)
            print(f"save the last frame to: {output_path}")
            return output_path
        except IOError as e:
            raise RuntimeError(f"failed to save frame: {str(e)}")
    
def extract_frames(video_path: str, output_dir: str, target_fps: int = 1, grey=False) -> None:
    """
    Extract video frames at specified FPS using decord and save losslessly with Pillow
    
    Args:
        video_path: Path to input video file
        output_dir: Directory to save extracted frames
        target_fps: Target frames per second (default=1)
    """
    try:
        # Create output directory if not exists
        os.makedirs(output_dir, exist_ok=True)
        
        # Initialize video reader
        vr = VideoReader(video_path, ctx=cpu(0))
        
        # Get video metadata
        original_fps = vr.get_avg_fps()
        total_frames = len(vr)
        
        # Calculate frame sampling interval
        interval = max(1, round(original_fps / target_fps))
        
        # Generate frame indices to extract
        frame_indices = np.arange(0, total_frames, interval)
        
        # Process each selected frame
        for second, idx in enumerate(frame_indices):
            # Read frame (BGR format from decord)
            bgr_frame = vr[idx].asnumpy()
            
            # Convert BGR to RGB color space
            # rgb_frame = cv2.cvtColor(bgr_frame, cv2.COLOR_BGR2RGB)
            
            # Convert to PIL Image
            image = Image.fromarray(bgr_frame)
            
            filename = os.path.join(output_dir, f"{idx:05d}.png")
            
            if grey:
                image = image.resize(
                    (512, 512),
                    resample=Image.Resampling.LANCZOS  # or Image.BICUBIC / Image.BILINEAR
                )
            # Save with lossless compression (PNG format)
            image.save(
                filename,
                format="PNG",
                optimize=True,     # Enable optimization
                compress_level=0   # Maximum compression (0-9)
            )
            
        print(f"Successfully extracted {len(frame_indices)} frames to {output_dir}")

        return original_fps

    except Exception as e:
        print(f"Frame extraction failed: {str(e)}")
        raise



def get_video_duration_seconds(video_path: Union[str, os.PathLike]) -> float:
    p = str(video_path)
    if not (p.startswith("http://") or p.startswith("https://")):
        if not os.path.exists(p):
            raise FileNotFoundError(f"No such file: {p}")

    vr = VideoReader(p, ctx=cpu(0))
    n_frames = len(vr)
    if n_frames == 0:
        raise ValueError("Empty video (0 frames).")

    try:
        ts = vr.get_frame_timestamp(n_frames - 1)
        if isinstance(ts, (list, tuple, np.ndarray)):
            end_ts = ts[-1]
        else:
            end_ts = ts
        dur = float(end_ts)
        if math.isfinite(dur) and dur > 0:
            return dur
    except Exception:
        pass

    try:
        fps = float(vr.get_avg_fps())
        if fps > 0:
            return n_frames / fps
    except Exception:
        pass

    raise RuntimeError("Failed to determine video duration via decord.")


def format_hhmmss_ms(seconds: float) -> str:
    ms_total = int(round(seconds * 1000))
    h, rem = divmod(ms_total, 3600000)
    m, rem = divmod(rem, 60000)
    s, ms = divmod(rem, 1000)
    return f"{h:02d}:{m:02d}:{s:02d}.{ms:03d}"



def stitch_frames_to_video(image_folder: str, output_video_path: str, fps: int = 30) -> None:
    """
    Stitches a sequence of image frames from a folder into a video file using imageio.

    Args:
        image_folder (str): Path to the directory containing the image frames.
        output_video_path (str): Path to save the output video file (e.g., 'output.mp4').
        fps (int): Frames per second for the output video.
    """
    try:
        import natsort
        images = [img for img in os.listdir(image_folder) if img.endswith(".png")]
        sorted_images = natsort.natsorted(images)
    except ImportError:
        images = [img for img in os.listdir(image_folder) if img.endswith(".png")]
        sorted_images = sorted(images)

    if not sorted_images:
        print(f"not found any images in'{image_folder}' ")
        return

    file_paths = [os.path.join(image_folder, img) for img in sorted_images]

    print(f"start concat {len(file_paths)} ")

    with imageio.get_writer(output_video_path, fps=fps) as writer:
        for file_path in file_paths:
            try:
                image = imageio.imread(file_path)
                writer.append_data(image)
            except Exception as e:
                print(f"warning: jumped frame {file_path}, error: {e}")

    print(f"finished concat, saved: {output_video_path}")



def split_video_by_windows(video_path: str, time_windows: list, output_dir: str = None):
    """
    Split video into segments based on time windows and keep the parts between windows.
    
    Args:
        video_path: Path to input video file
        time_windows: List of time windows in format [[start1,end1],[start2,end2],...] (in seconds)
        output_dir: Directory to save segments (default: same directory as input video)
        
    Returns:
        list: Paths to all created video segments (both in-window and between-window segments)
    """
    if not os.path.isfile(video_path):
        raise FileNotFoundError(f"Video file not found: {video_path}")
        
    if not time_windows:
        raise ValueError("Time windows list cannot be empty")
        
    # Validate time windows
    for window in time_windows:
        if len(window) != 2:
            raise ValueError(f"Invalid time window format: {window}. Expected [start, end]")
        if window[0] >= window[1]:
            raise ValueError(f"Invalid time window: start ({window[0]}) must be before end ({window[1]})")
            
    # Set output directory
    if output_dir is None:
        output_dir = os.path.dirname(video_path)
    os.makedirs(output_dir, exist_ok=True)
    
    # Get video base name without extension
    base_name = os.path.splitext(os.path.basename(video_path))[0]
    
    # Get video duration
    vr = VideoReader(video_path, ctx=cpu(0))
    duration = len(vr) / vr.get_avg_fps()
    del vr
    
    # Sort time windows by start time
    time_windows = sorted(time_windows, key=lambda x: x[0])
    
    # Generate all segments (both in-window and between-window)
    all_segments = []
    in_window_segments = []
    prev_end = 0.0
    
    for i, (start, end) in enumerate(time_windows):
        # Add the segment before this window (if any)
        if start > prev_end:
            output_path = os.path.join(output_dir, f"{base_name}_{prev_end:.1f}-{start:.1f}.mp4")
            cmd = [
                "ffmpeg",
                "-i", video_path,
                "-ss", str(prev_end),
                "-to", str(start),
                "-c", "copy",
                "-y",
                output_path
            ]
            try:
                subprocess.run(cmd, check=True)
                all_segments.append(output_path)
            except subprocess.CalledProcessError as e:
                print(f"Failed to save between-window segment {i}: {e}")
        
        # Add the current window segment
        output_path = os.path.join(output_dir, f"{base_name}_{start:.1f}-{end:.1f}.mp4")
        cmd = [
            "ffmpeg",
            "-i", video_path,
            "-ss", str(start),
            "-to", str(end),
            "-c", "copy",
            "-y",
            output_path
        ]
        try:
            subprocess.run(cmd, check=True)
            all_segments.append(output_path)
            in_window_segments.append(output_path)
        except subprocess.CalledProcessError as e:
            print(f"Failed to split segment {i+1}: {e}")
        
        prev_end = end
    
    # Add the segment after last window (if any)
    if prev_end < duration:
        output_path = os.path.join(output_dir, f"{base_name}_{prev_end:.1f}-{duration:.1f}.mp4")
        cmd = [
            "ffmpeg",
            "-i", video_path,
            "-ss", str(prev_end),
            "-to", str(duration),
            "-c", "copy",
            "-y",
            output_path
        ]
        try:
            subprocess.run(cmd, check=True)
            all_segments.append(output_path)
        except subprocess.CalledProcessError as e:
            print(f"Failed to save final between-window segment: {e}")
            
    return all_segments, in_window_segments


def _storyboard_config_float(key: str, default: float) -> float:
    try:
        return float(get_mcp_section("video_gen").get(key, default))
    except (TypeError, ValueError):
        return float(default)


def _storyboard_duration(value, default: int = 4) -> int:
    try:
        duration = float(value)
    except (TypeError, ValueError):
        duration = default
    min_duration = max(4, _storyboard_config_float("min_duration_seconds", 4))
    max_duration = max(min_duration, _storyboard_config_float("max_duration_seconds", 10))
    return int(round(max(min_duration, min(max_duration, duration))))


def _storyboard_bool(value) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on", "single_take", "single-take"}
    return bool(value)


def _storyboard_text(value) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _storyboard_scene_key(shot: dict) -> str:
    for key in ("generation_unit_id", "scene_id", "continuity_anchor"):
        value = _storyboard_text(shot.get(key)).lower()
        if value:
            return value
    return ""


def _merge_storyboard_text(*parts) -> str:
    merged = []
    seen = set()
    for part in parts:
        text = _storyboard_text(part)
        if not text:
            continue
        normalized = " ".join(text.lower().split())
        if normalized in seen:
            continue
        seen.add(normalized)
        merged.append(text.rstrip("."))
    return ". Then, ".join(merged) + ("." if merged else "")


def _postprocess_storyboard_generation_units(storyboard: dict) -> dict:
    if not isinstance(storyboard, dict) or not isinstance(storyboard.get("shots"), list):
        return storyboard

    max_duration = max(3, _storyboard_config_float("max_duration_seconds", 10))
    merged_shots = []
    for shot in storyboard["shots"]:
        if not isinstance(shot, dict):
            continue
        shot["duration"] = _storyboard_duration(shot.get("duration"))
        if not merged_shots:
            merged_shots.append(shot)
            continue

        previous = merged_shots[-1]
        same_unit = _storyboard_scene_key(previous) and _storyboard_scene_key(previous) == _storyboard_scene_key(shot)
        single_take = _storyboard_bool(previous.get("single_take_preferred")) or _storyboard_bool(shot.get("single_take_preferred"))
        combined_duration = _storyboard_duration(previous.get("duration")) + _storyboard_duration(shot.get("duration"))
        if same_unit and single_take and combined_duration <= max_duration:
            previous["duration"] = combined_duration
            previous["single_take_preferred"] = True
            previous["merged_from_shots"] = [*previous.get("merged_from_shots", [previous.get("id")]), *shot.get("merged_from_shots", [shot.get("id")])]
            previous["plot_correspondence"] = _merge_storyboard_text(previous.get("plot_correspondence"), shot.get("plot_correspondence"))
            previous["setting_description"] = _merge_storyboard_text(previous.get("setting_description"), shot.get("setting_description"))
            previous["static_shot_description"] = _merge_storyboard_text(previous.get("static_shot_description"), shot.get("static_shot_description"))
            previous["start_state"] = previous.get("start_state") or shot.get("start_state")
            previous["end_state"] = shot.get("end_state") or previous.get("end_state")
            previous["duplicate_guard"] = _merge_storyboard_text(previous.get("duplicate_guard"), shot.get("duplicate_guard"))
            previous["onstage_characters"] = list(dict.fromkeys((previous.get("onstage_characters") or []) + (shot.get("onstage_characters") or [])))
        else:
            merged_shots.append(shot)

    current_start = 0
    for index, shot in enumerate(merged_shots, start=1):
        shot["id"] = index
        if "start_time" in shot:
            shot["start_time"] = current_start
        current_start += _storyboard_duration(shot.get("duration"))
        if "end_time" in shot:
            shot["end_time"] = current_start

    storyboard["shots"] = merged_shots
    return storyboard


async def storyboard_generate(user_prompt: str, gentype: str=None) -> dict:
    """
    Transforms a brief story outline into a detailed storyboard, complete with character introductions (including physical characteristics) and descriptions of various scene segments.
    This tool helps in pre-visualizing video narratives.
    
    Args:
        user_prompt: Users' input text, used to generate a video story script.
        
    Returns:
        dict: A dictionary representing the generated storyboard, with the following keys:
              - 'characters' (list): A list of character objects, each containing their physical characteristics, and descriptions.
              - 'shots' (list): A list of shot objects, defining the video sequence.
              - 'style' (str): A concise description of the overall visual style.
    """
    if gentype == "entity2video":
        with open(_prompt_path("prompts/generation/storyboard_gen/entity2video.txt"), "r") as f:
            refine_prompt = f.read()
    else:
        with open(_prompt_path("prompts/generation/storyboard_gen/storyboard_gen.txt"), "r") as f:
            refine_prompt = f.read()
    
    query_content = f"{refine_prompt}\n\n{user_prompt}"

    messages = [
        {"role": "user", "content": query_content}
    ]
    
    response = query_openai(
        api_key=llm_config.get('openai_api_key', None),
        model=llm_config.get('model', 'gpt-5-2025-08-07'),
        base_url=llm_config.get('base_url'),
        messages=messages,
        max_completion_tokens=8192
    )

    response_text = response["content"]
    
    # Extract JSON from markdown code block if present
    import re
    json_match = re.search(r"```json\n(.*)\n```", response_text, re.DOTALL)
    if json_match:
        json_string = json_match.group(1)
    else:
        json_string = response_text # Assume it's pure JSON if no markdown block

    # Parse the JSON response and populate the server_timeline
    try:
        storyboard_data = json.loads(json_string)

        return _postprocess_storyboard_generation_units(storyboard_data)
        
    except json.JSONDecodeError as e:
        logger.error(f"Failed to decode JSON from LLM response: {e}")
        return {"error": f"Failed to parse storyboard: {e}", "raw_response": response_text}
    except Exception as e:
        logger.error(f"Error processing storyboard data: {e}")
        return {"error": f"Error processing storyboard data: {e}", "raw_response": response_text}

def split_video_by_fps(
    video_path: str,
    fps: float,
    clip_max_frames: int
) -> List[np.ndarray]:
    """
    use decord to read video, sample frames at given fps, and split into clips of max clip_max_frames each.
    """
    vr = VideoReader(video_path, ctx=cpu())
    total_frames = len(vr)
    if total_frames == 0:
        return []

    orig_fps = float(vr.get_avg_fps())
    eff_fps = min(fps, orig_fps)

    step = orig_fps / eff_fps
    indices = np.round(np.arange(0, total_frames, step)).astype(np.int64)
    indices = np.clip(indices, 0, total_frames - 1)
    _, unique_pos = np.unique(indices, return_index=True)
    indices = indices[np.sort(unique_pos)]

    if indices.size == 0:
        return []

    clips: List[np.ndarray] = []
    for start in range(0, len(indices), clip_max_frames):
        batch_idx = indices[start:start + clip_max_frames]
        frames_nd = vr.get_batch(batch_idx)
        frames_np = frames_nd.asnumpy()
        clips.append(frames_np)

    return clips



def encode_clips_to_base64(clips: List[np.ndarray], image_format: str = "JPEG") -> List[List[str]]:
    all_clips_base64: List[List[str]] = []

    for clip in clips:
        clip_base64_frames = []
        for frame in clip:
            img = Image.fromarray(frame.astype("uint8"))
            buf = io.BytesIO()
            img.save(buf, format=image_format)
            byte_data = buf.getvalue()
            base64_str = "data:image/{};base64,".format(image_format.lower()) + base64.b64encode(byte_data).decode("utf-8")
            clip_base64_frames.append(base64_str)
        all_clips_base64.append(clip_base64_frames)

    return all_clips_base64

