import requests
import json
import time
import logging
import os
import base64
from datetime import datetime

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger()

# from dotenv import load_dotenv

# load_dotenv()


def _wavespeed_base_url(base_url: str | None = None) -> str:
    return (base_url or os.getenv("WAVESPEED_BASE_URL") or "https://api.wavespeed.ai/api/v3").rstrip("/")


def text_to_image_generate(api_key : str, prompt : str, model: str | None="flux-kontext-pro", provider: str | None="wavespeed-ai", aspect_ratio: str="16:9", guidance_scale: float=3.5, safety_tolerance: str="5", num_images: int=1, base_url: str | None = None) -> str | None:
    url = f"{_wavespeed_base_url(base_url)}/{provider or 'wavespeed-ai'}/{model or 'flux-kontext-pro'}/text-to-image"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }
    seed = int(datetime.now().timestamp())
    payload = {
        "prompt": prompt,
        "num_images": num_images,
        "aspect_ratio": aspect_ratio,
        "guidance_scale": guidance_scale,
        "safety_tolerance": safety_tolerance,
        "seed": seed
    }

    begin = time.time()
    response = requests.post(url, headers=headers, data=json.dumps(payload))
    if response.status_code == 200:
        result = response.json()["data"]
        request_id = result["id"]
        logger.info(f"Task submitted successfully. Request ID: {request_id}")
    else:
        logger.info(f"Error: {response.status_code}, {response.text}")
        return {
            'success': False,
            'error': f"Error: {response.status_code}, {response.text}"
        }

    url = f"{_wavespeed_base_url(base_url)}/predictions/{request_id}/result"
    headers = {"Authorization": f"Bearer {api_key}"}

    # Poll for results
    while True:
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            result = response.json()["data"]
            status = result["status"]

            if status == "completed":
                end = time.time()
                logger.info(f"Task completed in {end - begin} seconds.")
                url = result["outputs"][0]
                logger.info(f"Task completed. URL: {url}")
                return url
            elif status == "failed":
                logger.info(f"Task failed: {result.get('error')}")
                return None
            else:
                logger.info(f"Task still processing. Status: {status}")
        else:
            logger.info(f"Error: {response.status_code}, {response.text}")
            return None


def image_to_image_generate(api_key, prompt, images, model: str | None="flux-kontext-pro", provider: str | None="wavespeed-ai", aspect_ratio="16:9", guidance_scale=3.5, safety_tolerance="5", base_url: str | None = None):
    if isinstance(images, list):
        logger.info("Hello from WaveSpeedAI!")

        url = f"{_wavespeed_base_url(base_url)}/{provider or 'wavespeed-ai'}/{model or 'flux-kontext-pro'}/multi"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        }
        b64_list = []
        for image in images:
            with open(image, "rb") as f:
                img_bytes = f.read()
            b = base64.b64encode(img_bytes).decode("utf-8")
            ext = os.path.splitext(image)[1].lower()
            mime = "jpeg" if ext in [".jpg", ".jpeg"] else ext.strip(".")
            b64_list.append(f"data:image/{mime};base64,{b}")
        seed = int(datetime.now().timestamp())
        payload = {
            "guidance_scale": guidance_scale,
            "images": b64_list,
            "prompt": prompt,
            "safety_tolerance": safety_tolerance,
            "aspect_ratio": aspect_ratio,
            "seed": seed
        }

        begin = time.time()
        response = requests.post(url, headers=headers, data=json.dumps(payload))
        if response.status_code == 200:
            result = response.json()["data"]
            request_id = result["id"]
            logger.info(f"Task submitted successfully. Request ID: {request_id}")
        else:
            logger.info(f"Error: {response.status_code}, {response.text}")
            return {
                'success': False,
                'error': f"Error: {response.status_code}, {response.text}"
            }

        url = f"{_wavespeed_base_url(base_url)}/predictions/{request_id}/result"
        headers = {"Authorization": f"Bearer {api_key}"}

        # Poll for results
        while True:
            response = requests.get(url, headers=headers)
            if response.status_code == 200:
                result = response.json()["data"]
                status = result["status"]

                if status == "completed":
                    end = time.time()
                    logger.info(f"Task completed in {end - begin} seconds.")
                    url = result["outputs"][0]
                    logger.info(f"Task completed. URL: {url}")
                    return url
                elif status == "failed":
                    logger.info(f"Task failed: {result.get('error')}")
                    return None
                else:
                    logger.info(f"Task still processing. Status: {status}")
            else:
                logger.info(f"Error: {response.status_code}, {response.text}")
                return None
    else:
        logger.info("Hello from WaveSpeedAI!")
        

        url = f"{_wavespeed_base_url(base_url)}/{provider or 'wavespeed-ai'}/{model}"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        }
        with open(images, "rb") as f:
            img_bytes = f.read()
        b64 = base64.b64encode(img_bytes).decode("utf-8")
        payload = {
            "guidance_scale": 3.5,
            "image": f"data:image/jpeg;base64,{b64}",
            "prompt": prompt,
            "safety_tolerance": "5"
        }

        begin = time.time()
        response = requests.post(url, headers=headers, data=json.dumps(payload))
        if response.status_code == 200:
            result = response.json()["data"]
            request_id = result["id"]
            logger.info(f"Task submitted successfully. Request ID: {request_id}")
        else:
            logger.info(f"Error: {response.status_code}, {response.text}")
            return {
                'success': False,
                'error': f"Error: {response.status_code}, {response.text}"
            }

        url = f"{_wavespeed_base_url(base_url)}/predictions/{request_id}/result"
        headers = {"Authorization": f"Bearer {api_key}"}

        # Poll for results
        while True:
            response = requests.get(url, headers=headers)
            if response.status_code == 200:
                result = response.json()["data"]
                status = result["status"]

                if status == "completed":
                    end = time.time()
                    logger.info(f"Task completed in {end - begin} seconds.")
                    url = result["outputs"][0]
                    logger.info(f"Task completed. URL: {url}")
                    return url
                elif status == "failed":
                    logger.info(f"Task failed: {result.get('error')}")
                    return None
                else:
                    logger.info(f"Task still processing. Status: {status}")
            else:
                logger.info(f"Error: {response.status_code}, {response.text}")
                return None

