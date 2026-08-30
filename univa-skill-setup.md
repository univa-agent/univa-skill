
# UniVA New Environment Setup Guide (Windows / Linux)

This setup guide keeps only three runnable targets and makes **external agent skill collaboration** the default target.

If the user does not explicitly ask for the Web frontend or direct `agent.py` / backend API mode, configure only **Part 1: External Agent Skill Collaboration**. This is the minimum useful setup: Codex, Claude Code, or another terminal agent reads UniVA skills, follows the media review gate, calls existing MCP tools/provider APIs, handles generation/editing/understanding/preferences, and verifies delivery artifacts.

Run commands from the repository root unless stated otherwise. Replace example paths with your real repository path:

```bash
cd /path/to/univa
```

## 0. Setup Targets

| Target | Default | Use Case | Required Configuration |
|---|---:|---|---|
| 1. External agent skill collaboration | Yes | Codex / Claude Code / terminal agents operate UniVA through repo skills, direct runners, MCP tools, and approval gates | Python, FFmpeg, `.env`, `mcp_configs.json`, provider keys, optional local model paths |
| 2. `agent.py` / backend API | No | Interactive CLI, FastAPI, `scripts/univa_agent_client.py`, sessions, pause/resume, Web backend | Target 1 plus `univa/univa_agent.py` or `python -m univa.univa_server` |
| 3. Web frontend | No | `apps/web` editor and browser chat UI | Target 2 plus Bun/Node and `apps/web/.env.local` |

Do not add unrelated setup targets to this guide. CUDA, PyTorch wheels, API keys, upload services, `cloudflared`, Chrome/Chromium, and local checkpoint paths depend on each user's machine and must remain configuration items rather than source-code edits.

### Behavior Already Fixed in Code

New users should not modify code for these items:

- `.env` boolean, integer, and float values are read as real types by MCP config.
- Image tools support `seedream`; image model type and video model type are separated.
- Video merge temporary files are written under the output directory and cleaned up.
- `UNIVA_CACHE_DIR` controls Ark task state, defaulting to `results/cache/univa`.
- `UNIVA_CONFIG_DIR` controls local `config.toml` location and can point to `temp/config/univa`.
- `UNIVA_SERVER_HOST` / `UNIVA_SERVER_PORT` control backend bind address and port, defaulting to `0.0.0.0:8000`.
- `scripts/preflight_media_runtime.py` validates local runtime boundaries without calling Ark/Wavespeed or spending provider quota.

## 1. Default: External Agent Skill Collaboration

Goal: external agents operate UniVA according to `AGENTS.md`, `skills/INDEX.md`, `skills/meta/media-review-gate.md`, and `skills/agent-integrations/*`. The default flow is: read skills -> plan/review -> wait for explicit approval -> call existing MCP tools or direct runners -> verify real outputs.

### 1.1 Prerequisites

Required:

- Python 3.10+.
- FFmpeg and ffprobe.
- Access to the LLM / Ark / Wavespeed API that you plan to use.

Optional by feature:

- GPU / CUDA / PyTorch: only for local understanding, tracking, or local editing models.
- `cloudflared`: only when Ark video editing needs a local video exposed as a public HTTPS reference video.
- Local checkpoints: only when enabling local video understanding, tracking, or local VACE editing.

Check tools:

```bash
python --version
ffmpeg -version
ffprobe -version
```

Windows PowerShell:

```powershell
python --version
ffmpeg -version
ffprobe -version
```

### 1.2 Create Local Directories

```bash
mkdir -p results cache temp/config/univa
mkdir -p data
```

PowerShell:

```powershell
New-Item -ItemType Directory -Force results, cache, temp/config/univa, data
```

### 1.3 Install Python Environment

Use one Python environment per setup. Avoid mixing interpreters.

