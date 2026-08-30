# Claude Code UniVA Media Ops

Use this skill when Claude Code operates UniVA media workflows.

Read `skills/INDEX.md`, `skills/meta/media-review-gate.md`, the task-specific core contract, and relevant creative, pipeline, theme, and user preference skills. Use existing UniVA backend and MCP tools. For every media generation or mutation, create a plan/review artifact, stop at `awaiting_human`, execute only the approved plan, verify output files, and write delivery reporting. Use backend behavior only when the task specifically needs sessions, streaming, auth, pause/resume, or Web/API integration.