def text_to_video_generate(api_key, prompt, save_path: str = None, model: str | None="seedance-v1-pro-t2v-480p", provider: str | None="bytedance", duration=None, base_url: str | None = None, aspect_ratio: str = "16:9"):
    url = f"{_wavespeed_base_url(base_url)}/{provider or 'wavespeed-ai'}/{model}"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }
    payload = {
        "aspect_ratio": aspect_ratio,
        "prompt": prompt,
        "seed": -1
    }
    if duration is not None:
        payload["duration"] = duration

    begin = time.time()
    response = requests.post(url, headers=headers, data=json.dumps(payload))
    if response.status_code == 200:
        result = response.json()["data"]
        request_id = result["id"]
        logger.info(f"Task submitted successfully. Request ID: {request_id}")
    else:
        logger.info(f"Error: {response.status_code}, {response.text}")
        return {
            'success': False,
            'error': f"Error: {response.status_code}, {response.text}"
        }

    url = f"{_wavespeed_base_url(base_url)}/predictions/{request_id}/result"
    headers = {"Authorization": f"Bearer {api_key}"}

    # Poll for results
    while True:
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            result = response.json()["data"]
            status = result["status"]

            if status == "completed":
                end = time.time()
                logger.info(f"Task completed in {end - begin} seconds.")
                url = result["outputs"][0]
                logger.info(f"Task completed. URL: {url}")
                time_ft = datetime.now().strftime("%m%d%H%M%S")
                url_name = url.split("/")[-1]
                output_filename = os.path.abspath(save_path if save_path else f"results/{time_ft}_{url_name}")
                resp = requests.get(url, stream=True)
                resp.raise_for_status()
                with open(output_filename, "wb") as f:
                    for chunk in resp.iter_content(8192):
                        f.write(chunk)
                return {
                    'success': True,
                    'output_path': output_filename,
                    'message': "Video generated successfully."
                }
            elif status == "failed":
                logger.info(f"Task failed: {result.get('error')}")
                return {
                    'success': False,
                    'error': f"Task failed: {result.get('error')}"
                }
            else:
                logger.info(f"Task still processing. Status: {status}")
        else:
            logger.info(f"Error: {response.status_code}, {response.text}")
            return {
                'success': False,
                'error': f"Error: {response.status_code}, {response.text}"
            }


