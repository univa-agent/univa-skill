# UniVA External Agent Bridge

Use this skill when a terminal-first AI coding agent operates UniVA for media generation, editing, understanding, or compound media tasks.

## Required Context

Read `AGENTS.md`, `skills/INDEX.md`, `skills/meta/media-review-gate.md`,
`skills/meta/artifact-provenance.md`, the relevant generate/edit/understand meta
skill, the task-specific core Tool Contract, and relevant
creative/pipeline/theme/user preference skills before selecting a tool.

## Task Selection

- ASR/transcription: read `core/localization`; call `transcribe_media` directly
  for read-only output. Do not require Web or start the backend.
- Full localization: use `pipeline_defs/localization.yaml`; approval is required
  before voiceover, muxing, or subtitle rendering.
- Long-video index/search: read `core/media-index`; index, enrich from trusted
  timed data, then search exact timecodes.
- Durable pause/resume/auth: use the backend and `scripts/univa_agent_client.py`;
  retain the current session/token and never replay a consumed token.
- Version/cost/provenance audit: follow `meta/artifact-provenance`; do not edit
  the SQLite stores directly.

## Operating Rules

- Use repository skills, pipelines, and `univa/mcp_tools` functions. Do not create a second media runtime or provider client.
- For media generation or mutation, write a concrete plan/review artifact and stop at `awaiting_human` before any tool call.
- Execute only after explicit approval of the displayed plan version.
- Pass the approved exact prompt, text, timing, references, and parameters to the UniVA tool.
- For generated video audio, preserve native audio returned by the video API first, use the registered dedicated audio API second, and use local FFmpeg synthetic audio fallback only when the generated video has no audio stream and the dedicated audio API path is unavailable or fails.
- Preserve user data and generated media under `data/`, `results/`, or `univa/results/`.
- Verify real output files and write a delivery report.

Use the backend only when testing Web/API/session/auth/pause-resume behavior or when the user explicitly asks for backend execution.
