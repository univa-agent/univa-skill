import datetime
import os
import cv2
import torch
from PIL import Image
from mcp.server.fastmcp import FastMCP
from ultralytics import SAM
import numpy as np
from transformers import AutoTokenizer, AutoModel

from univa.config.mcp_config import get_mcp_section
from univa.mcp_tools.base import ToolResponse, setup_logger
from univa.utils.image_process import visualize_masks_on_images
from univa.utils.video_process import extract_frames, stitch_frames_to_video


video_tracking_config = get_mcp_section("video_tracking")
if video_tracking_config.get("cuda_visible_devices"):
    os.environ["CUDA_VISIBLE_DEVICES"] = str(video_tracking_config["cuda_visible_devices"])

# Configure logging
log_dir = "logs"
logger = setup_logger(__name__, "logs/mcp_tools", "video_tracking.log")
logger.info(f"Loaded video_tracking_config: {video_tracking_config}")

# Create an MCP server
mcp = FastMCP("Video_Tracking_Server")


# Add an addition tool
@mcp.tool()
def video_referring_segmentation(prompt: str, video_path: str, return_mask: bool = False) -> str:
    """
    Performs video instance segmentation to identify and outline specific objects within a video based on a textual prompt.
    This tool is useful for tasks requiring precise object localization and tracking in video content.

    Args:
        prompt (str): User's instruction.
        video_path (str): The path of the video.

    Returns:
        dict: A dictionary containing the success status, a message, and the path to the segmentation results.
              - 'success' (bool): True if the segmentation was successful, False otherwise.
              - 'message' (str): A message describing the result, including the text answer and path to visualized results.
              - 'output_path' (str, optional): The path to the directory containing the visualized segmentation video results if successful.
              - 'error' (str, optional): An error message if the operation failed.
    """
    try:
        # load the model and tokenizer
        path = video_tracking_config.get("sa2va_model_path")
        model = AutoModel.from_pretrained(
            path,
            torch_dtype=torch.bfloat16,
            low_cpu_mem_usage=True,
            use_flash_attn=True,
            trust_remote_code=True).eval().cuda()
        tokenizer = AutoTokenizer.from_pretrained(path, trust_remote_code=True, use_fast=False)

        # for video chat with segmentation mask output
        video_base_name = video_path.split(".")[0].split("/")[-1].replace(" ", "_")
        output_dir_base = os.path.join(log_dir, video_path.split(".")[0].split("/")[-1].replace(" ", "_"))
        output_dir = os.path.join(output_dir_base, prompt)
        avg_fps = extract_frames(video_path, output_dir=output_dir, target_fps=30, grey=True)
        video_folder = output_dir
        images_paths = os.listdir(video_folder)
        images_paths = [os.path.join(video_folder, image_path) for image_path in images_paths]
        images_paths.sort()
        # if len(images_paths) > 5:  # uniformly sample 5 frames
        #     step = (len(images_paths) - 1) // (5 - 1)
        #     images_paths = [images_paths[0]] + images_paths[1:-1][::step][1:] + [images_paths[-1]]
        # print(images_paths)
        images = [Image.open(image_path).convert('RGB') for image_path in images_paths]
        text_prompts = "<image>" + prompt
        input_dict = {
            'video': images,
            'text': text_prompts,
            'past_text': '',
            'mask_prompts': None,
            'tokenizer': tokenizer,
        }

        with torch.no_grad():
            return_dict = model.predict_forward(**input_dict)

        answer = return_dict["prediction"] # the text format answer
        masks = return_dict['prediction_masks']  # segmentation masks, list(np.array(n_frames, h, w), ...)
        masks_inv = [(~(mask.astype(bool))).astype(np.uint8) for mask in masks]

        output_dir_segmentation = os.path.join(output_dir_base, "segmentation_results", prompt)
        _ = visualize_masks_on_images(
            images,
            masks_inv,
            # alpha=0.5,
            alpha=1.0,
            color=(255, 255, 255),
            # color=(0, 150, 255),
            save_dir=output_dir_segmentation,
            grey=False,
        )

        time_ = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        segmented_video_path = f"logs/segmented_{time_}.mp4"
        stitch_frames_to_video(output_dir_segmentation, segmented_video_path, avg_fps)
        response = f"{answer}\n the visualized segmentation results are saved in {segmented_video_path}"

        torch.cuda.empty_cache()
        del model
        del tokenizer

        if return_mask:
            return {
                'success': True,
                'message': response,
                'output_path': segmented_video_path
            }
        
        return {
            'success': True,
            'message': response,
            'output_path': segmented_video_path
        }
    
    except Exception as e:
        return {
            'success': False,
            'error': str(e)
        }