def image_to_video_generate(api_key, prompt, image, save_path: str = None, model: str | None="seedance-v1-pro-i2v-480p", provider: str | None="bytedance", duration=None, base_url: str | None = None, aspect_ratio: str = "16:9"):
    logger.info("Hello from WaveSpeedAI!")
    

    url = f"{_wavespeed_base_url(base_url)}/{provider or 'wavespeed-ai'}/{model}"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }
    with open(image, "rb") as f:
        img_bytes = f.read()
    b64 = base64.b64encode(img_bytes).decode("utf-8")
    seed = int(datetime.now().timestamp())
    payload = {
        "image": f"data:image/jpeg;base64,{b64}",
        "prompt": prompt,
        "seed": seed,
        "aspect_ratio": aspect_ratio,
    }
    if duration is not None:
        payload["duration"] = duration

    begin = time.time()
    response = requests.post(url, headers=headers, data=json.dumps(payload))
    if response.status_code == 200:
        result = response.json()["data"]
        request_id = result["id"]
        logger.info(f"Task submitted successfully. Request ID: {request_id}")
    else:
        logger.info(f"Error: {response.status_code}, {response.text}")
        return {
            'success': False,
            'error': f"Error: {response.status_code}, {response.text}"
        }

    url = f"{_wavespeed_base_url(base_url)}/predictions/{request_id}/result"
    headers = {"Authorization": f"Bearer {api_key}"}

    # Poll for results
    while True:
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            result = response.json()["data"]
            status = result["status"]

            if status == "completed":
                end = time.time()
                logger.info(f"Task completed in {end - begin} seconds.")
                url = result["outputs"][0]
                logger.info(f"Task completed. URL: {url}")
                time_ft = datetime.now().strftime("%m%d%H%M%S")
                url_name = url.split("/")[-1]
                output_filename = os.path.abspath(save_path if save_path else f"results/{time_ft}_{url_name}")
                resp = requests.get(url, stream=True)
                resp.raise_for_status()
                with open(output_filename, "wb") as f:
                    for chunk in resp.iter_content(8192):
                        f.write(chunk)
                return {
                    'success': True,
                    'output_path': output_filename,
                    'message': "Video generated successfully."
                }
            elif status == "failed":
                logger.info(f"Task failed: {result.get('error')}")
                return {
                    'success': False,
                    'error': f"Task failed: {result.get('error')}"
                }
            else:
                logger.info(f"Task still processing. Status: {status}")
        else:
            logger.info(f"Error: {response.status_code}, {response.text}")
            return {
                'success': False,
                'error': f"Error: {response.status_code}, {response.text}"
            }

def frame_to_frame_video(api_key, prompt, images, save_path: str = None, model: str | None="wan-flf2v", provider: str | None="wavespeed-ai", duration=None, base_url: str | None = None):
    logger.info("Hello from WaveSpeedAI!")
    

    url = f"{_wavespeed_base_url(base_url)}/{provider or 'wavespeed-ai'}/{model}"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }
    with open(images[0], "rb") as f:
        img_bytes = f.read()
    first_frame_b64 = base64.b64encode(img_bytes).decode("utf-8")
    with open(images[-1], "rb") as f:
        img_bytes = f.read()
    last_frame_b64 = base64.b64encode(img_bytes).decode("utf-8")
    seed = int(datetime.now().timestamp())
    payload = {
        "enable_safety_checker": True,
        "first_image": f"data:image/jpeg;base64,{first_frame_b64}",
        "guidance_scale": 5,
        "last_image": f"data:image/jpeg;base64,{last_frame_b64}",
        "negative_prompt": "",
        "num_inference_steps": 30,
        "prompt": prompt,
        "seed": seed,
        "size": "832*480"
    }
    if duration is not None:
        payload["duration"] = duration

    begin = time.time()
    response = requests.post(url, headers=headers, data=json.dumps(payload))
    if response.status_code == 200:
        result = response.json()["data"]
        request_id = result["id"]
        logger.info(f"Task submitted successfully. Request ID: {request_id}")
    else:
        logger.info(f"Error: {response.status_code}, {response.text}")
        return {
            'success': False,
            'error': f"Error: {response.status_code}, {response.text}"
        }

    url = f"{_wavespeed_base_url(base_url)}/predictions/{request_id}/result"
    headers = {"Authorization": f"Bearer {api_key}"}

    # Poll for results
    while True:
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            result = response.json()["data"]
            status = result["status"]

            if status == "completed":
                end = time.time()
                logger.info(f"Task completed in {end - begin} seconds.")
                url = result["outputs"][0]
                logger.info(f"Task completed. URL: {url}")
                time_ft = datetime.now().strftime("%m%d%H%M%S")
                url_name = url.split("/")[-1]
                output_filename = os.path.abspath(save_path if save_path else f"results/{time_ft}_{url_name}")
                resp = requests.get(url, stream=True)
                resp.raise_for_status()
                with open(output_filename, "wb") as f:
                    for chunk in resp.iter_content(8192):
                        f.write(chunk)
                return {
                    'success': True,
                    'output_path': output_filename,
                    'message': f"{prompt} success generate video"
                }
            elif status == "failed":
                logger.info(f"Task failed: {result.get('error')}")
                return {
                    'success': False,
                    'error': f"Task failed: {result.get('error')}"
                }
            else:
                logger.info(f"Task still processing. Status: {status}")
        else:
            logger.info(f"Error: {response.status_code}, {response.text}")
            return {
                'success': False,
                'error': f"Task failed: {result.get('error')}"
            }
        
        
