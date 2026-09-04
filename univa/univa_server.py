import asyncio
import uuid
import os
import shutil
from typing import Dict, Optional, AsyncGenerator, Any
from pathlib import Path
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request, Depends, File, UploadFile, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel, Field
from typing import List
import json
import logging
from datetime import datetime
import traceback
import re

def _init_env():
    base = Path(__file__).resolve().parents[1]
    env_file = base / ".env"
    if not env_file.exists():
        raise RuntimeError("Config missing: please copy .env.example to .env and fill your keys.")
    load_dotenv(dotenv_path=str(env_file), override=False)

_init_env()

from univa.univa_agent import PlanActSystem

from univa.config.config import config, auth_service
from univa.auth.middleware import AuthMiddleware

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

os.environ['UniVA_HTTP_SERVER_MODE'] = 'true'

app = FastAPI(title="UniVA Chat API", version="0.1.0")

# CORS middleware setting
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Auth middleware
app.add_middleware(
    AuthMiddleware,
    auth_service=auth_service,
    auth_enabled=config.get('auth_enabled', True)
)

global_plan_act_system: Optional[PlanActSystem] = None

DATA_ROOT = Path(__file__).resolve().parents[1] / "data"

def _sanitize_project_name(name: str) -> str:
    """Convert a user-facing project name into a safe data directory name."""
    normalized = re.sub(r"\s+", " ", (name or "").strip())
    safe = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", normalized)
    safe = safe.strip(" .")
    if not safe:
        raise HTTPException(status_code=400, detail="Project name is required")
    return safe[:120]

def _project_data_dir(project_id: Optional[str] = None, project_name: Optional[str] = None) -> Path:
    # Project name is the backend folder identity. Project id is only a fallback
    # for older clients that have not yet been updated.
    raw_name = project_name or project_id
    if not raw_name:
        raise HTTPException(status_code=400, detail="Project name is required")

    project_dir = DATA_ROOT / _sanitize_project_name(raw_name)
    resolved_root = DATA_ROOT.resolve()
    resolved_dir = project_dir.resolve()
    if resolved_root != resolved_dir and resolved_root not in resolved_dir.parents:
        raise HTTPException(status_code=400, detail="Invalid project directory")
    return project_dir

def _resolve_project_file_path(
    server_path: str,
    project_id: Optional[str] = None,
    project_name: Optional[str] = None,
) -> Path:
    if not server_path:
        raise HTTPException(status_code=400, detail="server_path is required")

    target = Path(server_path).resolve()
    allowed_root = (
        _project_data_dir(project_id, project_name).resolve()
        if project_id or project_name
        else DATA_ROOT.resolve()
    )

    if allowed_root != target and allowed_root not in target.parents:
        raise HTTPException(status_code=400, detail="File is outside the active project data directory")

    return target


def _build_project_context(
    project_id: Optional[str] = None,
    project_name: Optional[str] = None,
) -> Optional[Dict[str, str]]:
    if not project_id and not project_name:
        return None

    project_dir = _project_data_dir(project_id, project_name)
    return {
        "project_id": project_id or "",
        "project_name": project_name or project_id or "",
        "safe_project_name": project_dir.name,
        "data_dir": str(project_dir),
    }


async def initialize_global_agents() -> PlanActSystem:
    global global_plan_act_system
    
    if global_plan_act_system:
        return global_plan_act_system
    
    config_path = config.get('mcp_servers_config')
    
    mcp_commands = []
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            mcp_config = json.load(f)
        mcp_servers = mcp_config.get("mcpServers", {})
        logger.info(f"Loaded {len(mcp_servers)} MCP servers from config")
        
        # construct mcp commands
        for server_name, server_config in mcp_servers.items():
            command = server_config.get("command", "")
            args = server_config.get("args", [])
            env = server_config.get("env", {})
            
            full_command = f"{command} {' '.join(args)}"
            
            mcp_commands.append(full_command)
            logger.info(f"Registered MCP server '{server_name}': {full_command}")
        
    except FileNotFoundError:
        logger.warning(f"MCP config file not found: {config_path}, using default")
    except Exception as e:
        logger.error(f"Error loading MCP config: {e}")
    
    global_plan_act_system = PlanActSystem(mcp_command=mcp_commands)
    await global_plan_act_system.__aenter__()
    
    logger.info("Global PlanActSystem initialized")
    
    return global_plan_act_system



