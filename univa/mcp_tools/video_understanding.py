from mcp.server.fastmcp import FastMCP
from typing import Any

from univa.config.mcp_config import get_mcp_section
from univa.mcp_tools.base import ToolResponse, setup_logger
from univa.utils.query_llm import multimodal_query
from univa.utils.media_index import MediaIndex



video_understanding_config = get_mcp_section("video_understanding")

# Configure logging
logger = setup_logger(__name__, "logs/mcp_tools", "video_understanding.log")
logger.info(f"Loaded video_understanding_config: {video_understanding_config}")

# Create an MCP server
mcp = FastMCP("Video_Understanding_Server")
_media_index = MediaIndex()


@mcp.tool()
def index_video_media(video_path: str, segment_duration_seconds: float = 5.0, force: bool = False) -> dict:
    """Create or reuse a durable time-coded index for a local video."""
    try:
        result = _media_index.index_video(video_path, segment_duration_seconds, force)
        result["media_index"] = {
            "index_id": result.get("index_id"),
            "source_path": result.get("source_path"),
            "metadata": result.get("metadata"),
            "segments": result.get("segments", []),
        }
        return result
    except Exception as exc:
        logger.exception("Video indexing failed")
        return {"success": False, "error": str(exc), "source_path": video_path, "segments": []}


@mcp.tool()
def update_video_index_segments(
    media_path: str,
    annotations: list[dict[str, Any]],
    replace_existing: bool = False,
) -> dict:
    """Add trusted time-coded captions, transcripts, or keywords to an index."""
    try:
        result = _media_index.enrich_segments(
            media_path, annotations, replace_existing=replace_existing
        )
        result["media_index"] = {
            "index_id": result.get("index_id"),
            "source_path": result.get("source_path"),
            "metadata": result.get("metadata"),
            "segments": result.get("segments", []),
        }
        return result
    except Exception as exc:
        logger.exception("Video index enrichment failed")
        return {"success": False, "error": str(exc), "source_path": media_path, "segments": []}


@mcp.tool()
def search_video_moments(query: str, media_path: str = "", top_k: int = 10) -> dict:
    """Search indexed captions, transcripts, and keywords and return timecodes."""
    try:
        return _media_index.search(query, media_path or None, top_k)
    except Exception as exc:
        logger.exception("Video moment search failed")
        return {"success": False, "error": str(exc), "segments": []}


@mcp.tool()
def get_video_moment(media_path: str, start_seconds: float, end_seconds: float) -> dict:
    """Return indexed segments overlapping a requested time range."""
    try:
        return _media_index.get_moment(media_path, start_seconds, end_seconds)
    except Exception as exc:
        logger.exception("Video moment lookup failed")
        return {"success": False, "error": str(exc), "segments": []}


@mcp.tool()
def vision2text_gen(prompt: str, multimodal_path: str, type: str) -> dict:
    """
    Analyzes and describes the content of a video or image based on a given prompt, converting visual information into text.
    This tool is useful for understanding ambiguous or complex visual inputs, providing detailed textual descriptions of the content.

    Args:
        prompt (str): User's instruction.
        multimodal_path (str): The path of the video or image.
        type (str): The type of the multimodal input, either "video" or "image".

    Returns:
        dict: A dictionary containing the success status and a message.
              - 'success' (bool): True if the vision content was understood successfully, False otherwise.
              - 'message' (str, optional): The details of the vision content if successful.
              - 'error' (str, optional): An error message if the operation failed.
    """
    try:
        if type == "video":
            content = multimodal_query(prompt, video_path=multimodal_path)
        elif type == "image":
            content = multimodal_query(prompt, image_path=multimodal_path)
        else:
            return ToolResponse(
                success=False,
                message="The type of the multimodal input should be either 'video' or 'image'."
            )

        return ToolResponse(
            success=True,
            message="Vision content understood successfully.",
            content=content
        )
    except Exception as e:
        return ToolResponse(
            success=False,
            message=f"An error occurred: {str(e)}"
        )



if __name__ == "__main__":
    mcp.run(transport="stdio")
