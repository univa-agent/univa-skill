# Claude Code Guidance for UniVA

Use UniVA's repo-local agent-integration skills when working in this repository.

Primary entry point: `skills/agent-integrations/claude-code-univa-video-ops/SKILL.md`.

Operational rule: use direct repo runners or existing `univa.mcp_tools`
functions for ordinary terminal-first generation, understanding, ASR, and
editing tasks. Use the backend and `scripts/univa_agent_client.py` when the
task needs durable sessions, streaming, auth, pause/resume, automatic Artifact
records, compound routing, or preference operations. Read
`skills/core/localization.md` for ASR/localization,
`skills/core/media-index.md` for time-coded search, and
`skills/meta/artifact-provenance.md` for version/receipt/cost handling. Modify
code or skills only when the user asks to change project behavior.