Linux venv with matching CUDA 12.8:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -U pip setuptools wheel
pip install -r requirements.txt
pip install mcp==1.27.2 httpx-sse==0.4.3
```

Linux CPU or mismatched CUDA:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -U pip setuptools wheel
python - <<'PY'
from pathlib import Path
skip = ('nvidia-', 'triton', 'torch==', 'torchvision==', 'torchaudio==')
lines = []
for line in Path('requirements.txt').read_text().splitlines():
    stripped = line.strip()
    if not stripped or stripped.startswith('#'):
        continue
    if stripped.startswith(skip):
        continue
    lines.append(line)
Path('requirements.runtime.txt').write_text('\n'.join(lines) + '\n')
PY
pip install -r requirements.runtime.txt
pip install mcp==1.27.2 httpx-sse==0.4.3
```

Windows venv:

```powershell
py -3.10 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -U pip setuptools wheel
python - <<'PY'
from pathlib import Path
skip = ('nvidia-', 'triton', 'torch==', 'torchvision==', 'torchaudio==')
lines = []
for line in Path('requirements.txt').read_text().splitlines():
    stripped = line.strip()
    if not stripped or stripped.startswith('#'):
        continue
    if stripped.startswith(skip):
        continue
    lines.append(line)
Path('requirements.runtime.txt').write_text('\n'.join(lines) + '\n')
PY
pip install -r requirements.runtime.txt
pip install mcp==1.27.2 httpx-sse==0.4.3
```

For Conda or system Python, activate the target environment first. Later, `mcp_configs.json` must use that environment's `sys.executable`.

### 1.4 Create Minimal `.env`

Create `.env` in the repository root. Fill only keys you actually use. Do not commit secrets.

```dotenv
UNIVA_CACHE_DIR=results/cache/univa
UNIVA_CONFIG_DIR=temp/config/univa
UNIVA_SERVER_HOST=0.0.0.0
UNIVA_SERVER_PORT=8000
OPENAI_API_KEY=
OPENAI_BASE_URL=
OPENAI_MODEL=gpt-4.1
WAVESPEED_API_KEY=
WAVESPEED_VIDEO_MODEL=seedance
WAVESPEED_IMAGE_MODEL=seedream
WAVESPEED_TEXT_TO_VIDEO=seedance
WAVESPEED_IMAGE_TO_VIDEO=seedance
WAVESPEED_FRAME_TO_FRAME_VIDEO=wan_api
WAVESPEED_TEXT_TO_IMAGE=seedream
WAVESPEED_IMAGE_TO_IMAGE=seedream
ARK_API_KEY=
ARK_VIDEO_MODEL=
ARK_IMAGE_MODEL=
ARK_TASK_STATE_DIR=results/cache/univa
VIDEO_AUTO_AUDIO=true
VIDEO_AUTO_AUDIO_INCLUDE_BGM=true
VIDEO_AUTO_AUDIO_INCLUDE_AMBIENCE=true
VIDEO_AUTO_AUDIO_INCLUDE_SFX=true
VIDEO_AUTO_AUDIO_INCLUDE_TRANSITIONS=true
VIDEO_AUTO_AUDIO_INCLUDE_VOICEOVER=false
```

Optional feature values:

| Feature | Configuration |
|---|---|
| Wavespeed image/video/audio/speech | `WAVESPEED_API_KEY`, optional `WAVESPEED_*_MODEL` / `WAVESPEED_*_PROVIDER` |
| Ark image/video generation | `ARK_API_KEY`, `ARK_*_MODEL` |
| Ark local video editing | `VIDEO_UPLOAD_PROVIDER=cloudflare_tunnel` + `VIDEO_UPLOAD_CLOUDFLARED_BIN`, or `VIDEO_UPLOAD_URL` / `VIDEO_UPLOAD_API_KEY` |
| Local video understanding | `VIDEO_UNDERSTAND_MODEL_PATH`, `VIDEO_RETRIEVER_MODEL_PATH`, plus matching model dependencies/checkpoints |
| Local video tracking | `VIDEO_TRACK_SA2VA_PATH`, `VIDEO_TRACK_SAM_PATH` |
| Local VACE editing | `VIDEO_EDIT_MODEL_PATH`, `VACE_PYTHON`, `VACE_WORKDIR`, `VACE_TEMP_DIR`, `VACE_RESULTS_DIR` |

