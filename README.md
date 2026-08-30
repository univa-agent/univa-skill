# UniVA

<p align="center">
  <a href="https://univa.online"><img src="https://img.shields.io/badge/Project-Website-orange" alt="Project Website"></a>
  <a href="https://arxiv.org/abs/2511.08521"><img src="https://img.shields.io/badge/Paper-arXiv-brightgreen" alt="Paper"></a>
  <a href="https://huggingface.co/datasets/UniVA-Agent/UniVA-Bench"><img src="https://img.shields.io/badge/Benchmark-UniVA--Bench-yellow" alt="Benchmark"></a>
  <a href="https://huggingface.co/spaces/UniVA-Agent/UniVA-Leaderboard"><img src="https://img.shields.io/badge/Leaderboard-HuggingFace-gold" alt="Leaderboard"></a>
  <a href="https://discord.gg/85GkGW897V"><img src="https://img.shields.io/badge/Community-Discord-blueviolet" alt="Discord"></a>
</p>


<table>
  <tr>
    <td width="50%" align="center">
        <img src="docs/assets/readme/Univa-skill.png" alt="Sports crowd sequence video preview" width="60%">
    </td>
  </tr>
</table>


UniVA turns a creative request into a reviewed production plan, then executes the approved plan through existing MCP media tools. It is designed for agentic video work: Codex, Claude Code, a backend API, or the Web editor can all use the same skill system, approval gates, user preferences, and delivery verification.

## What UniVA Can Do

| Capability | What happens |
|---|---|
| Text-to-video | Expands a short brief into shot-level prompts, durations, transitions, and final video generation requests, with multiple reviews to ensure generation quality. |
| Image-to-video | Animates reference images while preserving visual anchors and requested motion. |
| Image generation/editing | Generates images, image variants, and sequential image outputs through the same review gate. |
| Video editing | Produces reviewed edit proposals for style transfer, repainting, depth/background edits, and pose-reference edits. |
| Video understanding | Analyzes content, style, rhythm, structure, reusable prompts, and downstream editing guidance. |
| Audio and speech | Plans and generates BGM, ambience, SFX, transition sounds, speech, and audio that fits the target video. |
| User preferences | Saves reusable style, pacing, camera, output, and workflow preferences as repo-local skills. |
| Compound tasks | Uses existing content to support generation, editing, analysis, and final composition across multi-turn conversations. |
| Web editor | Provides chat, media library, project-scoped uploads, and timeline-oriented workflows. |


## Example Prompts

When you do not have a clear concept yet, you can use a simple fuzzy prompt or one sentence. UniVA will help expand the content with more detail, shots, storyboard structure, and related planning. You do not need to worry that it will immediately generate content far away from the intended plot, because you can review and guide revisions to UniVA's expanded prompts before generation.

You can also provide a rich prompt plan. UniVA will polish it according to the review principles so the final prompt is more accurate and better aligned with the creative target.

```text
Generate a 5-second product promo video for an electric sedan.
Analyze this video and extract reusable shot rhythm, camera language, and style prompts.
Convert this video to watercolor animation while preserving motion and composition.
Save preference: future product videos should use calm tech style, minimal transitions, and no voiceover.
Create a three-shot travel video with ambience, smooth transitions, and no narration.
```

## Demo Gallery

| Stylized Creation | Product Promo | Visual Effects |
|---|---|---|
| [![Old Chinese painting](docs/assets/readme/oldpaiting.jpg)] | [![EV ad poster](docs/assets/readme/noodles.png)] | [![Smooth crossfade poster](docs/assets/readme/winter-train.png)] |
| Chinese traditional landscape painting | Close-up of spaghetti | The sci-fi blues train is heading to the city |

### Video Gallery

<table>
  <tr>
    <td width="50%">
      <a href="docs/assets/readme/tokyo-olympics-promo-with-audio.mp4">
        <img src="docs/assets/readme/olympics.png" alt="Tokyo Olympics-style promo video preview" width="100%">
      </a>
      <br><sub><a href="docs/assets/readme/tokyo-olympics-promo-with-audio.mp4">Watch video</a> - Tokyo Olympics-style promo with planned multi-shot composition and storyboard packaging.</sub>
    </td>
    <td width="50%">
      <a href="docs/assets/readme/stadium-crowd-story.mp4">
        <img src="docs/assets/readme/smooth-crossfade-poster.jpg" alt="Sports crowd sequence video preview" width="100%">
      </a>
      <br><sub><a href="docs/assets/readme/stadium-crowd-story.mp4">Watch video</a> - Sports crowd sequence with dynamic camera changes and multi-shot fusion.</sub>
    </td>
  </tr>
  <tr>
    <td width="50%">
      <a href="docs/assets/readme/comic-action-short.mp4">
        <img src="docs/assets/readme/anime-fight-poster.jpg" alt="Comic-style action short video preview" width="100%">
      </a>
      <br><sub><a href="docs/assets/readme/comic-action-short.mp4">Watch video</a> - Comic-style action short with stylized motion, captions, and character-focused composition.</sub>
    </td>
    <td width="50%">
      <a href="docs/assets/readme/desert-car.mp4">
        <img src="docs/assets/readme/desert.png" alt="Desert off-road vehicle short video preview" width="100%">
      </a>
      <br><sub><a href="docs/assets/readme/desert-car.mp4">Watch video</a> - Desert off-road vehicle short featuring a red vehicle and dramatic light.</sub>
    </td>
  </tr>
