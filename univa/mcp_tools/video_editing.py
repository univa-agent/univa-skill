import os
import subprocess
from datetime import datetime
from pathlib import Path
from mcp.server.fastmcp import FastMCP

from typing import Optional, List, Dict
import json
import uuid
import shutil
from PIL import Image 

from univa.config.mcp_config import get_mcp_section, get_wavespeed_config
from univa.utils.probing import find_or_sample_clips, VLMGenerator
from univa.utils.wavespeed_api import runway_video_editing, vace_api
from univa.utils.volcengine_api import video_edit_generate as ark_video_edit

from univa.mcp_tools.base import ToolResponse, setup_logger


video_editing_config = get_mcp_section("video_editing")


def _redact_config(value):
    if isinstance(value, dict):
        redacted = {}
        for key, item in value.items():
            if any(token in key.lower() for token in ("api", "key", "token", "secret")):
                redacted[key] = "***REDACTED***" if item else item
            else:
                redacted[key] = _redact_config(item)
        return redacted
    if isinstance(value, list):
        return [_redact_config(item) for item in value]
    return value


# Configure logging
log_dir = "logs"
logger = setup_logger(__name__, "logs/mcp_tools", "video_editing.log")
logger.info("Loaded video_editing_config: %s", _redact_config(video_editing_config))


def _get_editing_provider():
    """Return (provider_name, api_key, style_model, repaint_model, base_url, provider_config)."""
    provider = video_editing_config.get("provider", "wavespeed")

    if provider == "volcengine_ark":
        ark_cfg = video_editing_config.get("volcengine_ark", {})
        return (
            provider,
            ark_cfg.get("api_key", ""),
            ark_cfg.get("style_transfer_model"),
            ark_cfg.get("repainting_model"),
            ark_cfg.get("base_url"),
            ark_cfg,
        )

    wavespeed_cfg = get_wavespeed_config(video_editing_config)
    return (
        "wavespeed",
        wavespeed_cfg.get("api_key", ""),
        wavespeed_cfg.get("style_transfer_model"),
        wavespeed_cfg.get("repainting_model"),
        wavespeed_cfg.get("base_url"),
        wavespeed_cfg,
    )


def _local_vace_config() -> dict:
    return video_editing_config.get("local_vace", {}) or {}


def _vace_python() -> str:
    return _local_vace_config().get("python", "python")


def _vace_workdir() -> str | None:
    return _local_vace_config().get("workdir") or None


def _vace_temp_dir(datetime_now: str) -> str:
    base = _local_vace_config().get("temp_dir", "temp")
    return os.path.abspath(os.path.join(base, datetime_now))


def _vace_results_dir(datetime_now: str) -> str:
    base = _local_vace_config().get("results_dir", "results")
    return os.path.abspath(os.path.join(base, datetime_now))


# Create an MCP server
mcp = FastMCP("Video_Edit_Server")



