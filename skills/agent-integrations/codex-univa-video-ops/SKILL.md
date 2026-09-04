# Codex UniVA Media Ops

Use this skill when Codex operates UniVA for video, image, audio, speech, understanding, editing, or compound media tasks.

## Video Generation

Prefer `scripts/codex_video_runner.py` for Codex-driven video generation. The runner loads relevant skills, records skill context, creates research and storyboard artifacts, and calls existing `univa/mcp_tools` functions in process. Run it first in review mode so it writes `research_brief.json`, `shot_plan.json`, `storyboard_validation.json`, and `storyboard_review.json`, then stop for approval. Generate only by rerunning with `--approved-plan <run_dir>/shot_plan.json`.

For approved generation with audio enabled, follow UniVA's audio priority: keep native audio returned by the video API first, fall back to the registered dedicated audio API second, and use local FFmpeg synthetic audio only when the generated video has no audio stream and the dedicated audio path is unavailable or fails. Single-shot runs may pass the approved `auto_audio` options directly to the video generation tool. Multi-shot runs keep intermediate clip full mixes disabled and apply cohesive audio at merge time.

## Video Understanding and Editing

Prefer `scripts/codex_video_task_runner.py --task understand|edit`. Understanding writes an analysis plan, calls `vision2text_gen`, and produces reports. Editing writes `edit_proposal.json` and `edit_proposal_review.json`, then stops for approval. Execute edits only with an approved plan.

For durable long-video indexing and time-coded lookup, also read
`skills/core/media-index.md`. Use `index_video_media`, enrich only with trusted
timed analysis through `update_video_index_segments`, then search. Do not claim
visual or semantic retrieval from an empty text index.

## ASR and Localization

For prompts containing ASR, transcription, subtitle translation, bilingual
captions, dubbing, or localization, read `skills/core/localization.md` and
`skills/pipelines/localization/executive-producer.md`.

- ASR-only work is read-only: call
  `univa.mcp_tools.localization.transcribe_media` directly with the configured
  UniVA Python environment; no Web or backend server is required.
- Save real transcript/caption output under `results/localization/`. Do not
  fabricate text when `faster-whisper` or a model download is unavailable.
- Translation, sidecar captions, voiceover, and rendering are separate user
  intents. Do not add them to an ASR-only request.
- Voiceover, muxing, and rendered subtitles mutate/create media and require the
  universal plan/review gate before execution.

## Durable Runtime and Provenance

Read `skills/meta/artifact-provenance.md` for version, hash, receipt, cost, and
approval binding. Use the backend plus `scripts/univa_agent_client.py` only
when durable sessions, auth, pause/resume, or automatic Pipeline Artifact
records are required. Keep the current single-use continuation token and do
not retry resume blindly.

## Other Media

For image, audio, speech, and non-video mutation, apply the same media review gate with `media_plan.json`, `media_plan_validation.json`, `media_plan_review.json`, or equivalent checkpoint artifacts before calling MCP tools.

## Rules

Read `skills/INDEX.md`, `skills/meta/media-review-gate.md`, the matching core contract, and task-relevant creative/theme/pipeline/user skills. Do not bypass approval, do not shorten approved prompts, and do not invent alternate runtimes.