def audio_gen(api_key, prompt, video_url, model: str | None="mmaudio-v2", save_path=None, provider: str | None="wavespeed-ai", duration=5, guidance_scale=4.5, mask_away_clip=False, negative_prompt="", num_inference_steps=25, base_url: str | None = None):
    logger.info("Hello from WaveSpeedAI!")

    # Check if video_url is a local file path
    if os.path.exists(video_url):
        # Read the local video file and convert it to base64
        with open(video_url, "rb") as f:
            video_bytes = f.read()
        video_b64 = base64.b64encode(video_bytes).decode("utf-8")
        # Determine the MIME type based on file extension
        ext = os.path.splitext(video_url)[1].lower()
        mime_type = "mp4" if ext in [".mp4", ".mov", ".avi", ".mkv"] else "mp4"  # Default to mp4 if unknown
        video_data_uri = f"data:video/{mime_type};base64,{video_b64}"
    else:
        # Assume it's a URL
        video_data_uri = video_url

    url = f"{_wavespeed_base_url(base_url)}/{provider or 'wavespeed-ai'}/{model}"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }
    payload = {
        "duration": duration,
        "guidance_scale": guidance_scale,
        "mask_away_clip": mask_away_clip,
        "negative_prompt": negative_prompt,
        "num_inference_steps": num_inference_steps,
        "prompt": prompt,
        "video": video_data_uri
    }

    begin = time.time()
    response = requests.post(url, headers=headers, data=json.dumps(payload))
    if response.status_code == 200:
        result = response.json()["data"]
        request_id = result["id"]
        logger.info(f"Task submitted successfully. Request ID: {request_id}")
    else:
        logger.info(f"Error: {response.status_code}, {response.text}")
        return {
            'success': False,
            'error': f"Error: {response.status_code}, {response.text}"
        }

    url = f"{_wavespeed_base_url(base_url)}/predictions/{request_id}/result"
    headers = {"Authorization": f"Bearer {api_key}"}

    # Poll for results
    while True:
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            result = response.json()["data"]
            status = result["status"]

            if status == "completed":
                end = time.time()
                logger.info(f"Task completed in {end - begin} seconds.")
                url = result["outputs"][0]
                logger.info(f"Task completed. URL: {url}")
                time_ft = datetime.now().strftime("%m%d%H%M%S")
                url_name = url.split("/")[-1]
                output_filename = os.path.abspath(save_path if save_path else f"results/{time_ft}_{url_name}")
                resp = requests.get(url, stream=True)
                resp.raise_for_status()
                with open(output_filename, "wb") as f:
                    for chunk in resp.iter_content(8192):
                        f.write(chunk)
                return {
                    'success': True,
                    'output_path': output_filename,
                    'message': f"{prompt} success generate video"
                }
            elif status == "failed":
                logger.info(f"Task failed: {result.get('error')}")
                return {
                    'success': False,
                    'error': f"Task failed: {result.get('error')}"
                }
            else:
                logger.info(f"Task still processing. Status: {status}")
        else:
            logger.info(f"Error: {response.status_code}, {response.text}")
            return {
                'success': False,
                'error': f"Error: {response.status_code}, {response.text}"
            }

        time.sleep(0.5)