class ChatRequest(BaseModel):
    prompt: str
    session_id: Optional[str] = None
    model: Optional[str] = None
    project_id: Optional[str] = None
    project_name: Optional[str] = None


class ProjectRenameRequest(BaseModel):
    old_project_name: str
    new_project_name: str


class DeleteFileRequest(BaseModel):
    server_path: str
    project_id: Optional[str] = None
    project_name: Optional[str] = None


class ResumeRequest(BaseModel):
    session_id: str
    continuation_token: str = ""
    user_input: str = ""


class HealthResponse(BaseModel):
    status: str
    timestamp: str


async def stream_chat_response(
    user_id: str,
    session_id: str,
    user_prompt: str,
    is_frontend: bool = False,
    project_context: Optional[Dict[str, str]] = None,
):
    """
    Stream chat response as SSE

    return SSE stream compatible with useCompletion
    """
    try:
        system = await initialize_global_agents()

        logger.info(f"Streaming task execution for user {user_id}, session {session_id}")

        # calling agent's streaming execution method
        async for event in system.execute_task_stream(
            session_id,
            user_prompt,
            is_frontend=is_frontend,
            project_context=project_context,
            owner_id=user_id,
        ):
            if event.get('type') == 'finish':
                event['session_id'] = session_id
            
            json_str = json.dumps(event, ensure_ascii=False)
            logger.info(f"Sending SSE event: {event.get('type', 'unknown')}")
            logger.debug(f"Event details:\n{json_str}")
            
            sse_message = f"data: {json_str}\n\n"
            yield sse_message.encode('utf-8') if isinstance(sse_message, str) else sse_message
            
            await asyncio.sleep(0.01)
        
        logger.info("Stream completed successfully")
        
    except Exception as e:
        logger.error(f"Error in stream_chat_response: {e}")
        logger.error(traceback.format_exc())
        error_message = f"data: {json.dumps({'type': 'error', 'message': str(e)}, ensure_ascii=False)}\n\n"
        yield error_message.encode('utf-8') if isinstance(error_message, str) else error_message