# @mcp.tool()
def swap_object_tool(
    prompt: str,
    video: str,
    image: str,
    label: str
) -> dict:
    """
    Swaps a specified object in a target video with the corresponding object from a reference image.

    This function identifies all instances of a given object class (e.g., "person", "car") in the input video and replaces them with the object provided in the reference image, guided by a textual prompt.

    Args:
        prompt (str): A textual description guiding the swapping and generation process.
        video (str): Path to the target input video file where objects will be replaced.
        image (str): Path to the reference image file containing the object to swap in.
        label (str): The class name of the object to be swapped (e.g., "person", "face", "cat").

    Returns:
        dict: A dictionary containing the operation's success status and results.
              - 'success' (bool): True if the operation completed successfully, False otherwise.
              - 'output_path' (str, optional): Path to the generated video if successful.
              - 'error' (str, optional): An error message if the operation failed.
              
    Example Usage:
        swap_anything_tool(
            prompt="a man with a beard",
            video="assets/videos/input_person.mp4",
            image="assets/images/bearded_man_face.jpg",
            label="person"
        )
    """

    mode: str = "label,salientbboxtrack",
    base_seed: int = None,
    frame_num: int = 81,
    size: str = None,
    sample_steps: int = 50,
    maskaug_mode: str = "bbox",
    maskaug_ratio: float = 0.3,
    skip_preprocess: bool = False,

    if not all([prompt, video, image, label, mode]):
        return {
            'success': False,
            'error': "Missing required arguments. 'prompt', 'video', 'image', 'label', and 'mode' are all required."
        }

    task = "swap_anything"
    datetime_now = datetime.now().strftime("%Y%m%d_%H%M%S")
    preprocessed_files = {}
    preprocess_cmd_str = None

    if not skip_preprocess:
        pre_save_dir = _vace_temp_dir(datetime_now)

        preprocess_cmd = [
            _vace_python(), "vace/vace_preproccess.py",
            "--task", task,
            "--video", video,
            "--image", image,
            "--label", label,
            "--mode", mode,
            "--pre_save_dir", pre_save_dir
        ]

        if maskaug_mode:
            preprocess_cmd.extend(["--maskaug_mode", maskaug_mode])
        if maskaug_ratio != 0.1:
            preprocess_cmd.extend(["--maskaug_ratio", str(maskaug_ratio)])
        
        preprocess_cmd_str = ' '.join(preprocess_cmd)
        preprocess_log = os.path.join(log_dir, f"vace_preprocess_{task}_{datetime_now}.log")
        
        try:
            with open(preprocess_log, "w") as log_file:
                log_file.write(f"Executing Preprocessing Command:\n{preprocess_cmd_str}\n\n")
                result = subprocess.run(
                    preprocess_cmd,
                    cwd=_vace_workdir(),
                    stdout=log_file,
                    stderr=subprocess.STDOUT,
                    text=True,
                    check=True
                )

            processed_dir = Path(pre_save_dir)
            if processed_dir.exists():
                video_files = list(processed_dir.glob("src_video*.mp4"))
                mask_files = list(processed_dir.glob("src_mask*.mp4"))
                ref_images = list(processed_dir.glob("src_ref_image*.png"))
                
                if video_files:
                    preprocessed_files['src_video'] = str(max(video_files, key=os.path.getctime))
                if mask_files:
                    preprocessed_files['src_mask'] = str(max(mask_files, key=os.path.getctime))
                if ref_images:
                    preprocessed_files['src_ref_images'] = [str(f) for f in sorted(ref_images)]

        except (subprocess.CalledProcessError, FileNotFoundError) as e:
            error_message = f"Preprocessing failed. See log for details: {preprocess_log}. Error: {str(e)}"
            return {
                'success': False,
                'error': error_message,
                'log_files': {'preprocess': preprocess_log},
                'command': {'preprocess': preprocess_cmd_str}
            }
        except Exception as e:
            return {'success': False, 'error': f"An unexpected error occurred during preprocessing: {str(e)}"}

    save_dir = _vace_results_dir(datetime_now)

    inference_cmd = [
        _vace_python(), "vace/vace_wan_inference.py",
        "--prompt", prompt,
        "--ckpt_dir", video_editing_config.get("model_path"),
        "--save_dir", save_dir,
    ]

    if 'src_video' in preprocessed_files:
        inference_cmd.extend(["--src_video", preprocessed_files['src_video']])
    if 'src_mask' in preprocessed_files:
        inference_cmd.extend(["--src_mask", preprocessed_files['src_mask']])
    if 'src_ref_images' in preprocessed_files:
        ref_images_str = ",".join(preprocessed_files['src_ref_images'])
        inference_cmd.extend(["--src_ref_images", ref_images_str])

    if base_seed is not None:
        inference_cmd.extend(["--base_seed", str(base_seed)])
    if frame_num != 81:
        inference_cmd.extend(["--frame_num", str(frame_num)])
    if size:
        inference_cmd.extend(["--size", size])
    if sample_steps != 50:
        inference_cmd.extend(["--sample_steps", str(sample_steps)])
        
    inference_cmd_str = ' '.join(inference_cmd)
    inference_log = os.path.join(log_dir, f"vace_inference_{task}_{datetime_now}.log")
    
    try:
        with open(inference_log, "w") as log_file:
            log_file.write(f"Executing Inference Command:\n{inference_cmd_str}\n\n")
            result = subprocess.run(
                inference_cmd,
                cwd=_vace_workdir(),
                stdout=log_file,
                stderr=subprocess.STDOUT,
                text=True,
                check=True
            )

        time = datetime.now().strftime("%m%d%H%M%S")
        output_path_path = os.path.join(save_dir, f"{time}_output.mp4")

        return {
            'success': True,
            'output_path': output_path_path
        }
            
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        error_message = f"Inference failed. See log for details: {inference_log}. Error: {str(e)}"
        return {
            'success': False,
            'error': error_message
        }
    except Exception as e:
        return {'success': False, 'error': f"An unexpected error occurred during inference: {str(e)}"}