def runway_video_editing(api_key, prompt, video_url, aspect_ratio="16:9", save_path: str = None, model: str | None="gen4-aleph", provider: str | None="runwayml", base_url: str | None = None):
    url = f"{_wavespeed_base_url(base_url)}/{provider or 'runwayml'}/{model or 'gen4-aleph'}"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }

    with open(video_url, "rb") as f:
            video_bytes = f.read()
    video_b64 = base64.b64encode(video_bytes).decode("utf-8")
    # Determine the MIME type based on file extension
    ext = os.path.splitext(video_url)[1].lower()
    mime_type = "mp4" if ext in [".mp4", ".mov", ".avi", ".mkv"] else "mp4"  # Default to mp4 if unknown
    video_data_uri = f"data:video/{mime_type};base64,{video_b64}"

    payload = {
        "aspect_ratio": aspect_ratio,
        "prompt": prompt,
        "video": video_data_uri
    }

    begin = time.time()
    response = requests.post(url, headers=headers, data=json.dumps(payload))
    if response.status_code == 200:
        result = response.json()["data"]
        request_id = result["id"]
        logger.info(f"Task submitted successfully. Request ID: {request_id}")
    else:
        logger.info(f"Error: {response.status_code}, {response.text}")
        return

    url = f"{_wavespeed_base_url(base_url)}/predictions/{request_id}/result"
    headers = {"Authorization": f"Bearer {api_key}"}

    # Poll for results
    while True:
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            result = response.json()["data"]
            status = result["status"]

            if status == "completed":
                end = time.time()
                logger.info(f"Task completed in {end - begin} seconds.")
                url = result["outputs"][0]
                time_ft = datetime.now().strftime("%m%d%H%M%S")
                url_name = url.split("/")[-1]
                os.makedirs("results", exist_ok=True)
                output_filename = os.path.abspath(save_path if save_path else f"results/{time_ft}_{url_name}")
                resp = requests.get(url, stream=True)
                resp.raise_for_status()
                with open(output_filename, "wb") as f:
                    for chunk in resp.iter_content(8192):
                        f.write(chunk)
                return {
                    'success': True,
                    'output_path': output_filename,
                    'message': f"{prompt} success generate video"
                }
            elif status == "failed":
                logger.info(f"Task failed: {result.get('error')}")
                return {
                    'success': False,
                    'error': f"Task failed: {result.get('error')}"
                }
            else:
                logger.info(f"Task still processing. Status: {status}")
        else:
            logger.info(f"Error: {response.status_code}, {response.text}")
            return {
                'success': False,
                'error': f"Error: {response.status_code}, {response.text}"
            }


def vace_api(
    api_key,
    prompt,
    image_url: str=None,
    video_url: str=None,
    context_scale: int=1,
    flow_shift: int=16,
    guidance_scale: int=5,
    duration: int=5,
    num_inference_steps: int=40,
    task: str="depth",
    size: str="1280*720",
    save_path: str=None,
    model: str | None = "wan-2.1-14b-vace",
    provider: str | None = "wavespeed-ai",
    base_url: str | None = None,
):
    url = f"{_wavespeed_base_url(base_url)}/{provider or 'wavespeed-ai'}/{model or 'wan-2.1-14b-vace'}"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }

    if os.path.exists(video_url):
        # Read the local video file and convert it to base64
        with open(video_url, "rb") as f:
            video_bytes = f.read()
        video_b64 = base64.b64encode(video_bytes).decode("utf-8")
        # Determine the MIME type based on file extension
        ext = os.path.splitext(video_url)[1].lower()
        mime_type = "mp4" if ext in [".mp4", ".mov", ".avi", ".mkv"] else "mp4"  # Default to mp4 if unknown
        video_data_uri = f"data:video/{mime_type};base64,{video_b64}"
    else:
        # Assume it's a URL
        video_data_uri = video_url

    with open(image_url, "rb") as f:
        img_bytes = f.read()
    b64 = base64.b64encode(img_bytes).decode("utf-8")
    image_b64 = f"data:image/jpeg;base64,{b64}"

    seed = int(datetime.now().timestamp())
    payload = {
        "context_scale": context_scale,
        "duration": duration,
        "flow_shift": flow_shift,
        "guidance_scale": guidance_scale,
        "images": [
            image_b64
        ],
        "negative_prompt": "",
        "num_inference_steps": num_inference_steps,
        "prompt": prompt,
        "seed": seed,
        "size": size,
        "task": task,
        "video": video_data_uri if video_url else ""
    }

    begin = time.time()
    response = requests.post(url, headers=headers, data=json.dumps(payload))
    if response.status_code == 200:
        result = response.json()["data"]
        request_id = result["id"]
        logger.info(f"Task submitted successfully. Request ID: {request_id}")
    else:
        logger.info(f"Error: {response.status_code}, {response.text}")
        return

    url = f"{_wavespeed_base_url(base_url)}/predictions/{request_id}/result"
    headers = {"Authorization": f"Bearer {api_key}"}

    # Poll for results
    while True:
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            result = response.json()["data"]
            status = result["status"]

            if status == "completed":
                end = time.time()
                logger.info(f"Task completed in {end - begin} seconds.")
                url = result["outputs"][0]
                time_ft = datetime.now().strftime("%m%d%H%M%S")
                url_name = url.split("/")[-1]
                output_filename = os.path.abspath(save_path if save_path else f"results/{time_ft}_{url_name}")
                resp = requests.get(url, stream=True)
                resp.raise_for_status()
                with open(output_filename, "wb") as f:
                    for chunk in resp.iter_content(8192):
                        f.write(chunk)
                return {
                    'success': True,
                    'output_path': output_filename,
                    'message': f"{prompt} success generate video"
                }
            elif status == "failed":
                logger.info(f"Task failed: {result.get('error')}")
                return {
                    'success': False,
                    'error': f"Task failed: {result.get('error')}"
                }
            else:
                logger.info(f"Task still processing. Status: {status}")
        else:
            logger.info(f"Error: {response.status_code}, {response.text}")
            return {
                'success': False,
                'error': f"Error: {response.status_code}, {response.text}"
            }