Do not commit private paths, API keys, or checkpoint paths into `univa/config/mcp_tools_config/config.yaml`. Prefer `.env` overrides.

### 1.5 Generate `univa/config/mcp_configs.json`

All MCP servers must point to the same Python interpreter that has UniVA dependencies installed.

```bash
UNIVA_MCP_PYTHON="$(python -c 'import sys; print(sys.executable)')"
python - <<'PY'
import json, os
from pathlib import Path
py = os.environ['UNIVA_MCP_PYTHON']
root = Path.cwd()
servers = {
    'video_gen': 'univa.mcp_tools.video_gen',
    'image_gen': 'univa.mcp_tools.image_gen',
    'audio_gen': 'univa.mcp_tools.audio_gen',
    'video_editing': 'univa.mcp_tools.video_editing',
    'video_understanding': 'univa.mcp_tools.video_understanding',
    'video_tracking': 'univa.mcp_tools.video_tracking',
}
config = {'mcpServers': {name: {'command': py, 'args': ['-m', module], 'env': {'PYTHONPATH': str(root)}} for name, module in servers.items()}}
out = root / 'univa/config/mcp_configs.json'
out.write_text(json.dumps(config, indent=2) + '\n')
print(out)
PY
```

Check for stale paths:

```bash
python - <<'PY'
import json
from pathlib import Path
cfg = json.loads(Path('univa/config/mcp_configs.json').read_text())
for name, server in cfg['mcpServers'].items():
    print(name, '->', server['command'])
PY
```

### 1.6 Preflight

```bash
python scripts/preflight_media_runtime.py
```

`READY_UNTIL_PROVIDER` means local imports, config, directories, FFmpeg, and MCP routing passed. Real remote generation still depends on API keys, account permissions, balance, region, upload URL, and provider availability. Reports are written under `results/preflight_media_runtime_<timestamp>/`.

### 1.7 Default Agent Collaboration Commands

Agents must read `AGENTS.md`, `skills/INDEX.md`, `skills/meta/media-review-gate.md`, and the matching integration skill before media work.

Video generation review phase:

```bash
python scripts/codex_video_runner.py \
  --prompt "Generate a 5-second product promo video" \
  --research-note "Reference notes provided by the user or search" \
  --output-dir results/codex_video_runs
```

Approved video generation:

```bash
python scripts/codex_video_runner.py \
  --prompt "Generate a 5-second product promo video" \
  --approved-plan <run_dir>/shot_plan.json \
  --output-dir results/codex_video_runs
```

Video understanding:

```bash
python scripts/codex_video_task_runner.py \
  --task understand \
  --media /path/to/video.mp4 \
  --prompt "Analyze content, style, shot rhythm, and reusable generation prompts"
```

Video editing proposal:

```bash
python scripts/codex_video_task_runner.py \
  --task edit \
  --media /path/to/video.mp4 \
  --prompt "Convert to watercolor animation style while preserving original motion and composition"
```

Approved video editing:

```bash
python scripts/codex_video_task_runner.py \
  --task edit \
  --media /path/to/video.mp4 \
  --prompt "Convert to watercolor animation style while preserving original motion and composition" \
  --approved-plan <run_dir>/edit_proposal.json
```

Image, audio, speech, and non-video edits use the same review gate with `media_plan.json`, `media_plan_validation.json`, `media_plan_review.json`, or edit proposal artifacts. After approval, call only the exact approved MCP request.

Preference examples:

```text
Save preference: for future product videos, use a calm tech feel, minimal transitions, and no voiceover
Show my preferences
Set #1 as the default preference
Update #1 preference: prefer 16:9 landscape output
```

Only `skills/user/preference_config.yaml.active_skill_name` is applied at runtime.

## 2. Optional: `agent.py` / Backend API