@mcp.tool()
def depth_modify(
    prompt: str,
    video: str
) -> dict:
    """
    Based on a text prompt, use depth information to edit or replace the foreground or background of a video.

    This function is specifically designed for video editing tasks that require distinguishing between foreground and background. It is suitable for intelligent video editing, such as replacing the background or changing the foreground color, while leaving the other content unchanged.

    Args:
        prompt (str): Text describing the video editing instructions. This is key to instructing the AI on how to modify the video.
        For example: "Change the background to a snowy mountain" or "Keep the characters the same, but change the background to a cyberpunk style."
        video (str): The path to the original video file to be edited. For example: 'data/input_video.mp4'.

    Returns:
        dict: A dictionary containing the result of the operation.
        - If successful, the format is: {'success': True, 'output_path': 'path/to/output.mp4'}
        - If failed, the format may be: {'success': False, 'error': 'error message', 'log_file': 'path/to/log.log'}
    """
    model = video_editing_config.get("style_transfer")

    if model == "vace":

        task = "depth"
        
        datetime_now = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        preprocessed_files = {}
        pre_save_dir = _vace_temp_dir(datetime_now)
        preprocess_cmd = [
            _vace_python(),
            "vace/vace_preproccess.py",
            "--task", task,
            "--video", video,
            "--pre_save_dir", pre_save_dir
        ]
            
        # Execute preprocessing
        preprocess_log = os.path.join(log_dir, f"vace_preprocess_{task}_{datetime_now}.log")
        try:
            with open(preprocess_log, "w") as log_file:
                log_file.write("Preprocessing command: " + ' '.join(preprocess_cmd) + "\n")
                result = subprocess.run(
                    preprocess_cmd,
                    cwd=_vace_workdir(),
                    stdout=log_file,
                    stderr=subprocess.STDOUT,
                    text=True
                )
                
            if result.returncode != 0:
                return {
                    'success': False,
                    'error': f"Preprocessing failed with return code {result.returncode}",
                    'log_file': preprocess_log
                }
                    
            # Find preprocessed files in ./processed/
            processed_dir = Path(pre_save_dir)
            if processed_dir.exists():
                # Get latest files
                video_files = list(processed_dir.glob("src_video*.mp4"))
                
                if video_files:
                    preprocessed_files['src_video'] = str(max(video_files, key=os.path.getctime))
                        
        except Exception as e:
            return {
                'success': False,
                'error': f"Preprocessing error: {str(e)}"
            }
        
        # Step 2: Inference
        if not prompt:
            return {
                'success': False,
                'error': "Prompt is required for inference"
            }
        
        # Build inference command
        inference_cmd = [
            _vace_python(),
            "vace/vace_wan_inference.py",
            "--prompt", prompt,
            "--src_video", preprocessed_files['src_video'],
            "--ckpt_dir", video_editing_config.get("model_path"),
            "--save_dir", _vace_results_dir(datetime_now),
        ]
        
        # Execute inference
        inference_log = os.path.join(log_dir, f"vace_inference_{task}_{datetime_now}.log")
        try:
            with open(inference_log, "w") as log_file:
                result = subprocess.run(
                    inference_cmd,
                    cwd=_vace_workdir(),
                    stdout=log_file,
                    stderr=subprocess.STDOUT,
                    text=True
                )
                
            if result.returncode == 0:
                return {
                    'success': True,
                    'output_path': os.path.abspath(os.path.join(_vace_results_dir(datetime_now), "out_video.mp4"))
                }
            else:
                return {
                    'success': False,
                    'error': f"Inference failed with return code {result.returncode}"
                }

        except Exception as e:
            return {
                'success': False,
                'error': f"Inference error: {str(e)}"
            }
    else:
        provider, api_key, style_model, repaint_model, base_url, provider_cfg = _get_editing_provider()
        if provider == "volcengine_ark":
            res = ark_video_edit(api_key, prompt, video, model=style_model, base_url=base_url)
        else:
            res = runway_video_editing(api_key, prompt, video, model=style_model, provider=provider_cfg.get("style_transfer_provider"), base_url=base_url)
        if isinstance(res, dict) and res.get('output_path'):
            res['output_path'] = os.path.abspath(res['output_path'])
        return res


# @mcp.tool()
def recolor(
    prompt: str,
    video: str
) -> dict:
    """
    Recolorize a video or modify the color of specific areas based on a text prompt, allowing for overall stylistic recoloring.

    Args:
        prompt (str): Text describing the color editing instructions. This is key to instructing the AI on how to colorize.
        For example: "Turn her skirt red" or "Turn the entire scene into a retro sepia tone."
        video (str): The path to the original video file to be edited. For example: 'data/input_video.mp4'.

    Returns:
        dict: A dictionary containing the results of the operation.
        - If successful, the format is: {'success': True, 'output_path': 'path/to/output.mp4'}
        - If failed, the format may be:
        {'success': False, 'error': 'error message', 'log_file': 'path/to/log.log'}
    """

    task = "gray"
    
    datetime_now = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    preprocessed_files = {}
    pre_save_dir = _vace_temp_dir(datetime_now)
    preprocess_cmd = [
        _vace_python(),
        "vace/vace_preproccess.py",
        "--task", task,
        "--video", video,
        "--pre_save_dir", pre_save_dir
    ]
        
    # Execute preprocessing
    preprocess_log = os.path.join(log_dir, f"vace_preprocess_{task}_{datetime_now}.log")
    try:
        with open(preprocess_log, "w") as log_file:
            log_file.write("Preprocessing command: " + ' '.join(preprocess_cmd) + "\n")
            result = subprocess.run(
                preprocess_cmd,
                cwd=_vace_workdir(),
                stdout=log_file,
                stderr=subprocess.STDOUT,
                text=True
            )
            
        if result.returncode != 0:
            return {
                'success': False,
                'error': f"Preprocessing failed with return code {result.returncode}",
                'log_file': preprocess_log
            }
                
        # Find preprocessed files in ./processed/
        processed_dir = Path(pre_save_dir)
        if processed_dir.exists():
            # Get latest files
            video_files = list(processed_dir.glob("src_video*.mp4"))
            
            if video_files:
                preprocessed_files['src_video'] = str(max(video_files, key=os.path.getctime))
                    
    except Exception as e:
        return {
            'success': False,
            'error': f"Preprocessing error: {str(e)}"
        }
    
    # Step 2: Inference
    if not prompt:
        return {
            'success': False,
            'error': "Prompt is required for inference"
        }
    
    # Build inference command
    inference_cmd = [
        _vace_python(),
        "vace/vace_wan_inference.py",
        "--prompt", prompt,
        "--src_video", preprocessed_files['src_video'],
        "--ckpt_dir", video_editing_config.get("model_path"),
        "--save_dir", _vace_results_dir(datetime_now),
    ]
    
    # Execute inference
    inference_log = os.path.join(log_dir, f"vace_inference_{task}_{datetime_now}.log")
    try:
        with open(inference_log, "w") as log_file:
            result = subprocess.run(
                inference_cmd,
                cwd=_vace_workdir(),
                stdout=log_file,
                stderr=subprocess.STDOUT,
                text=True
            )
            
        if result.returncode == 0:
            return {
                'success': True,
                'output_path': os.path.abspath(os.path.join(_vace_results_dir(datetime_now), "out_video.mp4"))
            }
        else:
            return {
                'success': False,
                'error': f"Inference failed with return code {result.returncode}"
            }
            
    except Exception as e:
        return {
            'success': False,
            'error': f"Inference error: {str(e)}"
        }