def speech_gen(api_key: str, prompt: str, voice_id: str = "Wise_Woman", emotion: str = "surprised", english_normalization: bool = False, pitch: int = 0, speed: float = 1.0, volume: float = 1, save_path=None, provider: str | None="minimax", model: str | None="speech-2.5-turbo-preview", base_url: str | None = None):

    url = f"{_wavespeed_base_url(base_url)}/{provider or 'wavespeed-ai'}/{model}"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }
    payload = {
        "emotion": emotion,
        "english_normalization": english_normalization,
        "pitch": pitch,
        "speed": speed,
        "text": prompt,
        "voice_id": voice_id,
        "volume": volume
    }

    begin = time.time()
    response = requests.post(url, headers=headers, data=json.dumps(payload))
    if response.status_code == 200:
        result = response.json()["data"]
        request_id = result["id"]
        logger.info(f"Task submitted successfully. Request ID: {request_id}")
    else:
        logger.info(f"Error: {response.status_code}, {response.text}")
        return

    url = f"{_wavespeed_base_url(base_url)}/predictions/{request_id}/result"
    headers = {"Authorization": f"Bearer {api_key}"}

    # Poll for results
    while True:
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            result = response.json()["data"]
            status = result["status"]

            if status == "completed":
                end = time.time()
                logger.info(f"Task completed in {end - begin} seconds.")
                url = result["outputs"][0]
                logger.info(f"Task completed. URL: {url}")
                time_ft = datetime.now().strftime("%m%d%H%M%S")
                url_name = url.split("/")[-1]
                output_filename = os.path.abspath(save_path if save_path else f"results/{time_ft}_{url_name}")
                resp = requests.get(url, stream=True)
                resp.raise_for_status()
                with open(output_filename, "wb") as f:
                    for chunk in resp.iter_content(8192):
                        f.write(chunk)
                return {
                    'success': True,
                    'output_path': output_filename,
                    'message': f"{prompt[:30]} success generate video"
                }
            elif status == "failed":
                logger.info(f"Task failed: {result.get('error')}")
                return {
                    'success': False,
                    'error': f"Task failed: {result.get('error')}"
                }
            else:
                logger.info(f"Task still processing. Status: {status}")
        else:
            logger.info(f"Error: {response.status_code}, {response.text}")
            return {
                'success': False,
                'error': f"Error: {response.status_code}, {response.text}"
            }

        time.sleep(0.5)