</table>

## Why UniVA Is Different

UniVA is not just a wrapper around a video model. It is a production control layer.

- **Skill-driven execution**: every capability is documented as a skill contract under `skills/`.
- **MCP-native tools**: generation, editing, understanding, audio, merge, and tracking are exposed as modular MCP tools that can evolve flexibly.
- **Review before generation**: media-producing and media-mutating tools stop at a concrete plan/review artifact before execution to protect generation quality.
- **Exact approved handoff**: the final tool call uses the approved prompt, timing, source paths, references, and parameters to avoid wasting quota.
- **Agent friendly**: Codex and Claude Code can directly use all UniVA skills without starting the backend.
- **Frontend ready**: the built-in backend supports a Web interface for chat, uploads, project context, and workflows.
- **Preference memory**: multiple user-level preference skills guide future outputs so generated media can keep a distinctive personal style.

## Architecture

```text
User request
  -> Skills and preference loading
  -> Intent routing
  -> Plan / proposal / storyboard
  -> Validation and human review
  -> Approved MCP tool execution
  -> Output verification
  -> Delivery report
```

```text
skills/
  core/              MCP tool contracts
  creative/          prompt, brief, story, style, duration, audio, quality guidance
  meta/              routing, review, checkpoint, output, preference protocols
  themes/            generation quality enhancers
  pipelines/         stage director skills

pipeline_defs/       executable pipeline manifests
univa/mcp_tools/     image, video, audio, editing, understanding, tracking tools
scripts/             direct runners, clients, preflight, tool contract export
apps/web/            Next.js editor and chat frontend
```

## Quickstart

The fastest path is **external agent skill collaboration**. It does not require the Web frontend or a running backend server. Use this when Codex, Claude Code, or another terminal agent operates the repository.

### 1. Requirements

- Python 3.10+
- FFmpeg and ffprobe
- API access for the providers you plan to use, typically Wavespeed and/or Ark

Check:

```bash
python --version
ffmpeg -version
ffprobe -version
```

### 2. Create the Python Environment

Linux with a matching CUDA environment:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -U pip setuptools wheel
pip install -r requirements.txt
pip install mcp==1.27.2 httpx-sse==0.4.3
```

Linux CPU, mismatched CUDA, or Windows:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -U pip setuptools wheel
pip install -r requirements.runtime.txt
pip install mcp==1.27.2 httpx-sse==0.4.3
```

`requirements.runtime.txt` is the checked-in filtered dependency file generated from `requirements.txt` for CPU, incompatible CUDA, or Windows environments. It removes CUDA/PyTorch-pinned entries such as the CUDA PyTorch index, `cuda-*`, `nvidia-*`, `triton*`, `torch==*`, `torchvision==*`, and `torchaudio==*`.

This filtered install is enough for API-backed orchestration, the backend, MCP routing, FFmpeg merge/composition, and provider-based image/video/audio generation. It does not install PyTorch. Local checkpoint-based features such as local video understanding, tracking, or local video editing need a platform-compatible PyTorch install and matching model paths.