# @mcp.tool()
def video_all_segmentation(video_path: str) -> str:
    """
    Segments all detectable objects within a video, providing a comprehensive mask for each identified object.
    This tool is useful for general object detection and mask generation across an entire video.

    Args:
        video_path (str): The path of the video.

    Returns:
        dict: A dictionary containing the success status, a message, and the path to the segmentation results.
              - 'success' (bool): True if the segmentation was successful, False otherwise.
              - 'message' (str): A message indicating where the results are saved.
              - 'output_path' (str, optional): The path to the directory containing the segmentation results if successful.
              - 'error' (str, optional): An error message if the operation failed.
    """
    model = SAM(video_tracking_config.get("sam_model_path"))

    

    # Run inference
    model(video_path, save=True, project=log_dir, name="runs_segment_predict")

    results_path = os.path.join(log_dir, 'runs_segment_predict')
    return {
        'success': True,
        'message': f"Results saved to {results_path}",
        'output_path': results_path
    }


def overlay_image_on_mask(background_image, overlay_image, mask):
    """
    Puts an overlay image onto a background image based on a given mask.
    This version automatically handles size mismatches between the mask and the background image.
    """
    result_image = background_image.copy()
    
    bg_h, bg_w = background_image.shape[:2]
    mask_h, mask_w = mask.shape[:2]

    # if mask and background sizes do not match, resize the mask
    if bg_h != mask_h or bg_w != mask_w:
        # use cv2 resize for better performance
        resized_mask = cv2.resize(mask.astype(np.float32), (bg_w, bg_h), interpolation=cv2.INTER_LINEAR)
    else:
        resized_mask = mask
    
    # make sure the mask is binary
    if resized_mask.max() > 1:
        binary_mask = (resized_mask > 128).astype(np.uint8) * 255
    else:
        binary_mask = (resized_mask > 0.5).astype(np.uint8) * 255

    # calculate bounding box of the mask
    y_coords, x_coords = np.where(binary_mask > 0)
    if len(x_coords) == 0:
        return background_image

    x_min, x_max = np.min(x_coords), np.max(x_coords)
    y_min, y_max = np.min(y_coords), np.max(y_coords)
    bbox_height = y_max - y_min + 1
    bbox_width = x_max - x_min + 1

    # resize overlay image to fit the bounding box
    resized_overlay = cv2.resize(overlay_image, (bbox_width, bbox_height))

    # extract the ROI from the background image
    roi_background = result_image[y_min:y_max+1, x_min:x_max+1]
    
    # extract the ROI from the binary mask
    roi_mask = binary_mask[y_min:y_max+1, x_min:x_max+1]

    # use the mask to blend the overlay with the background
    alpha = roi_mask[..., np.newaxis] / 255.0
    
    blended_roi = (resized_overlay.astype(np.float32) * alpha) + \
                  (roi_background.astype(np.float32) * (1.0 - alpha))
    
    result_image[y_min:y_max+1, x_min:x_max+1] = blended_roi.astype(np.uint8)
    return result_image


if __name__ == "__main__":
    mcp.run(transport="stdio")


