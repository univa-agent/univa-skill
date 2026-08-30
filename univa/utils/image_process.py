import numpy as np
from PIL import Image
import cv2
import os
import requests
import shutil

def download_image(image_url, save_path="temp.jpg"):
    """
    Downloads an image from a specified URL and saves it to a local file path.
    This internal helper function is used for saving generated or referenced images.

    Args:
        image_url (str): The URL of the image to download.
        save_path (str): The local file path (including filename) where the image should be saved.
                         Example: 'images/downloaded_image.jpg'
    """

    # Send an HTTP GET request to the URL, stream=True avoids loading the whole file in memory
    response = requests.get(image_url, stream=True)

    # Check if the request was successful (status code 200)
    response.raise_for_status() # This will raise an HTTPError for bad responses (4xx or 5xx)

    # Open the local file in binary write mode ('wb') and save the content
    with open(save_path, 'wb') as out_file:
        # Use shutil.copyfileobj for efficient streaming download
        shutil.copyfileobj(response.raw, out_file)



def character_concatetion(image_list: list[str]):
    cropped_pil_images = [Image.open(img_path).convert('RGBA') for img_path in image_list]

    max_height = max(img.height for img in cropped_pil_images)
    total_width = sum(img.width for img in cropped_pil_images)

    canvas = Image.new('RGBA', (total_width, max_height), (0, 0, 0, 0))

    x_offset = 0
    for img in cropped_pil_images:
        y_offset = (max_height - img.height) // 2
        canvas.paste(img, (x_offset, y_offset))
        x_offset += img.width

    canvas.save("stitched_image.png")


def visualize_masks_on_images(images, masks, alpha=0.5, color=(0, 255, 0), save_dir=None, grey=False):
    """
    Visualize segmentation masks on original images.
    
    Args:
        images: List of PIL Images
        masks: Can be:
            - A list of numpy arrays with shape (h, w)
            - A single numpy array with shape (n_frames, h, w)
            - A list containing a single numpy array with shape (n_frames, h, w) [Sa2VA model output]
            - A list of multiple segmentation masks (one per class)
        alpha: Transparency of the mask overlay (0-1)
        color: RGB color tuple for the mask
        save_dir: Directory to save visualized images to (optional)
    
    Returns:
        List of PIL Images with masks visualized
    """
    
    # Process masks based on their structure
    masks_list = []
    
    # Case 1: masks is a list with a single numpy array of shape (n_frames, h, w) - Sa2VA output format
    if (isinstance(masks, list) and len(masks) == 1 and 
        isinstance(masks[0], np.ndarray) and len(masks[0].shape) == 3):
        # print("Detected Sa2VA output format: list with a single array of shape (n_frames, h, w)")
        masks_list = [masks[0][i] for i in range(masks[0].shape[0])]
    
    # Case 2: masks is a single numpy array with shape (n_frames, h, w)
    elif isinstance(masks, np.ndarray) and len(masks.shape) == 3:
        # print("Detected single array with shape (n_frames, h, w)")
        masks_list = [masks[i] for i in range(masks.shape[0])]
    
    # Case 3: masks is already a list of 2D arrays
    elif isinstance(masks, list) and all(isinstance(m, np.ndarray) and len(m.shape) == 2 for m in masks):
        # print("Detected list of 2D mask arrays")
        masks_list = masks
    
    # If nothing matched, try a fallback approach
    else:
        # print("Using fallback approach for mask processing")
        try:
            if isinstance(masks, list) and len(masks) > 0:
                if hasattr(masks[0], 'shape') and len(masks[0].shape) > 2:
                    # Try to use first frame from each mask
                    masks_list = [m[0] if len(m.shape) > 2 else m for m in masks]
                else:
                    masks_list = masks
            else:
                masks_list = [masks]
        except Exception as e:
            # print(f"Error in fallback approach: {e}")
            # Create empty masks as a last resort
            masks_list = [np.zeros((img.height, img.width), dtype=np.uint8) for img in images]
    
    # print(f"Processed masks: {len(masks_list)} items")
    
    # Handle case where number of masks doesn't match number of images
    if len(images) != len(masks_list):
        # print(f"WARNING: Number of images ({len(images)}) doesn't match number of masks ({len(masks_list)})")
        
        if len(masks_list) > len(images):
            # print("Truncating masks list to match number of images")
            masks_list = masks_list[:len(images)]
        else:
            # print("Extending masks list with empty masks")
            empty_masks = [np.zeros((img.height, img.width), dtype=np.uint8) 
                          for img in images[len(masks_list):]]
            masks_list.extend(empty_masks)
    
    visualized_images = []
    
    if grey:
        for i, (image, mask) in enumerate(zip(images, masks_list)):

            mask_bw = (mask * 255).astype(np.uint8)  # mask=1->255，mask=0->0

            vis_pil = Image.fromarray(mask_bw, mode='L')

            visualized_images.append(vis_pil)

            if save_dir is not None:
                os.makedirs(save_dir, exist_ok=True)
                vis_pil = vis_pil.resize(
                    (512, 512),
                    resample=Image.Resampling.LANCZOS  
                )
                vis_pil.save(os.path.join(save_dir, f"{i:05d}.png"))

    else:
        for i, (image, mask) in enumerate(zip(images, masks_list)):
            # Convert PIL image to numpy array (RGB)
            img_np = np.array(image)
            
            # Create a copy for visualization
            vis_img = img_np.copy()
            
            # Ensure mask is binary (0 or 1)
            if mask.max() > 1:
                mask = (mask > 0).astype(np.uint8)
            
            # Resize mask if needed
            if mask.shape[:2] != img_np.shape[:2]:
                # print(f"Resizing mask {i} from {mask.shape[:2]} to {img_np.shape[:2]}")
                mask = cv2.resize(mask, (img_np.shape[1], img_np.shape[0]), interpolation=cv2.INTER_NEAREST)
            
            # Create a colored mask
            colored_mask = np.zeros_like(img_np)
            for c in range(3):
                colored_mask[:, :, c] = mask * color[c]
            
            # Overlay the mask on the image
            vis_img = cv2.addWeighted(vis_img, 1, colored_mask, alpha, 0)
            
            # Convert back to PIL Image
            vis_pil = Image.fromarray(vis_img)
            visualized_images.append(vis_pil)
            
            # Save if requested
            if save_dir is not None:
                os.makedirs(save_dir, exist_ok=True)
                vis_pil.save(os.path.join(save_dir, f"segmented_frame_{i:03d}.png"))
    
    return visualized_images