@app.post("/chat/stream")
async def chat(request: ChatRequest, req: Request):
    """
    Unified chat request handling endpoint - using PlanActSystem (streaming)

    Access code is passed via X-Access-Code header (handled by auth middleware)
    Returns a streaming response compatible with Vercel AI SDK
    """
    try:
        # get user_id and access_code from request state (injected by auth middleware)
        user_id = getattr(req.state, 'user_id', 'anonymous')
        access_code = getattr(req.state, 'access_code', None)
        
        # check conversation limit
        if access_code and config.get('auth_enabled', True):
            if not auth_service.check_conversation_limit(access_code):
                code_info = auth_service.get_access_code_info(access_code)
                if code_info:
                    raise HTTPException(
                        status_code=429,
                        detail=f"Conversation limit reached ({code_info['conversation_count']}/{code_info['max_conversations']}). Please contact administrator."
                    )
                else:
                    raise HTTPException(status_code=429, detail="Conversation limit reached")
            
            # increment conversation count
            auth_service.increment_conversation_count(access_code)
        
        # generate session_id if not provided
        session_id = request.session_id or str(uuid.uuid4())
        
        logger.info(f"POST /chat/stream - user: {user_id}, session: {session_id}, prompt: {request.prompt[:50]}...")
        
        # Detect if request is from the frontend editor
        is_frontend = (
            req.headers.get('X-UniVA-Client', '') == 'editor'
        )
        project_context = (
            _build_project_context(request.project_id, request.project_name)
            if is_frontend else None
        )
        return StreamingResponse(
            stream_chat_response(
                user_id, session_id, request.prompt, is_frontend, project_context
            ),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error processing chat request: {e}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/chat/stream")
async def chat_get(
    prompt: str,
    session_id: Optional[str] = None,
    accessCode: Optional[str] = None,
    project_id: Optional[str] = None,
    project_name: Optional[str] = None,
    request: Request = None
):
    """
    Get method chat endpoint for streaming responses.
    Note: Access code is passed via URL parameter due to EventSource limitations.
    Returns a streaming response compatible with Vercel AI SDK.
    """
    try:
        # If accessCode is provided, validate it
        if accessCode and config.get('auth_enabled', True):
            user_id = auth_service.validate_access_code(accessCode)
            if not user_id:
                raise HTTPException(status_code=401, detail="Invalid access code")
            
            # Check conversation limit
            if not auth_service.check_conversation_limit(accessCode):
                code_info = auth_service.get_access_code_info(accessCode)
                if code_info:
                    raise HTTPException(
                        status_code=429,
                        detail=f"Conversation limit reached ({code_info['conversation_count']}/{code_info['max_conversations']}). Please contact administrator."
                    )
                else:
                    raise HTTPException(status_code=429, detail="Conversation limit reached")
            
            auth_service.increment_conversation_count(accessCode)
            
            # Inject user_id into request state for consistency
            request.state.user_id = user_id
        else:
            # get user_id from request state (injected by auth middleware)
            user_id = getattr(request.state, 'user_id', 'anonymous')
        
        sid = session_id or str(uuid.uuid4())
        # Detect frontend editor client (via query param for EventSource compatibility)
        is_frontend = request.query_params.get('client', '') == 'editor'
        project_context = (
            _build_project_context(project_id, project_name)
            if is_frontend else None
        )

        return StreamingResponse(
            stream_chat_response(user_id, sid, prompt, is_frontend, project_context),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error processing chat request: {e}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/files/upload")
async def upload_file(
    file: UploadFile = File(...),
    project_id: Optional[str] = Form(None),
    project_name: Optional[str] = Form(None),
):
    """
    Upload a file from the frontend editor to the current project's server data
    directory and return its absolute backend path.
    """
    try:
        upload_dir = _project_data_dir(project_id, project_name)
        upload_dir.mkdir(parents=True, exist_ok=True)

        # Sanitize filename and avoid collisions inside this project only.
        safe_name = (file.filename or "upload").replace("..", "").replace("/", "_").replace("\\", "_")
        dest = upload_dir / safe_name
        if dest.exists():
            base, ext = os.path.splitext(safe_name)
            dest = upload_dir / f"{base}_{uuid.uuid4().hex[:6]}{ext}"

        content = await file.read()
        with open(dest, "wb") as f:
            f.write(content)

        logger.info(f"File uploaded: {safe_name} → {dest} ({len(content)} bytes)")
        return {
            "success": True,
            "project_id": project_id,
            "project_name": project_name,
            "project_dir": str(upload_dir.resolve()),
            "original_name": file.filename,
            "server_path": str(dest.resolve()),
            "size_bytes": len(content),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"File upload failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/files/delete")
async def delete_project_file(request: DeleteFileRequest):
    """Delete one uploaded/generated file from the active project's data directory."""
    try:
        target = _resolve_project_file_path(
            request.server_path,
            request.project_id,
            request.project_name,
        )

        if not target.exists():
            return {
                "success": True,
                "deleted": False,
                "server_path": str(target),
                "message": "File already absent",
            }

        if not target.is_file():
            raise HTTPException(status_code=400, detail="Only files can be deleted")

        target.unlink()
        logger.info(f"Deleted project file: {target}")
        return {
            "success": True,
            "deleted": True,
            "server_path": str(target),
            "message": "File deleted",
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete project file: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/files/project/rename")
async def rename_project_files(request: ProjectRenameRequest):
    """Rename a backend project data directory when the frontend project is renamed."""
    try:
        old_dir = _project_data_dir(project_name=request.old_project_name)
        new_dir = _project_data_dir(project_name=request.new_project_name)

        if old_dir == new_dir:
            return {
                "moved": False,
                "old_dir": str(old_dir.resolve()),
                "new_dir": str(new_dir.resolve()),
                "message": "Project directory unchanged",
            }

        DATA_ROOT.mkdir(parents=True, exist_ok=True)
        if not old_dir.exists():
            return {
                "moved": False,
                "old_dir": str(old_dir.resolve()),
                "new_dir": str(new_dir.resolve()),
                "message": "Old project directory does not exist",
            }

        if new_dir.exists():
            for child in old_dir.iterdir():
                target = new_dir / child.name
                if target.exists():
                    stem = target.stem
                    suffix = target.suffix
                    target = new_dir / f"{stem}_{uuid.uuid4().hex[:6]}{suffix}"
                shutil.move(str(child), str(target))
            old_dir.rmdir()
        else:
            shutil.move(str(old_dir), str(new_dir))

        return {
            "moved": True,
            "old_dir": str(old_dir.resolve()),
            "new_dir": str(new_dir.resolve()),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to rename project files: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/files/project/{project_id}")
async def delete_project_files(project_id: str, project_name: Optional[str] = None):
    """Delete only the backend files for the specified project."""
    try:
        project_dir = _project_data_dir(project_id, project_name)
        if not project_dir.exists():
            return {"deleted": 0, "message": "Project upload directory does not exist"}

        deleted = 0
        for root, _dirs, filenames in os.walk(project_dir):
            deleted += len(filenames)

        shutil.rmtree(project_dir)
        logger.info(f"Deleted project upload directory: {project_dir}")

        return {"deleted": deleted, "message": f"Deleted {deleted} files"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete project files: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/health")
async def health():
    return HealthResponse(
        status="healthy",
        timestamp=datetime.now().isoformat()
    )

@app.get("/")
async def root():
    return {"message": "UniVA Chat API is running", "version": "0.3.0-pipeline"}


@app.post("/chat/resume")
async def resume_pipeline(request: ResumeRequest, req: Request):
    """
    Resume an interactive pipeline from a suspended (awaiting_human) state.

    Accepts the user's choice/confirmation input and continues the pipeline
    execution from the suspended stage.
    """
    try:
        system = await initialize_global_agents()

        orchestrator = getattr(system, '_pipeline_orchestrator', None)
        if not orchestrator:
            raise HTTPException(status_code=500, detail="Pipeline orchestrator not available")

        owner_id = getattr(req.state, 'user_id', 'anonymous')
        if not request.continuation_token:
            raise HTTPException(status_code=400, detail="continuation_token is required")

        state = orchestrator.get_state(request.session_id)
        if not state:
            raise HTTPException(
                status_code=404,
                detail=f"No active pipeline for session '{request.session_id}'. "
                       f"The session may have expired or already completed."
            )

        if state.owner_id and state.owner_id != owner_id:
            # Do not reveal another user's session status.
            raise HTTPException(
                status_code=404,
                detail=f"No active pipeline for session '{request.session_id}'",
            )

        if state.status != "awaiting_human":
            raise HTTPException(
                status_code=409,
                detail=f"Pipeline is not awaiting input (status: {state.status})"
            )

        # Process user input through the orchestrator. The owner and token are
        # checked before any stage can execute.
        try:
            state = await orchestrator.resume(
                request.user_input,
                system,
                request.session_id,
                continuation_token=request.continuation_token,
                owner_id=owner_id,
            )
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

        return {
            "session_id": request.session_id,
            "pipeline": state.pipeline_name,
            "status": state.status,
            "current_stage": state.current_stage_index,
            "interaction_stage": state.interaction_stage,
            "continuation_token": state.continuation_token,
            "artifacts": {k: str(v)[:500] for k, v in state.artifacts.items()},
            "budget": state.budget.summary() if state.budget else None,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error resuming pipeline: {e}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/chat/pipeline/{session_id}")
async def get_pipeline_state(session_id: str, req: Request):
    """
    Get the current state of an interactive pipeline for a given session.
    Useful for frontend to poll status or recover from disconnection.
    """
    try:
        system = await initialize_global_agents()

        orchestrator = getattr(system, '_pipeline_orchestrator', None)
        if not orchestrator:
            raise HTTPException(status_code=500, detail="Pipeline orchestrator not available")

        owner_id = getattr(req.state, 'user_id', 'anonymous')
        state = orchestrator.get_state(session_id)
        if not state:
            raise HTTPException(
                status_code=404,
                detail=f"No active pipeline for session '{session_id}'"
            )

        if state.owner_id and state.owner_id != owner_id:
            raise HTTPException(status_code=404, detail=f"No active pipeline for session '{session_id}'")

        return {
            "session_id": session_id,
            "pipeline": state.pipeline_name,
            "status": state.status,
            "current_stage_index": state.current_stage_index,
            "interaction_stage": state.interaction_stage,
            "interaction_prompt": state.interaction_prompt,
            "artifacts_count": len(state.artifacts),
            "budget": state.budget.summary() if state.budget else None,
            "stage_timeline": state.stage_timeline,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting pipeline state: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ── Skill & Pipeline API Endpoints ─────────────────────────────────────

from univa.utils.skill_loader import get_skill_loader





def _get_loader():
    """Get skill loader for the current project."""
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return get_skill_loader(project_root)


@app.get("/skills")
async def list_skills(category: Optional[str] = None):
    """
    List all available skills, optionally filtered by category.

    Categories: core, creative, meta, pipelines
    """
    try:
        loader = _get_loader()
        skills = loader.list_skills(category)
        return {
            "skills": skills,
            "count": len(skills),
            "category": category or "all"
        }
    except Exception as e:
        logger.error(f"Error listing skills: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/skills/{skill_path:path}")
async def get_skill(skill_path: str):
    """
    Get the content of a specific skill by its path.

    Example: /skills/core/wavespeed-video-gen
    """
    try:
        loader = _get_loader()
        content = loader.load_skill(skill_path)
        return {
            "skill_path": skill_path,
            "content": content
        }
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Skill not found: {skill_path}")
    except Exception as e:
        logger.error(f"Error loading skill {skill_path}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/skills/search/{tool_name}")
async def find_skills_for_tool(tool_name: str):
    """
    Find skills relevant to a specific MCP tool.

    Example: /skills/search/text2video_gen
    """
    try:
        loader = _get_loader()
        skills = loader.find_skills_for_tool(tool_name)
        return {
            "tool": tool_name,
            "matching_skills": skills,
            "count": len(skills)
        }
    except Exception as e:
        logger.error(f"Error searching skills for tool {tool_name}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/pipelines")
async def list_pipelines():
    """List all available pipelines with their metadata."""
    try:
        loader = _get_loader()
        pipeline_names = loader.list_pipelines()
        pipelines = []
        for name in pipeline_names:
            pipeline_def = loader.load_pipeline(name)
            if pipeline_def:
                pipelines.append({
                    "name": name,
                    "version": pipeline_def.get("version", "?"),
                    "description": pipeline_def.get("description", ""),
                    "category": pipeline_def.get("category", ""),
                    "stability": pipeline_def.get("stability", "unknown"),
                    "stages": [
                        {
                            "name": s.get("name"),
                            "produces": s.get("produces", []),
                            "tools_available": s.get("tools_available", []),
                            "human_approval_default": s.get("human_approval_default", False),
                        }
                        for s in pipeline_def.get("stages", [])
                    ]
                })
        return {
            "pipelines": pipelines,
            "count": len(pipelines)
        }
    except Exception as e:
        logger.error(f"Error listing pipelines: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/pipelines/{pipeline_name}")
async def get_pipeline(pipeline_name: str):
    """
    Get the full definition of a specific pipeline.

    Example: /pipelines/story-video
    """
    try:
        loader = _get_loader()
        pipeline_def = loader.load_pipeline(pipeline_name)
        if not pipeline_def:
            raise HTTPException(status_code=404, detail=f"Pipeline not found: {pipeline_name}")
        return pipeline_def
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error loading pipeline {pipeline_name}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/pipelines/{pipeline_name}/stages/{stage_name}")
async def get_pipeline_stage(pipeline_name: str, stage_name: str):
    """
    Get the full context for a specific pipeline stage, including
    the stage director skill content, review criteria, and tool requirements.

    Example: /pipelines/story-video/stages/assets
    """
    try:
        loader = _get_loader()
        context = loader.get_pipeline_stage_context(pipeline_name, stage_name)
        if not context:
            raise HTTPException(
                status_code=404,
                detail=f"Stage '{stage_name}' not found in pipeline '{pipeline_name}'"
            )
        return context
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error loading stage {stage_name} from {pipeline_name}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


def verify_admin(req: Request):
    """verify admin access code from request"""
    admin_code = config.get('admin_access_code')
    logger.info(f"verify_admin: admin_code from config = {admin_code[:8] if admin_code else 'None'}...")
    
    if not admin_code:
        logger.error("Admin access code not configured in config")
        raise HTTPException(status_code=500, detail="Admin access code not configured")
    
    access_code = getattr(req.state, 'access_code', None)
    logger.info(f"verify_admin: access_code from request = {access_code[:8] if access_code else 'None'}...")
    
    if not access_code:
        logger.warning("Access code not found in request state")
        raise HTTPException(status_code=401, detail="Access code required")
    
    if access_code != admin_code:
        logger.warning(f"Access code mismatch: provided={access_code[:8]}..., expected={admin_code[:8]}...")
        raise HTTPException(status_code=403, detail="Admin access required")
    
    logger.info("Admin verification successful")
    return True


class CreateAccessCodeRequest(BaseModel):
    user_id: str
    description: str = ""
    max_conversations: Optional[int] = None


class BatchCreateAccessCodesRequest(BaseModel):
    count: int
    user_id_prefix: str = "user"
    description: str = ""
    max_conversations: Optional[int] = None


class UpdateAccessCodeRequest(BaseModel):
    description: Optional[str] = None
    enabled: Optional[bool] = None
    max_conversations: Optional[int] = None


class BatchDeleteRequest(BaseModel):
    access_codes: List[str]


class ImportCodesRequest(BaseModel):
    codes: List[Dict[str, Any]]
    overwrite: bool = False


@app.post("/admin/access-codes")
async def create_access_code(
    request: CreateAccessCodeRequest,
    req: Request = None,
    _: None = Depends(verify_admin)
):
    """create a new access code (admin only)"""
    try:
        access_code = auth_service.add_access_code(
            request.user_id,
            request.description,
            max_conversations=request.max_conversations
        )
        logger.info(f"Admin created access code for user {request.user_id}")
        return {
            "access_code": access_code,
            "user_id": request.user_id,
            "max_conversations": request.max_conversations
        }
    except Exception as e:
        logger.error(f"Error creating access code: {e}")
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/admin/access-codes/batch")
async def batch_create_access_codes(
    request: BatchCreateAccessCodesRequest,
    req: Request = None,
    _: None = Depends(verify_admin)
):
    """create multiple access codes in batch (admin only)"""
    try:
        if request.count <= 0 or request.count > 100:
            raise HTTPException(status_code=400, detail="Count must be between 1 and 100")
        
        created_codes = []
        for i in range(request.count):
            user_id = f"{request.user_id_prefix}_{i+1}"
            access_code = auth_service.add_access_code(
                user_id,
                request.description,
                max_conversations=request.max_conversations
            )
            created_codes.append({
                "access_code": access_code,
                "user_id": user_id,
                "max_conversations": request.max_conversations
            })
        
        logger.info(f"Admin batch created {len(created_codes)} access codes")
        return {"codes": created_codes, "count": len(created_codes)}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error batch creating access codes: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/admin/access-codes/stats")
async def get_access_codes_stats(
    req: Request = None,
    _: None = Depends(verify_admin)
):
    """get statistics about access codes (admin only)"""
    try:
        codes = auth_service.list_access_codes()
        
        total_codes = len(codes)
        enabled_codes = sum(1 for c in codes if c['enabled'])
        disabled_codes = total_codes - enabled_codes
        
        total_usage = sum(c['usage_count'] for c in codes)
        total_conversations = sum(c['conversation_count'] for c in codes)
        
        # calculate limited vs unlimited codes
        limited_codes = sum(1 for c in codes if c['max_conversations'] is not None)
        unlimited_codes = total_codes - limited_codes
        
        # calculate exhausted codes
        exhausted_codes = sum(
            1 for c in codes
            if c['max_conversations'] is not None
            and c['conversation_count'] >= c['max_conversations']
        )
        
        # recently used codes
        recent_used = sorted(
            [c for c in codes if c['last_used']],
            key=lambda x: x['last_used'],
            reverse=True
        )[:10]
        
        stats = {
            "total_codes": total_codes,
            "enabled_codes": enabled_codes,
            "disabled_codes": disabled_codes,
            "limited_codes": limited_codes,
            "unlimited_codes": unlimited_codes,
            "exhausted_codes": exhausted_codes,
            "total_usage": total_usage,
            "total_conversations": total_conversations,
            "recent_used": recent_used
        }
        
        logger.info("Admin retrieved access codes statistics")
        return stats
    except Exception as e:
        logger.error(f"Error getting access codes stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/admin/access-codes/export/json")
async def export_access_codes(
    req: Request = None,
    _: None = Depends(verify_admin)
):
    """export all access codes as JSON (admin only)"""
    try:
        codes = auth_service.list_access_codes()
        logger.info(f"Admin exported {len(codes)} access codes")
        return JSONResponse(
            content={"codes": codes, "exported_at": datetime.now().isoformat()},
            headers={
                "Content-Disposition": f"attachment; filename=access_codes_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            }
        )
    except Exception as e:
        logger.error(f"Error exporting access codes: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/admin/access-codes")
async def list_access_codes(
    search: Optional[str] = None,
    enabled: Optional[bool] = None,
    skip: int = 0,
    limit: int = 50,
    req: Request = None,
    _: None = Depends(verify_admin)
):
    """list access codes with optional filtering and pagination (admin only)"""
    try:
        codes = auth_service.list_access_codes()
        
        # filtering
        if search:
            search_lower = search.lower()
            codes = [
                c for c in codes
                if search_lower in c['user_id'].lower()
                or search_lower in c['description'].lower()
                or search_lower in c['access_code'].lower()
            ]
        
        if enabled is not None:
            codes = [c for c in codes if c['enabled'] == enabled]
        
        total = len(codes)
        
        # pagination
        codes = codes[skip:skip + limit]
        
        logger.info(f"Admin listed {len(codes)} access codes (total: {total})")
        return {
            "codes": codes,
            "total": total,
            "skip": skip,
            "limit": limit
        }
    except Exception as e:
        logger.error(f"Error listing access codes: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/admin/access-codes/{access_code}")
async def get_access_code(
    access_code: str,
    req: Request = None,
    _: None = Depends(verify_admin)
):
    """get details of a specific access code (admin only)"""
    try:
        code_info = auth_service.get_access_code_info(access_code)
        if not code_info:
            raise HTTPException(status_code=404, detail="Access code not found")
        return code_info
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting access code: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.put("/admin/access-codes/{access_code}")
async def update_access_code(
    access_code: str,
    request: UpdateAccessCodeRequest,
    req: Request = None,
    _: None = Depends(verify_admin)
):
    """update an existing access code (admin only)"""
    try:
        code_info = auth_service.get_access_code_info(access_code)
        if not code_info:
            raise HTTPException(status_code=404, detail="Access code not found")
        
        # update fields
        if request.enabled is not None:
            auth_service.enable_access_code(access_code, request.enabled)
        
        if request.max_conversations is not None:
            auth_service.set_conversation_limit(access_code, request.max_conversations)
        
        if request.description is not None:
            # update description
            if access_code in auth_service.config.access_codes:
                auth_service.config.access_codes[access_code].description = request.description
                auth_service._save_config()
        
        logger.info(f"Admin updated access code: {access_code[:8]}...")
        return {"message": "Access code updated", "access_code": access_code}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating access code: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/admin/access-codes/{access_code}")
async def delete_access_code(
    access_code: str,
    req: Request = None,
    _: None = Depends(verify_admin)
):
    """delete an access code (admin only)"""
    try:
        if auth_service.remove_access_code(access_code):
            logger.info(f"Admin deleted access code: {access_code[:8]}...")
            return {"message": "Access code deleted"}
        raise HTTPException(status_code=404, detail="Access code not found")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting access code: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/admin/access-codes/batch-delete")
async def batch_delete_access_codes(
    request: BatchDeleteRequest,
    req: Request = None,
    _: None = Depends(verify_admin)
):
    """delete multiple access codes in batch (admin only)"""
    try:
        deleted_count = 0
        errors = []
        
        for code in request.access_codes:
            try:
                if auth_service.remove_access_code(code):
                    deleted_count += 1
                else:
                    errors.append({"code": code, "error": "Not found"})
            except Exception as e:
                errors.append({"code": code, "error": str(e)})
        
        logger.info(f"Admin batch deleted {deleted_count} access codes")
        return {
            "deleted_count": deleted_count,
            "errors": errors
        }
    except Exception as e:
        logger.error(f"Error batch deleting access codes: {e}")
        raise HTTPException(status_code=500, detail=str(e))




@app.post("/admin/access-codes/import/json")
async def import_access_codes(
    request: ImportCodesRequest,
    req: Request = None,
    _: None = Depends(verify_admin)
):
    """from JSON import access codes (admin only)"""
    try:
        imported_count = 0
        skipped_count = 0
        errors = []
        
        for code_data in request.codes:
            try:
                access_code = code_data.get('access_code')
                user_id = code_data.get('user_id')
                
                if not access_code or not user_id:
                    errors.append({"code": access_code, "error": "Missing required fields"})
                    continue
                
                if access_code in auth_service.config.access_codes:
                    if not request.overwrite:
                        skipped_count += 1
                        continue
                    else:
                        auth_service.remove_access_code(access_code)
                
                auth_service.add_access_code(
                    user_id=user_id,
                    description=code_data.get('description', ''),
                    access_code=access_code,
                    max_conversations=code_data.get('max_conversations')
                )
                
                if access_code in auth_service.config.access_codes:
                    code_info = auth_service.config.access_codes[access_code]
                    code_info.enabled = code_data.get('enabled', True)
                    code_info.usage_count = code_data.get('usage_count', 0)
                    code_info.conversation_count = code_data.get('conversation_count', 0)
                    if code_data.get('last_used'):
                        try:
                            code_info.last_used = datetime.fromisoformat(code_data['last_used'].replace('Z', '+00:00'))
                        except:
                            pass
                    auth_service._save_config()
                
                imported_count += 1
            except Exception as e:
                errors.append({"code": code_data.get('access_code'), "error": str(e)})
        
        logger.info(f"Admin imported {imported_count} access codes (skipped: {skipped_count})")
        return {
            "imported_count": imported_count,
            "skipped_count": skipped_count,
            "errors": errors
        }
    except Exception as e:
        logger.error(f"Error importing access codes: {e}")
        raise HTTPException(status_code=500, detail=str(e))




@app.put("/admin/access-codes/{access_code}/conversation-limit")
async def set_conversation_limit(
    access_code: str,
    max_conversations: Optional[int] = None,
    req: Request = None,
    _: None = Depends(verify_admin)
):
    """set the conversation limit for an access code (admin)
    
    Args:
        access_code: access code
        max_conversations: maximum number of conversations (None for unlimited)
    """
    try:
        if auth_service.set_conversation_limit(access_code, max_conversations):
            logger.info(f"Admin set conversation limit for {access_code[:8]}... to {max_conversations or 'unlimited'}")
            return {
                "message": f"Conversation limit set to {max_conversations or 'unlimited'}",
                "access_code": access_code,
                "max_conversations": max_conversations
            }
        raise HTTPException(status_code=404, detail="Access code not found")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error setting conversation limit: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/admin/access-codes/{access_code}/reset-conversation-count")
async def reset_conversation_count(
    access_code: str,
    req: Request = None,
    _: None = Depends(verify_admin)
):
    """reset the conversation count for an access code (admin)
    
    Args:
        access_code: access code
    """
    try:
        if auth_service.reset_conversation_count(access_code):
            logger.info(f"Admin reset conversation count for {access_code[:8]}...")
            code_info = auth_service.get_access_code_info(access_code)
            return {
                "message": "Conversation count reset successfully",
                "access_code": access_code,
                "conversation_count": code_info['conversation_count'] if code_info else 0
            }
        raise HTTPException(status_code=404, detail="Access code not found")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error resetting conversation count: {e}")
        raise HTTPException(status_code=500, detail=str(e))



@app.get("/access-code/status")
async def get_access_code_status(req: Request):
    """
    get access code status info (user)
    returns the status of the current access code, including:
    - enabled: whether the code is enabled
    - usage_count: total usage count
    - conversation_count: number of conversations used
    - max_conversations: maximum conversation limit (None means unlimited)
    - remaining_conversations: remaining conversations (None means unlimited)
    - last_used: last used timestamp
    - created_at: creation timestamp
    """
    try:
        # get access_code from request state (injected by auth middleware)
        access_code = getattr(req.state, 'access_code', None)
        
        if not access_code:
            raise HTTPException(status_code=401, detail="Access code not provided")
        
        code_info = auth_service.get_access_code_info(access_code)
        
        if not code_info:
            raise HTTPException(status_code=404, detail="Access code not found")
        
        remaining_conversations = None
        if code_info['max_conversations'] is not None:
            remaining_conversations = code_info['max_conversations'] - code_info['conversation_count']
            remaining_conversations = max(0, remaining_conversations)
        
        return {
            "enabled": code_info['enabled'],
            "usage_count": code_info['usage_count'],
            "conversation_count": code_info['conversation_count'],
            "max_conversations": code_info['max_conversations'],
            "remaining_conversations": remaining_conversations,
            "last_used": code_info['last_used'],
            "created_at": code_info['created_at']
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting access code status: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    

    


if __name__ == "__main__":
    import uvicorn
    host = os.getenv("UNIVA_SERVER_HOST", "0.0.0.0")
    port = int(os.getenv("UNIVA_SERVER_PORT", "8000"))
    uvicorn.run(app, host=host, port=port)