@mcp.tool()
def pose_reference(
    prompt: str,
    image: str=None,
    video: str=None
) -> dict:
    """
    Based on a text prompt, transfer the motions of a person in a video to a new character while preserving the original motion sequence. This function implements the pose transfer functionality, resulting in a new character performing the motions from the old video.

    Args:
        prompt (str): Describes the look and style of the new character you want to generate. The AI will apply the motions from the original video to this new character.
        For example: "A dancing astronaut", "A walking stormtrooper".
        image (str): The path to the source image file providing the pose reference. The image should contain one or more people whose poses will be extracted. For example: 'data/dancing_person.mp4'.
        video (str): The path to the source video file providing the motion reference. The video should contain one or more people whose poses will be extracted. For example: 'data/dancing_person.mp4'.

    Returns:
        dict: A dictionary containing the results of the operation.
        - If successful, the format is: {'success': True, 'output_path': 'path/to/output.mp4'}
        - If failed, the format may be: {'success': False, 'error': 'error message', 'log_file': 'path/to/log.log'}
    """
    model = video_editing_config.get("pose_reference")

    if model == "vace":
        task = "pose"
        
        datetime_now = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        preprocessed_files = {}
        pre_save_dir = _vace_temp_dir(datetime_now)
        preprocess_cmd = [
            _vace_python(),
            "vace/vace_preproccess.py",
            "--task", task,
            "--video", video,
            "--pre_save_dir", pre_save_dir
        ]
            
        # Execute preprocessing
        preprocess_log = os.path.join(log_dir, f"vace_preprocess_{task}_{datetime_now}.log")
        try:
            with open(preprocess_log, "w") as log_file:
                log_file.write("Preprocessing command: " + ' '.join(preprocess_cmd) + "\n")
                result = subprocess.run(
                    preprocess_cmd,
                    cwd=_vace_workdir(),
                    stdout=log_file,
                    stderr=subprocess.STDOUT,
                    text=True
                )
                
            if result.returncode != 0:
                return {
                    'success': False,
                    'error': f"Preprocessing failed with return code {result.returncode}",
                    'log_file': preprocess_log
                }
                    
            # Find preprocessed files in ./processed/
            processed_dir = Path(pre_save_dir)
            if processed_dir.exists():
                # Get latest files
                video_files = list(processed_dir.glob("src_video*.mp4"))
                
                if video_files:
                    preprocessed_files['src_video'] = str(max(video_files, key=os.path.getctime))
                        
        except Exception as e:
            return {
                'success': False,
                'error': f"Preprocessing error: {str(e)}"
            }
        
        # Step 2: Inference
        if not prompt:
            return {
                'success': False,
                'error': "Prompt is required for inference"
            }
        
        # Build inference command
        inference_cmd = [
            _vace_python(),
            "vace/vace_wan_inference.py",
            "--prompt", prompt,
            "--src_video", preprocessed_files['src_video'],
            "--ckpt_dir", video_editing_config.get("model_path"),
            "--save_dir", _vace_results_dir(datetime_now),
        ]
        
        # Execute inference
        inference_log = os.path.join(log_dir, f"vace_inference_{task}_{datetime_now}.log")
        try:
            with open(inference_log, "w") as log_file:
                result = subprocess.run(
                    inference_cmd,
                    cwd=_vace_workdir(),
                    stdout=log_file,
                    stderr=subprocess.STDOUT,
                    text=True
                )
                
            if result.returncode == 0:
                return {
                    'success': True,
                    'output_path': os.path.abspath(os.path.join(_vace_results_dir(datetime_now), "out_video.mp4"))
                }
            else:
                return {
                    'success': False,
                    'error': f"Inference failed with return code {result.returncode}"
                }
                
        except Exception as e:
            return {
                'success': False,
                'error': f"Inference error: {str(e)}"
            }
    else:
        provider, api_key, style_model, repaint_model, base_url, provider_cfg = _get_editing_provider()
        if provider == "volcengine_ark":
            res = ark_video_edit(api_key, prompt, video if video else image,
                                 model=style_model, base_url=base_url)
        else:
            res = vace_api(api_key, prompt, image, video, task="pose", model=provider_cfg.get("pose_model"), provider=provider_cfg.get("pose_provider"), base_url=base_url)
        if isinstance(res, dict) and res.get('output_path'):
            res['output_path'] = os.path.abspath(res['output_path'])
        return res


