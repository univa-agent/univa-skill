# Claude Code UniVA Media Ops

Use this skill when Claude Code operates UniVA media workflows.

Read `skills/INDEX.md`, `skills/meta/media-review-gate.md`,
`skills/meta/artifact-provenance.md`, the task-specific core contract, and
relevant creative, pipeline, theme, and user preference skills. Use existing
UniVA backend and MCP tools. For every media generation or mutation, create a
plan/review artifact, stop at `awaiting_human`, execute only the approved plan,
verify output files, and write delivery reporting.

For ASR/transcription, read `skills/core/localization.md` and directly call
`univa.mcp_tools.localization.transcribe_media`; this read-only operation does
not require Web or mutation approval. For full localization, use the
localization Pipeline and stop before voiceover/render. For durable video
search, read `skills/core/media-index.md`, index first, enrich only from trusted
timed analysis, and then search. Use backend behavior only when the task
specifically needs sessions, streaming, auth, pause/resume, automatic Artifact
records, or Web/API integration.