def seedream_v4_sequential_edit(api_key: str, prompt: str, images: list[str], max_images: int = 2, size: str = "2048*2048", enable_base64_output: bool = False, enable_sync_mode: bool = False, model: str | None = "seedream-v4/edit-sequential", provider: str | None = "bytedance", base_url: str | None = None):
    """
    Generate a series of magazine photoshoots using ByteDance seedream-v4 edit-sequential API.
    
    Args:
        api_key: WaveSpeed API key
        prompt: Text prompt for image generation
        images: List of image URLs (up to 10, empty strings for unused slots)
        max_images: Maximum number of images to generate
        size: Output image size
        enable_base64_output: Whether to return base64 encoded output
        enable_sync_mode: Whether to use synchronous mode
    
    Returns:
        dict: Result containing success status and output URL or error message
    """
    # Convert local image paths to base64 encoded data URIs
    b64_list = []
    for image in images:
        if image and os.path.exists(image):  # Only process non-empty strings that are valid file paths
            with open(image, "rb") as f:
                img_bytes = f.read()
            b64 = base64.b64encode(img_bytes).decode("utf-8")
            ext = os.path.splitext(image)[1].lower()
            mime = "jpeg" if ext in [".jpg", ".jpeg"] else ext.strip(".")
            b64_list.append(f"data:image/{mime};base64,{b64}")
        elif image:  # If it's a URL (non-empty but not a local file)
            b64_list.append(image)
        else:  # Empty string
            b64_list.append("")
    
    padded_images = b64_list[:10]
    
    url = f"{_wavespeed_base_url(base_url)}/{provider or 'bytedance'}/{model or 'seedream-v4/edit-sequential'}"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }
    payload = {
        "enable_base64_output": enable_base64_output,
        "enable_sync_mode": enable_sync_mode,
        "images": padded_images,
        "max_images": max_images,
        "prompt": prompt,
        "size": size
    }

    begin = time.time()
    response = requests.post(url, headers=headers, data=json.dumps(payload))
    if response.status_code == 200:
        result = response.json()["data"]
        request_id = result["id"]
        logger.info(f"Task submitted successfully. Request ID: {request_id}")
    else:
        logger.info(f"Error: {response.status_code}, {response.text}")
        return {
            'success': False,
            'error': f"Error: {response.status_code}, {response.text}"
        }

    url = f"{_wavespeed_base_url(base_url)}/predictions/{request_id}/result"
    headers = {"Authorization": f"Bearer {api_key}"}

    # Poll for results
    while True:
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            result = response.json()["data"]
            status = result["status"]

            if status == "completed":
                end = time.time()
                logger.info(f"Task completed in {end - begin} seconds.")
                output_url = result["outputs"]
                logger.info(f"Task completed. URL: {output_url}")
                return {
                    'success': True,
                    'output_path': output_url,
                    'message': "Image editing completed successfully."
                }
            elif status == "failed":
                logger.info(f"Task failed: {result.get('error')}")
                return {
                    'success': False,
                    'error': f"Task failed: {result.get('error')}"
                }
            else:
                logger.info(f"Task still processing. Status: {status}")
        else:
            logger.info(f"Error: {response.status_code}, {response.text}")
            return {
                'success': False,
                'error': f"Error: {response.status_code}, {response.text}"
            }



def seedream_v4_edit(api_key: str, prompt: str, images: str|list[str], size: str = "1024*1024", enable_base64_output: bool = False, enable_sync_mode: bool = False, save_path: str = None, model: str | None = "seedream-v4/edit", provider: str | None = "bytedance", base_url: str | None = None):
    url = f"{_wavespeed_base_url(base_url)}/{provider or 'bytedance'}/{model or 'seedream-v4/edit'}"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }
    if isinstance(images, str):
        images = [images]
    
    b64_list = []
    for image in images:
        if image and os.path.exists(image):
            with open(image, "rb") as f:
                img_bytes = f.read()
            b64 = base64.b64encode(img_bytes).decode("utf-8")
            ext = os.path.splitext(image)[1].lower()
            mime = "jpeg" if ext in [".jpg", ".jpeg"] else ext.strip(".")
            b64_list.append(f"data:image/{mime};base64,{b64}")
        elif image:
            b64_list.append(image)
    
    image_list = b64_list[:10]
    
    payload = {
        "enable_base64_output": enable_base64_output,
        "enable_sync_mode": enable_sync_mode,
        "images": image_list,
        "prompt": prompt,
        "size": size
    }

    begin = time.time()
    response = requests.post(url, headers=headers, data=json.dumps(payload))
    if response.status_code == 200:
        result = response.json()["data"]
        request_id = result["id"]
        logger.info(f"Task submitted successfully. Request ID: {request_id}")
    else:
        logger.info(f"Error: {response.status_code}, {response.text}")
        return {
            'success': False,
            'error': f"Error: {response.status_code}, {response.text}"
        }

    url = f"{_wavespeed_base_url(base_url)}/predictions/{request_id}/result"
    headers = {"Authorization": f"Bearer {api_key}"}

    # Poll for results
    while True:
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            result = response.json()["data"]
            status = result["status"]

            if status == "completed":
                end = time.time()
                logger.info(f"Task completed in {end - begin} seconds.")
                url = result["outputs"][0]
                logger.info(f"Task completed. URL: {url}")
                return {
                    'success': True,
                    'output_path': url,
                    'message': "Image editing completed successfully."
                }
            elif status == "failed":
                logger.info(f"Task failed: {result.get('error')}")
                return {
                    'success': False,
                    'error': f"Task failed: {result.get('error')}"
                }
            else:
                logger.info(f"Task still processing. Status: {status}")
        else:
            logger.info(f"Error: {response.status_code}, {response.text}")
            return {
                'success': False,
                'error': f"Error: {response.status_code}, {response.text}"
            }


