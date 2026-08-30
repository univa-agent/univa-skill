import os
from datetime import datetime
from mcp.server.fastmcp import FastMCP

from univa.config.mcp_config import get_mcp_section, get_wavespeed_config
from univa.mcp_tools.base import ToolResponse, redact_secrets, setup_logger
from univa.utils.image_process import download_image
from univa.utils.wavespeed_api import (
    text_to_image_generate as ws_text_to_image,
    seedream_v4_edit,
    seedream_v4_sequential_edit,
)
from univa.utils.volcengine_api import (
    text_to_image_generate as ark_text_to_image,
    image_to_image_generate as ark_image_to_image,
)


image_gen_config = get_mcp_section("image_gen")

logger = setup_logger(__name__, "logs/mcp_tools", "image_gen.log")
logger.info("Loaded image_gen_config: %s", redact_secrets(image_gen_config))

mcp = FastMCP("Image_Generation_Server")


def _get_image_provider():
    """Return (provider_name, api_key, provider_config)."""
    provider = image_gen_config.get("provider", "wavespeed")

    if provider == "volcengine_ark":
        ark_cfg = image_gen_config.get("volcengine_ark", {})
        return provider, ark_cfg.get("api_key", ""), ark_cfg

    wavespeed_cfg = get_wavespeed_config(image_gen_config)
    return "wavespeed", wavespeed_cfg.get("api_key", ""), wavespeed_cfg


def _save_image_from_url(image_url: str, prompt: str) -> ToolResponse:
    _time = datetime.now().strftime("%m%d%H%M%S")
    base_output_path = image_gen_config.get("base_output_path", "results/image")
    os.makedirs(base_output_path, exist_ok=True)
    image_save_path = os.path.abspath(os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        f"{base_output_path}/{_time}_{prompt[:30].replace(' ', '_')}.jpg"
    ))

    logger.info(f"Image URL: {image_url}")
    download_image(image_url, save_path=image_save_path)
    logger.info(f"Image saved to: {image_save_path}")

    return ToolResponse(
        success=True,
        output_path=image_save_path,
        message="Image generated successfully.",
    )


def _error_response(result, fallback: str) -> ToolResponse | None:
    if isinstance(result, dict) and not result.get("success", False):
        return ToolResponse(success=False, error=result.get("error", fallback))
    if result is None:
        return ToolResponse(success=False, error=fallback)
    return None


@mcp.tool()
def text2image_generate(prompt: str) -> ToolResponse:
    """Generates a new image based on a textual prompt."""
    model = image_gen_config.get("text_to_image")
    if model not in ("flux-kontext", "seedance", "seedream"):
        return ToolResponse(success=False, error=f"Unsupported text_to_image model type: {model}")

    provider, api_key, provider_cfg = _get_image_provider()
    if provider == "volcengine_ark":
        image_url = ark_text_to_image(
            api_key,
            prompt,
            model=provider_cfg.get("text_to_image_model"),
            base_url=provider_cfg.get("base_url"),
        )
    else:
        image_url = ws_text_to_image(
            api_key,
            prompt,
            model=provider_cfg.get("text_to_image_model"),
            provider=provider_cfg.get("text_to_image_provider"),
            base_url=provider_cfg.get("base_url"),
        )

    error = _error_response(image_url, "Image generation failed.")
    if error:
        return error

    return _save_image_from_url(image_url, prompt)


@mcp.tool()
def image2image_generate(prompt: str, image_path: str | list[str]) -> ToolResponse:
    """Generates or edits an image using text and reference image(s)."""
    model = image_gen_config.get("image_to_image")
    if model not in ("flux-kontext", "seedance", "seedream"):
        return ToolResponse(success=False, error=f"Unsupported image_to_image model type: {model}")

    provider, api_key, provider_cfg = _get_image_provider()
    if provider == "volcengine_ark":
        result = ark_image_to_image(
            api_key,
            prompt,
            image_path,
            model=provider_cfg.get("image_to_image_model"),
            base_url=provider_cfg.get("base_url"),
        )
        image_url = result.get("output_path") if isinstance(result, dict) and result.get("success") else result
    else:
        result = seedream_v4_edit(
            api_key,
            prompt,
            image_path,
            model=provider_cfg.get("image_to_image_model"),
            provider=provider_cfg.get("image_to_image_provider"),
            base_url=provider_cfg.get("base_url"),
        )
        image_url = result.get("output_path") if isinstance(result, dict) and result.get("success") else result

    error = _error_response(result, "Image editing failed.")
    if error:
        return error

    return _save_image_from_url(image_url, prompt)


@mcp.tool()
def sequential_image_gen(prompt: str, images: list[str], images_num: int = 2) -> ToolResponse:
    """Generates a series of related images based on input images and a prompt."""
    provider, api_key, provider_cfg = _get_image_provider()

    try:
        if provider == "volcengine_ark":
            result = ark_image_to_image(
                api_key,
                prompt,
                images,
                model=provider_cfg.get("image_to_image_model"),
                base_url=provider_cfg.get("base_url"),
            )
            error = _error_response(result, "Sequential image editing failed.")
            if error:
                return error
            output_images = [result.get("output_path")] if isinstance(result, dict) else [result]
        else:
            result = seedream_v4_sequential_edit(
                api_key=api_key,
                prompt=prompt,
                images=images,
                max_images=images_num,
                model=provider_cfg.get("sequential_image_model"),
                provider=provider_cfg.get("sequential_image_provider"),
                base_url=provider_cfg.get("base_url"),
            )
            error = _error_response(result, "Sequential image editing failed.")
            if error:
                return error
            output_images = result.get("output_path")

        output_paths = []
        for item in output_images or []:
            _time = datetime.now().strftime("%m%d%H%M%S")
            base_output_path = image_gen_config.get("base_output_path", "results/image")
            os.makedirs(base_output_path, exist_ok=True)
            image_save_path = os.path.abspath(f"{base_output_path}/{_time}_{prompt[:30].replace(' ', '_')}.jpg")
            download_image(item, save_path=image_save_path)
            output_paths.append(image_save_path)

        return ToolResponse(
            success=True,
            output_path=output_paths,
            message="Sequential image editing completed successfully.",
        )
    except Exception as e:
        return ToolResponse(
            success=False,
            error=f"Error during sequential image editing: {str(e)}",
        )


if __name__ == "__main__":
    mcp.run(transport="stdio")
