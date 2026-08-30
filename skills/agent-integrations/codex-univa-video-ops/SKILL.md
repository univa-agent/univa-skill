# Codex UniVA Media Ops

Use this skill when Codex operates UniVA for video, image, audio, speech, understanding, editing, or compound media tasks.

## Video Generation

Prefer `scripts/codex_video_runner.py` for Codex-driven video generation. The runner loads relevant skills, records skill context, creates research and storyboard artifacts, and calls existing `univa/mcp_tools` functions in process. Run it first in review mode so it writes `research_brief.json`, `shot_plan.json`, `storyboard_validation.json`, and `storyboard_review.json`, then stop for approval. Generate only by rerunning with `--approved-plan <run_dir>/shot_plan.json`.

For approved generation with audio enabled, follow UniVA's audio priority: keep native audio returned by the video API first, fall back to the registered dedicated audio API second, and use local FFmpeg synthetic audio only when the generated video has no audio stream and the dedicated audio path is unavailable or fails. Single-shot runs may pass the approved `auto_audio` options directly to the video generation tool. Multi-shot runs keep intermediate clip full mixes disabled and apply cohesive audio at merge time.

## Video Understanding and Editing

Prefer `scripts/codex_video_task_runner.py --task understand|edit`. Understanding writes an analysis plan, calls `vision2text_gen`, and produces reports. Editing writes `edit_proposal.json` and `edit_proposal_review.json`, then stops for approval. Execute edits only with an approved plan.

## Other Media

For image, audio, speech, and non-video mutation, apply the same media review gate with `media_plan.json`, `media_plan_validation.json`, `media_plan_review.json`, or equivalent checkpoint artifacts before calling MCP tools.

## Rules

Read `skills/INDEX.md`, `skills/meta/media-review-gate.md`, the matching core contract, and task-relevant creative/theme/pipeline/user skills. Do not bypass approval, do not shorten approved prompts, and do not invent alternate runtimes.