@mcp.tool()
def style_transfer(
    prompt: str,
    video: str
) -> dict:
    """
    Based on a text prompt, converts a video into a specified artistic style, achieving style transfer.

    This function extracts edges and contours to generate a line drawing video. This process retains the core structure and dynamic information of the original video, but removes its original colors and textures, providing an ideal structural foundation for applying the new style. It then "renders" the line drawing video, generating a video with the same content and dynamics as the original video, but with a completely new visual style.

    Args:
        prompt (str): Text describing the target artistic style. This is key to guiding the AI on which style to apply.
        For example: "Van Gogh Starry Night Style", "Transformed into a Watercolor Animation", "Cyberpunk City".
        video (str): The path to the original video file to be style transferred. For example: 'data/input_video.mp4'.

    Returns:
        dict: A dictionary containing the results of the operation.
        - If successful, the format is: {'success': True, 'output_path': 'path/to/output.mp4'}
        - If failed, the format may be: 
        {'success': False, 'error': 'error message', 'log_file': 'path/to/log.log'} 
    """
    model = video_editing_config.get("style_transfer")

    if model == "vace":
        task = "scribble"
        
        datetime_now = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        preprocessed_files = {}
        pre_save_dir = _vace_temp_dir(datetime_now)
        preprocess_cmd = [
            _vace_python(),
            "vace/vace_preproccess.py",
            "--task", task,
            "--video", video,
            "--pre_save_dir", pre_save_dir
        ]
            
        # Execute preprocessing
        preprocess_log = os.path.join(log_dir, f"vace_preprocess_{task}_{datetime_now}.log")
        try:
            with open(preprocess_log, "w") as log_file:
                log_file.write("Preprocessing command: " + ' '.join(preprocess_cmd) + "\n")
                result = subprocess.run(
                    preprocess_cmd,
                    cwd=_vace_workdir(),
                    stdout=log_file,
                    stderr=subprocess.STDOUT,
                    text=True
                )
                
            if result.returncode != 0:
                return {
                    'success': False,
                    'error': f"Preprocessing failed with return code {result.returncode}",
                    'log_file': preprocess_log
                }
                    
            # Find preprocessed files in ./processed/
            processed_dir = Path(pre_save_dir)
            if processed_dir.exists():
                # Get latest files
                video_files = list(processed_dir.glob("src_video*.mp4"))
                
                if video_files:
                    preprocessed_files['src_video'] = str(max(video_files, key=os.path.getctime))
                        
        except Exception as e:
            return {
                'success': False,
                'error': f"Preprocessing error: {str(e)}"
            }
        
        # Step 2: Inference
        if not prompt:
            return {
                'success': False,
                'error': "Prompt is required for inference"
            }
        
        # Build inference command
        inference_cmd = [
            _vace_python(),
            "vace/vace_wan_inference.py",
            "--prompt", prompt,
            "--src_video", preprocessed_files['src_video'],
            "--ckpt_dir", video_editing_config.get("model_path"),
            "--save_dir", _vace_results_dir(datetime_now),
        ]
        
        # Execute inference
        inference_log = os.path.join(log_dir, f"vace_inference_{task}_{datetime_now}.log")
        try:
            with open(inference_log, "w") as log_file:
                result = subprocess.run(
                    inference_cmd,
                    cwd=_vace_workdir(),
                    stdout=log_file,
                    stderr=subprocess.STDOUT,
                    text=True
                )
                
            if result.returncode == 0:
                return {
                    'success': True,
                    'output_path': os.path.abspath(os.path.join(_vace_results_dir(datetime_now), "out_video.mp4"))
                }
            else:
                return {
                    'success': False,
                    'error': f"Inference failed with return code {result.returncode}"
                }
                
        except Exception as e:
            return {
                'success': False,
                'error': f"Inference error: {str(e)}"
            }
    else:
        provider, api_key, style_model, repaint_model, base_url, provider_cfg = _get_editing_provider()
        if provider == "volcengine_ark":
            res = ark_video_edit(api_key, prompt, video, model=style_model, base_url=base_url)
        else:
            res = runway_video_editing(api_key, prompt, video, model=style_model, provider=provider_cfg.get("style_transfer_provider"), base_url=base_url)
        if isinstance(res, dict) and res.get('output_path'):
            res['output_path'] = os.path.abspath(res['output_path'])
        return res