Windows PowerShell uses the same filtered install, with activation changed to:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
py -m pip install -U pip setuptools wheel
py -m pip install -r requirements.runtime.txt
py -m pip install mcp==1.27.2 httpx-sse==0.4.3
```

Conda is also supported. Use one environment style consistently:

```bash
conda create -n univa python=3.10
conda activate univa
python -m pip install -U pip setuptools wheel
python -m pip install -r requirements.runtime.txt
python -m pip install mcp==1.27.2 httpx-sse==0.4.3
```

If you must use native Windows Python without a virtual environment, run the same install against the exact interpreter that will run UniVA:

```powershell
py -m pip install -U pip setuptools wheel
py -m pip install -r requirements.runtime.txt
py -m pip install mcp==1.27.2 httpx-sse==0.4.3
```

This is not recommended for development because it modifies the user/global Python package set. If you use it, generate the MCP server config with the same `py -3.10` interpreter.

After changing `requirements.txt`, regenerate `requirements.runtime.txt` with the same filter and review the diff before committing it.

### 3. Create Local Directories

```bash
mkdir -p results cache temp/config/univa data
```

### 4. Configure `.env`

Edit the repository-root `.env` file. 

Fill in the API keys and provider choices you plan to use, especially `PLAN_MODEL_API_KEY`, `ACT_MODEL_API_KEY`, `LLM_OPENAI_API_KEY`, `WAVESPEED_API_KEY`, `ARK_API_KEY`

Non-sensitive MCP defaults such as model names, base URLs, merge settings, and default video audio behavior live in `univa/config/mcp_tools_config/config.yaml`. Put secrets and machine-specific overrides in `.env`; only add model/audio override variables there when you intentionally want to override the YAML defaults. Do not commit real secrets.

### 5. Generate MCP Server Config

All MCP servers must point to the same Python interpreter that will run UniVA. Activate your `venv` or conda environment first; if you use native Windows Python without a virtual environment, use the same `py ` interpreter here.

```bash
python scripts/configure_mcp_servers.py
```

Windows PowerShell without a virtual environment:

```powershell
py scripts/configure_mcp_servers.py
```

If you need to point MCP servers to a specific interpreter explicitly, pass `--python /path/to/python`.

### 6. Preflight

```bash
python scripts/preflight_media_runtime.py
```

`READY_UNTIL_PROVIDER` means local imports, directories, FFmpeg, config, and MCP routing are ready. Real remote generation still depends on API keys, quota, region, upload URLs, and provider availability.

## Use UniVA With an External Coding Agent

For video generation driven by external agents like Codex, you can directly input the corresponding commands after enabling the external agent, and the agent will automatically read the relevant skills and carry out the task.


## Optional: Backend API

Use the backend when you need CLI interaction, FastAPI, sessions, auth, streaming, pause/resume, or the Web frontend.

```bash
python univa/univa_agent.py
python -m univa.univa_server
curl http://127.0.0.1:8000/health
```

If port `8000` is busy:

```bash
UNIVA_SERVER_PORT=18000 python -m univa.univa_server
```

API client:

```bash
python scripts/univa_agent_client.py chat --prompt "Show my preferences" --show-session
python scripts/univa_agent_client.py resume --session-id <session_id> --user-input "Confirm execution"
```

## Optional: Web Editor



The Web editor provides uploads, a media library, chat, project context, approval cards, and a timeline-oriented editing surface.

```bash
  npm install
  python -m uvicorn univa.univa_server:app --host 0.0.0.0
  --port 8000
```

In another terminal:

```bash
cd apps/web
npm run dev
```

Open the browser
```
Editor page: http://localhost:3000/editor/<project_id>
AI chat page (standalone): http://localhost:3000/chat
```

## Media Review Gate

UniVA intentionally separates planning from execution:

1. Load skills and contracts.
2. Research or analyze references.
3. Create an executable plan or proposal.
4. Write validation/review artifacts.
5. Stop at `awaiting_human`.
6. Execute only the approved plan version.
7. Verify real output files and write `delivery_report.json`.

This applies to video, image, audio, speech, generated assets, style transfer, repainting, replacement, extension, composition, and compound media tasks.

## Tool Coverage

| Domain | Tools |
|---|---|
| Video generation | `plan_video_shots`, `text2video_gen`, `image2video_gen`, `frame2frame_video_gen`, `video_extension`, `storyvideo_gen`, `entity2video` |
| Image generation | `text2image_generate`, `image2image_generate`, `sequential_image_gen` |
| Video editing | `depth_modify`, `style_transfer`, `repainting`, `pose_reference` |
| Video understanding | `vision2text_gen` |
| Video tracking | `video_referring_segmentation` |
| Audio and speech | `audio_gen`, `speech_gen`, `plan_audio_for_video`, `generate_audio_assets_from_plan`, `mux_audio_timeline` |
| Composition | `merge2videos`, `remotion_compose_video` |


## Codebase Structure

```text
apps/
  web/                       Next.js editor, chat UI, project workspace, uploads, and API routes

packages/
  auth/                      Shared authentication helpers
  db/                        Shared database schema, migrations, and typed access helpers
  remotion-compose/          Remotion composition project used for final video packaging
  video-export/              Timeline-to-export utilities and video export pipeline code

univa/                       Python agent runtime, backend entry points, prompts, and orchestration
  auth/                      Backend authentication models, middleware, and admin commands
  config/                    Runtime configuration plus generated MCP server configuration
  mcp_tools/                 MCP tool implementations for image, video, audio, editing, and tracking
  prompts/                   Prompt templates for planning, generation, understanding, and tracking
  utils/                     Shared media processing, model, pipeline, upload, and formatting utilities

skills/                      Tool contracts, workflow rules, topics, and user preferences for agents
  agent-integrations/        References for running external agents
  core/                      Detailed constraint tools
  creative/                  Handles creative extensions and quality improvements
  meta/                      Assistance content needed throughout the whole process
  pipelines/                 Pipeline process specifications
  themes/                    Guidance for generating themes
  user/                      User-level preferences

pipeline_defs/               YAML pipeline manifests that bind skills into executable stages
schemas/                     JSON schemas for artifacts, checkpoints, reviews, and delivery reports
scripts/                     Direct runners, API client, preflight checks, config generation, and utilities
tests/                       Python test suite for runtime, skills, tools, and orchestration behavior
docs/                        Project documentation assets, README media, and paper/demo material

data/                        Local project uploads and workspace media; preserve user-provided content
results/                     Generated plans, reviews, media outputs, and delivery artifacts
logs/                        Runtime and MCP tool logs
temp/                        Local scratch/config state created during development or execution
```