Use this only for CLI, FastAPI, API client, sessions, pause/resume, or Web backend behavior. The default direct-runner path does not require the backend.

```bash
python univa/univa_agent.py
python -m univa.univa_server
UNIVA_SERVER_PORT=18000 python -m univa.univa_server
curl http://127.0.0.1:8000/health
python scripts/univa_agent_client.py chat --prompt "Show my preferences" --show-session
UNIVA_ACCESS_CODE=<code> python scripts/univa_agent_client.py chat --prompt "Show my preferences"
python scripts/univa_agent_client.py resume --session-id <session_id> --user-input "Confirm execution"
```

If MCP connects but exposes no tools, check `mcp_configs.json.command`, repository `PYTHONPATH`, `python -c "import mcp, agno, univa"`, and the matching `univa.mcp_tools.<server>` import.

## 3. Optional: Web Frontend

Use this only for the browser editor, uploads, chat panel, or pipeline approval cards. First verify backend `/health`.

```bash
cd apps/web
bun install
cp .env.example .env.local
```

Minimum `apps/web/.env.local`:

```dotenv
AGENT_API_URL=http://127.0.0.1:8000
NEXT_PUBLIC_AGENT_API_URL=http://127.0.0.1:8000
```

Start backend and frontend:

```bash
python -m univa.univa_server
cd apps/web
bun dev
```

Open `http://127.0.0.1:3000`. Frontend chat proxies `/api/chat/stream` to backend `/chat/stream` with `client=editor`. Uploads and project files are stored under `data/<project_name>/`.

## 4. Completion Criteria

- `python scripts/preflight_media_runtime.py` reports `merge` as `LOCAL_PASS`.
- `image`, `video`, `audio`, and `video_editing` are at least `READY_UNTIL_PROVIDER`, or failures identify missing dependency, FFmpeg, config, or key.
- All `mcp_configs.json` servers point to the same Python.
- `.env` has no stale `/share` or `/path/to` placeholders unless that feature is disabled and empty.
- Generate/edit tasks write review artifacts and stop at `awaiting_human` before tool calls.
- Preference requests can read/write `skills/user/preference_config.yaml` and `skills/user/preference_XX.md`.
- Real media outputs have verifiable file paths under `results/`, `data/`, or `univa/results/`.

## 5. Troubleshooting

| Problem | Cause | Fix |
|---|---|---|
| Windows fails installing `nvidia-cufile-cu12` | Linux CUDA requirement | Use filtered Windows install. |
| `pip check` reports `mcp` / `httpx-sse` conflicts | Dependencies were overwritten | Reinstall `mcp==1.27.2 httpx-sse==0.4.3`. |
| MCP exposes no tools | Wrong Python in `mcp_configs.json.command` | Regenerate MCP config from current `sys.executable`. |
| Image model errors | Image config uses a video model type | Set image model type to `seedream`. |
| Automatic audio is not expected | Audio flags are implicit | Set `VIDEO_AUTO_AUDIO` and `VIDEO_AUTO_AUDIO_INCLUDE_*`. |
| Ark cannot use local video | Ark requires public HTTP(S) reference video | Configure `cloudflared` or an upload service. |
| Understanding/tracking fails | Local checkpoints or dependencies are missing | Configure model paths and matching CUDA/PyTorch. |
| `/health` times out | Backend down or port conflict | Set `UNIVA_SERVER_PORT=18000` and update frontend URL. |
| Frontend chat fails | Wrong `AGENT_API_URL` or backend down | Check `/health`, then update `.env.local`. |

## 6. Do Not Do These

- Do not bypass `skills/meta/media-review-gate.md` and call generation/editing tools directly.
- Do not write a parallel Ark/Wavespeed API runtime; use `univa/mcp_tools` and direct runners.
- Do not commit API keys, local absolute paths, or private checkpoint paths.
- Do not make local model capabilities mandatory defaults.
- Do not edit source code just to change ports, cache directories, config directories, or model types; use `.env`.