@mcp.tool()
def repainting(
    prompt: str,
    video: str,
    label: str=None
) -> dict:
    """
    Partially repaint or replace a specific object in a video, changing its appearance or transforming it into something entirely new based on a text prompt.

    This function implements video inpainting or object replacement by first calling the `label` parameter to identify and locate a specific object in the video (e.g., "cat," "car"). The script generates a precise dynamic mask for the identified object while preserving the original video. This mask marks the area to be edited. Next, it fills in the content described in `prompt`, modifying or completely replacing the original object and ensuring that the new content blends seamlessly with the rest of the video.

    Args:
        prompt (str): Text describing what new content you want to generate in the specified area. This is key to guiding the AI's creation. Examples: "A cat in armor," "A futuristic flying car."
        video (str): The path to the original video file to be edited. Example: 'data/cat_video.mp4'.
        label (str): A text label identifying the target object to be replaced or modified in the video. Example: "cat," "cat", "dog".

    Returns:
    dict: A dictionary containing the results of the operation.
        - If successful, the format may be: {'success': True, 'output_path': 'path/to/output.mp4'}
        - If failed, the format may be:
        {'success': False, 'error': 'error message', 'log_file': 'path/to/log.log'}
    """
    model = video_editing_config.get("repainting")

    if model == "vace":
        datetime_now = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Step 1: Preprocessing (if needed)
        preprocessed_files = {}
        task = "inpainting"
        # Build preprocessing command
        pre_save_dir = _vace_temp_dir(datetime_now)
        # python vace/vace_preproccess.py --task inpainting --mode label --label cat --video assets/videos/test.mp4
        preprocess_cmd = [
            _vace_python(),
            "vace/vace_preproccess.py",
            "--task", task,
            "--video", video,
            "--mode", "label",
            "--label", label,
            "--pre_save_dir", pre_save_dir
        ]
        
        # Execute preprocessing
        preprocess_log = os.path.join(log_dir, f"vace_preprocess_{task}_{datetime_now}.log")
        try:
            with open(preprocess_log, "w") as log_file:
                log_file.write("Preprocessing command: " + ' '.join(preprocess_cmd) + "\n")
                result = subprocess.run(
                    preprocess_cmd,
                    cwd=_vace_workdir(),
                    stdout=log_file,
                    stderr=subprocess.STDOUT,
                    text=True
                )
                
            if result.returncode != 0:
                return {
                    'success': False,
                    'error': f"Preprocessing failed with return code {result.returncode}"
                }
                
            # Find preprocessed files in ./processed/
            processed_dir = Path(pre_save_dir)
            if processed_dir.exists():
                # Get latest files
                video_files = list(processed_dir.glob("src_video*.mp4"))
                mask_files = list(processed_dir.glob("src_mask*.mp4"))
                
                if video_files:
                    preprocessed_files['src_video'] = str(max(video_files, key=os.path.getctime))
                if mask_files:
                    preprocessed_files['src_mask'] = str(max(mask_files, key=os.path.getctime))
                    
        except Exception as e:
            return {
                'success': False,
                'error': f"Preprocessing error: {str(e)}"
            }
        
        # Step 2: Inference
        if not prompt:
            return {
                'success': False,
                'error': "Prompt is required for inference"
            }
        
        # Build inference command
        inference_cmd = [
            _vace_python(),
            "vace/vace_wan_inference.py",
            "--prompt", prompt,
            "--ckpt_dir", video_editing_config.get("model_path"),
            "--save_dir", _vace_results_dir(datetime_now),
        ]

        # Add preprocessed files
        if 'src_video' in preprocessed_files:
            inference_cmd.extend(["--src_video", preprocessed_files['src_video']])
        if 'src_mask' in preprocessed_files:
            inference_cmd.extend(["--src_mask", preprocessed_files['src_mask']])
        
        # Execute inference
        inference_log = os.path.join(log_dir, f"vace_inference_{task}_{datetime_now}.log")
        try:
            with open(inference_log, "w") as log_file:
                result = subprocess.run(
                    inference_cmd,
                    cwd=_vace_workdir(),
                    stdout=log_file,
                    stderr=subprocess.STDOUT,
                    text=True
                )
                
            if result.returncode == 0:
                return {
                    'success': True,
                    'output_path': os.path.abspath(os.path.join(_vace_results_dir(datetime_now), "out_video.mp4"))
                }
            else:
                return {
                    'success': False,
                    'error': f"Inference failed with return code {result.returncode}"
                }
                
        except Exception as e:
            return {
                'success': False,
                'error': f"Inference error: {str(e)}"
            }
    else:
        provider, api_key, style_model, repaint_model, base_url, provider_cfg = _get_editing_provider()
        if provider == "volcengine_ark":
            res = ark_video_edit(api_key, prompt, video, model=repaint_model, base_url=base_url)
        else:
            res = runway_video_editing(api_key, prompt, video, model=repaint_model, provider=provider_cfg.get("repainting_provider"), base_url=base_url)
        if isinstance(res, dict) and res.get('output_path'):
            res['output_path'] = os.path.abspath(res['output_path'])
        return res




