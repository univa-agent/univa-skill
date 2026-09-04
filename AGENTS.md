# UniVA External Agent Guidance

When an AI coding agent operates this repository, use the repo-local skills, pipelines, and existing UniVA tool functions instead of inventing a new media runtime.

- Start with `skills/INDEX.md` to understand available UniVA skills, pipelines, MCP tools, and schemas.
- For every media generation or editing task, read and obey `skills/meta/media-review-gate.md`; this includes video, image, audio, speech, generated assets, and compound tasks.
- For Codex-driven video/image/audio generation, editing, or understanding tasks, read `skills/agent-integrations/codex-univa-video-ops/SKILL.md` (the legacy name now covers all UniVA media operations).
- For Claude Code-driven video/image/audio generation, editing, or understanding tasks, read `skills/agent-integrations/claude-code-univa-video-ops/SKILL.md` and the shared media review gate.
- For other terminal-first coding agents, read `skills/agent-integrations/univa-external-agent-bridge/SKILL.md`.
- For Codex-driven video generation tasks, prefer direct local execution with `scripts/codex_video_runner.py`; this reads repo skills, injects task-relevant skill context into planning, plans shots, calls the existing `univa/mcp_tools` generation functions in-process, merges clips, and writes artifacts under `results/` without starting `univa.univa_server`.
- For Codex-driven video understanding or editing tasks, prefer direct local execution with `scripts/codex_video_task_runner.py --task understand|edit`; this loads task-relevant core/pipeline/creative skills, records `skill_context.json` and `skill_context_full.json`, calls existing `vision2text_gen` or video editing MCP functions, and uses an edit proposal approval gate before mutation.
- For ASR, subtitle translation, bilingual captions, dubbing, or localization, read `skills/core/localization.md` and `skills/pipelines/localization/executive-producer.md`. ASR-only work may directly call `univa.mcp_tools.localization.transcribe_media` without Web/backend startup; voiceover, muxing, and subtitle rendering require the media plan/review gate.
- For durable video indexing or exact time-coded search, read `skills/core/media-index.md`; index first, enrich only with trusted timed captions/transcripts/analysis, then search. An empty text index is not semantic or visual retrieval.
- For canonical Artifact versions, hashes, costs, execution receipts, approval binding, and direct-versus-backend storage rules, read `skills/meta/artifact-provenance.md`.
- Use the existing backend (`python -m univa.univa_server`) and `scripts/univa_agent_client.py` only when testing Web/API behavior, auth/session streaming, pause/resume, or when the user explicitly asks to exercise the backend.
- Preserve user data and generated media under `data/`, `results/`, and `univa/results/`; do not delete or rewrite generated assets unless explicitly asked.

## Required Universal Media Plan/Review Gate

For all media creation and mutation, including single image/audio requests and image edits:

1. Load `skills/INDEX.md`, `skills/meta/media-review-gate.md`, the matching generate/edit meta skill, and task-specific core/creative/pipeline skills before selecting a tool. The task-specific core skill is the execution-time MCP contract source for function name, parameters, return fields, output policy, and failure shape. Read the actual `univa/mcp_tools` implementation only when updating tool contracts, debugging a contract mismatch, adding/changing a tool, or when the required contract is missing from the core skill.
2. Gather relevant research for reference-sensitive generation or analyze supplied source media for edits. Record limitations instead of silently bypassing them.
3. Produce a concrete plan/proposal, validation artifact, and review artifact showing the exact MCP request, assumptions, references, constraints, preservation rules, and quality checks.
4. Stop at `awaiting_human`. No generation or mutation tool may run until the user/controller explicitly approves that displayed plan version.
5. Execute only approved exact prompts, text, and parameters with existing UniVA functions; verify real output files and write `delivery_report.json`.
6. Auto-approve flags are for tests/benchmarks or explicit recorded full pre-approval only. A request to create or edit media is not approval of an unseen plan.

Video-specific `storyboard_*` and `edit_proposal_*` artifacts satisfy this gate. Image/audio generation and non-video edits use equivalent `media_plan.json`, `media_plan_validation.json`, and `media_plan_review.json` artifacts or a checkpoint with the same fields. If no repository tool supports the requested edit, block at proposal review; do not create an alternate runtime.

## Required Codex Video Generation Gate

For Codex-driven video generation, split execution into review and approved-generation phases:

1. Search or otherwise gather relevant current/domain reference notes from the user prompt. Pass them to `scripts/codex_video_runner.py` with `--research-note` or `--research-file`.
2. Let the runner create `research_brief.json`, `shot_plan.json`, `storyboard_validation.json`, and `storyboard_review.json`, then stop. Present the detailed storyboard to the user/controller for approval or revision.
3. Generate only after approval by rerunning with `--approved-plan <run_dir>/shot_plan.json`. The generation prompt for each shot must be the approved `shots[*].expanded_generation_prompt`, not keywords, `visual_prompt`, or the original user prompt.
4. Use `--auto-approve-storyboard` only for tests or explicit full pre-approval.


## Required Codex Video Understanding/Edit Path

For Codex-driven video understanding and editing, use `scripts/codex_video_task_runner.py` before falling back to the backend:

1. Understanding: run `--task understand --media <path> --prompt "<analysis request>"`. The runner loads video-understand/core/creative skills, writes `understanding_plan.json`, calls `vision2text_gen` for selected dimensions, and writes `structured_report.json` plus `delivery_report.json`.
2. Editing: run `--task edit --media <path> --prompt "<edit request>"`. The runner loads video-edit/core/creative skills, analyzes the source unless skipped, writes `edit_proposal.json` and `edit_proposal_review.json`, then stops for approval.
3. Execute edits only after approval with `--approved-plan <run_dir>/edit_proposal.json`, unless the user explicitly pre-approved `--auto-approve` for testing.
4. Use the backend only for Web/API/session/pause-resume/auth behavior or when the user explicitly asks to exercise the backend.