def hailuo_i2v_pro(api_key: str, prompt: str, image: str, end_image: str = None, enable_prompt_expansion: bool = True, save_path: str = None, model: str | None = "hailuo-02/i2v-standard", provider: str | None = "minimax", base_url: str | None = None):
    """
    Generate video from image using MiniMax hailuo-02 i2v-pro model.
    
    Args:
        api_key: WaveSpeed API key
        prompt: Text prompt for video generation
        image: Start image URL or local file path
        end_image: End image URL or local file path (optional)
        enable_prompt_expansion: Whether to enable prompt expansion
        save_path: Optional path to save the generated video
    
    Returns:
        dict: Result containing success status and output URL/path or error message
    """
    logger.info("Hello from WaveSpeedAI!")
    
    # Handle local image file by converting to base64
    if os.path.exists(image):
        with open(image, "rb") as f:
            img_bytes = f.read()
        b64 = base64.b64encode(img_bytes).decode("utf-8")
        ext = os.path.splitext(image)[1].lower()
        mime = "jpeg" if ext in [".jpg", ".jpeg"] else ext.strip(".")
        image_data = f"data:image/{mime};base64,{b64}"
    else:
        # Assume it's a URL
        image_data = image
    
    # Handle end image if provided
    end_image_data = None
    if end_image:
        if os.path.exists(end_image):
            with open(end_image, "rb") as f:
                img_bytes = f.read()
            b64 = base64.b64encode(img_bytes).decode("utf-8")
            ext = os.path.splitext(end_image)[1].lower()
            mime = "jpeg" if ext in [".jpg", ".jpeg"] else ext.strip(".")
            end_image_data = f"data:image/{mime};base64,{b64}"
        else:
            # Assume it's a URL
            end_image_data = end_image
    
    url = f"{_wavespeed_base_url(base_url)}/{provider or 'minimax'}/{model or 'hailuo-02/i2v-standard'}"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }
    payload = {
        "image": image_data,
        "prompt": prompt,
        "enable_prompt_expansion": enable_prompt_expansion
    }
    
    # Add end_image to payload if provided
    if end_image_data:
        payload["end_image"] = end_image_data

    begin = time.time()
    response = requests.post(url, headers=headers, data=json.dumps(payload))
    if response.status_code == 200:
        result = response.json()["data"]
        request_id = result["id"]
        logger.info(f"Task submitted successfully. Request ID: {request_id}")
    else:
        logger.info(f"Error: {response.status_code}, {response.text}")
        return {
            'success': False,
            'error': f"Error: {response.status_code}, {response.text}"
        }

    url = f"{_wavespeed_base_url(base_url)}/predictions/{request_id}/result"
    headers = {"Authorization": f"Bearer {api_key}"}

    # Poll for results
    while True:
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            result = response.json()["data"]
            status = result["status"]

            if status == "completed":
                end = time.time()
                logger.info(f"Task completed in {end - begin} seconds.")
                output_url = result["outputs"][0]
                logger.info(f"Task completed. URL: {output_url}")
                
                # Download video if save_path is provided
                if save_path:
                    resp = requests.get(output_url, stream=True)
                    resp.raise_for_status()
                    with open(save_path, "wb") as f:
                        for chunk in resp.iter_content(8192):
                            f.write(chunk)
                    return {
                        'success': True,
                        'output_path': os.path.abspath(save_path),
                        'message': "Video generated successfully."
                    }
                else:
                    return {
                        'success': True,
                        'output_url': output_url,
                        'message': "Video generated successfully."
                    }
            elif status == "failed":
                logger.info(f"Task failed: {result.get('error')}")
                return {
                    'success': False,
                    'error': f"Task failed: {result.get('error')}"
                }
            else:
                logger.info(f"Task still processing. Status: {status}")
        else:
            logger.info(f"Error: {response.status_code}, {response.text}")
            return {
                'success': False,
                'error': f"Error: {response.status_code}, {response.text}"
            }

        time.sleep(0.5)