# @mcp.tool()
def long_video_edit(
    video: str,
    task: str,
    edit_prompt: str,
    probe_prompt: Optional[str] = None,
    clip_granularity_s: float = 5.0,
    frames_strategy: str = "first_mid_last",
    step_ratio: float = 0.5,
    score_threshold: float = 0.6,
    top_k: Optional[int] = None,
    max_windows: Optional[int] = None,
    # task-specific
    label: Optional[str] = None,   # required for 'repainting' and 'swap'
    image: Optional[str] = None,   # required for 'swap'
    reencode_slices: bool = True   # re-encode slices when cutting to avoid keyframe issues
) -> dict:
    """
    Automatically edits an arbitrarily long video by first *probing* for relevant clips
    and then applying one of the existing VACE tools to each clip. Finally, all edited
    clips are concatenated into a single output video.

    This tool uses `utils/probing.py::find_or_sample_clips` to locate candidate windows
    based on a probing prompt (handled by a VLM generator). Each retained window is
    cut out with ffmpeg and processed by one of the registered VACE tools:
    `repainting`, `swap`, `depth`, `recolor`, `pose`, or `style`.

    Args:
        video (str): Path to the long input video.
        task (str): Which VACE editing tool to use. One of:
            {'repainting', 'swap', 'depth', 'recolor', 'pose', 'style'}.
        edit_prompt (str): Text instruction passed to the selected VACE tool for editing.
        probe_prompt (Optional[str]): Text instruction for *probing* (clip finding). If None,
            `edit_prompt` is used for probing as well.

        clip_granularity_s (float, optional): Window length (in seconds) for probing. Default: 5.0.
        frames_strategy (str, optional): Frame sampling strategy for probing. One of:
            - "first_mid_last" (default)
            - "uniform_N"       e.g., "uniform_5"
            - "every_N_sec"     e.g., "every_2_sec"
        step_ratio (float, optional): Sliding-window step as a fraction of `clip_granularity_s`
            (e.g., 0.5 means 50% overlap). Default: 0.5.
        score_threshold (float, optional): Keep windows whose normalized score >= this threshold
            (0.0–1.0). Default: 0.6.
        top_k (Optional[int], optional): If set, keep only the top-K highest-scoring windows.
        max_windows (Optional[int], optional): Hard cap on the number of windows to evaluate.

        label (Optional[str], optional): Target object class name (e.g., "car", "person").
            Required for tasks 'repainting' and 'swap'.
        image (Optional[str], optional): Path to the reference image used by 'swap'.
            Required when `task == 'swap'`.
        reencode_slices (bool, optional): If True, re-encode each cut segment to avoid keyframe
            boundary artifacts; if False, use stream copy (faster but less robust). Default: True.

    Returns:
        dict: A result dict aligned with other tools in this server.
            - 'success' (bool): True if the operation completed successfully, False otherwise.
            - 'output_path' (str, optional): Path to the merged, edited video when successful.
            - 'error' (str, optional): Error message when the operation fails.

    Example Usage:
        long_video_edit(
            video="/path/to/long_movie.mp4",
            task="repainting",
            probe_prompt="a person entering a red car",
            edit_prompt="turn the car blue, realistic",
            label="car",
            clip_granularity_s=5.0,
            frames_strategy="uniform_5",
            top_k=5
        )
    """
    # Use global config/log_dir if available; fall back to sane defaults.
    _globals = globals()
    _config = _globals.get("config", {}) or {}
    _log_dir = _globals.get("log_dir", "logs")
    os.makedirs(_log_dir, exist_ok=True)

    # Unify save directory and log file naming with existing tools.
    datetime_now = datetime.now().strftime("%Y%m%d_%H%M%S")
    save_dir = _vace_results_dir(datetime_now)
    os.makedirs(save_dir, exist_ok=True)
    inference_log = os.path.join(_log_dir, f"vace_inference_long_{datetime_now}.log")

    try:
        # ------------ Validate inputs ------------
        if not os.path.exists(video):
            return {'success': False, 'error': f"Video not found: {video}"}

        task = (task or "").lower().strip()
        if task not in {'repainting', 'swap', 'depth', 'recolor', 'pose', 'style'}:
            return {'success': False, 'error': f"Unsupported task: {task}"}

        if not edit_prompt:
            return {'success': False, 'error': "Parameter 'edit_prompt' cannot be empty."}

        if task == 'repainting' and not label:
            return {'success': False, 'error': "Task 'repainting' requires 'label'."}
        if task == 'swap' and (not label or not image):
            return {'success': False, 'error': "Task 'swap' requires both 'label' and 'image'."}

        probe_text = probe_prompt or edit_prompt

        # ------------ Build a VLM generator (optional external command) ------------
        vlm_cfg = (_config.get('video_editing', {}) or {}).get('video_long', {}) or {}
        vlm_cmd_tmpl: Optional[str] = vlm_cfg.get('vlm_cmd')  # e.g., "python utils/vlm_infer.py --images_dir {images_dir} --prompt {prompt}"

        def _vlm_subprocess(images: List[Image.Image], prompt: str) -> str:
            frames_dir = Path(save_dir) / f"vlm_frames_{uuid.uuid4().hex[:6]}"
            frames_dir.mkdir(parents=True, exist_ok=True)
            try:
                for i, im in enumerate(images):
                    im.save(frames_dir / f"frame_{i:03d}.jpg", quality=90)
                if vlm_cmd_tmpl:
                    cmd = vlm_cmd_tmpl.format(images_dir=str(frames_dir), prompt=json.dumps(prompt))
                    proc = subprocess.run(cmd, shell=True, capture_output=True, text=True)
                    out = (proc.stdout or "").strip() or (proc.stderr or "").strip()
                    return out if out else "UNCERTAIN"
                # Fallback when no VLM configured
                return "YES"
            finally:
                shutil.rmtree(frames_dir, ignore_errors=True)

        vlm: VLMGenerator = _vlm_subprocess

        # ------------ Probing phase ------------
        with open(inference_log, "w") as log_file:
            log_file.write(
                f"[LongEdit] Probing with clip_granularity={clip_granularity_s}, "
                f"frames_strategy={frames_strategy}, step_ratio={step_ratio}, "
                f"score_threshold={score_threshold}, top_k={top_k}, max_windows={max_windows}\n"
            )

        results = find_or_sample_clips(
            video=video,
            clip_granularity_s=clip_granularity_s,
            vlm=vlm,
            prompt=probe_text,
            mode="probe",
            frames_strategy=frames_strategy,
            step_ratio=step_ratio,
            score_threshold=score_threshold,
            top_k=top_k,
            max_windows=max_windows
        )

        with open(inference_log, "a") as log_file:
            compact = [{'time': r['time'], 'score': r.get('score')} for r in results]
            log_file.write(f"[LongEdit] Probe results: {json.dumps(compact)}\n")

        if not results:
            with open(inference_log, "a") as log_file:
                log_file.write("[LongEdit] No relevant clips found.\n")
            return {
                'success': False,
                'error': f"No relevant clips found by probing. See log for details: {inference_log}"
            }

        # ------------ Helper: cut clips with ffmpeg ------------
        def _ffmpeg_cut(src_path: str, start: float, end: float) -> str:
            seg_dir = os.path.join(save_dir, "clips")
            os.makedirs(seg_dir, exist_ok=True)
            seg_name = f"clip_{start:.2f}_{end:.2f}.mp4".replace(".", "_")
            out_path = os.path.join(seg_dir, seg_name)
            if reencode_slices:
                cmd = [
                    "ffmpeg", "-y",
                    "-ss", f"{start:.3f}", "-to", f"{end:.3f}",
                    "-i", src_path,
                    "-c:v", "libx264", "-preset", "fast", "-crf", "18",
                    "-c:a", "aac",
                    out_path
                ]
            else:
                cmd = [
                    "ffmpeg", "-y",
                    "-ss", f"{start:.3f}", "-to", f"{end:.3f}",
                    "-i", src_path,
                    "-c", "copy",
                    out_path
                ]
            with open(inference_log, "a") as log_file:
                log_file.write("Executing Inference Command:\n" + " ".join(cmd) + "\n\n")
            subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            return out_path

        # ------------ Edit each retained clip using the selected VACE tool ------------
        edited_paths: List[str] = []
        for r in results:
            start_s, end_s = r["time"]
            clip_path = _ffmpeg_cut(video, float(start_s), float(end_s))

            if task == 'repainting':
                res = repainting(prompt=edit_prompt, video=clip_path, label=label)  # type: ignore
            elif task == 'swap':
                res = swap_object_tool(prompt=edit_prompt, video=clip_path, image=image, label=label)  # type: ignore
            elif task == 'depth':
                res = depth_modify(prompt=edit_prompt, video=clip_path)  # type: ignore
            elif task == 'recolor':
                res = recolor(prompt=edit_prompt, video=clip_path)  # type: ignore
            elif task == 'pose':
                res = pose_reference(prompt=edit_prompt, video=clip_path)  # type: ignore
            elif task == 'style':
                res = style_transfer(prompt=edit_prompt, video=clip_path)  # type: ignore
            else:
                res = {'success': False, 'error': f'Unsupported task: {task}'}

            with open(inference_log, "a") as log_file:
                log_file.write(f"[LongEdit] Tool result for [{start_s:.3f},{end_s:.3f}]: {json.dumps(res)}\n")

            if isinstance(res, dict) and res.get('success') and res.get('output_path'):
                # Normalize to absolute path for ffmpeg concat robustness
                edited_paths.append(os.path.abspath(res['output_path']))

        if not edited_paths:
            with open(inference_log, "a") as log_file:
                log_file.write("[LongEdit] No segments were successfully edited.\n")
            return {
                'success': False,
                'error': f"No segments were successfully edited. See log for details: {inference_log}"
            }

        # ------------ Concatenate edited segments ------------
        concat_list = os.path.join(save_dir, "concat_list.txt")
        with open(concat_list, "w") as f:
            for p in edited_paths:
                f.write(f"file '{p}'\n")

        time_tag = datetime.now().strftime("%m%d%H%M%S")
        output_path_path = os.path.join(save_dir, f"{time_tag}_output.mp4")

        # Try stream-copy concat first
        concat_copy_cmd = [
            "ffmpeg", "-y",
            "-f", "concat", "-safe", "0",
            "-i", concat_list,
            "-c", "copy",
            output_path_path
        ]
        with open(inference_log, "a") as log_file:
            log_file.write("Executing Inference Command:\n" + " ".join(concat_copy_cmd) + "\n\n")

        try:
            subprocess.run(concat_copy_cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        except (subprocess.CalledProcessError, FileNotFoundError):
            # Fallback: re-encode concat if codecs/parameters mismatch
            concat_reencode_cmd = [
                "ffmpeg", "-y",
                "-f", "concat", "-safe", "0",
                "-i", concat_list,
                "-c:v", "libx264", "-preset", "fast", "-crf", "18",
                "-c:a", "aac",
                output_path_path
            ]
            with open(inference_log, "a") as log_file:
                log_file.write("Executing Inference Command:\n" + " ".join(concat_reencode_cmd) + "\n\n")
            subprocess.run(concat_reencode_cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        # ------------ Success (match existing return style) ------------
        return {
            'success': True,
            'output_path': output_path_path
        }

    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        error_message = f"Inference failed. See log for details: {inference_log}. Error: {str(e)}"
        return {
            'success': False,
            'error': error_message
        }
    except Exception as e:
        return {'success': False, 'error': f"An unexpected error occurred during inference: {str(e)}"}




if __name__ == "__main__":
    mcp.run(transport="stdio")
    