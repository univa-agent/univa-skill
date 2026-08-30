# Media Review Gate — Meta Skill

## When to Use

**MANDATORY** for every request that creates or mutates media in UniVA, including video, image, audio, speech, generated assets, style transfer, repainting, replacement, extension, composition, and compound tasks containing any of those operations.

Read-only understanding, inspection, metadata queries, and planning without tool execution do not require approval. The moment a task will call a media generation/editing tool or overwrite an artifact, this gate applies.

## Binding Rule

No media-producing or media-mutating MCP tool may run before the user or controlling agent has reviewed and explicitly approved the concrete execution plan for that gate. A direct tool call is an execution stage, not a substitute for the pipeline.

The gate covers at least:

- Video: text2video_gen, image2video_gen, frame2frame_video_gen, video_extension, storyvideo_gen, entity2video, and merge2videos when it creates a new deliverable.
- Image: text2image_generate, image2image_generate, and sequential_image_gen.
- Audio/speech: audio_gen, speech_gen, generate_audio_assets_from_plan, and mux_audio_timeline when it creates or mutates a deliverable.
- Editing: depth_modify, style_transfer, repainting, pose_reference, plus future media editing tools registered in skills/INDEX.md.

## Required Context Load

Before planning:

1. Read AGENTS.md and skills/INDEX.md.
2. Read skills/meta/generate-pipeline.md or skills/meta/edit-pipeline.md.
3. Read the task-specific core skill. Its **Tool Contract** section is the execution-time source of truth for MCP function name, complete parameters, default behavior, return fields, output policy, and failure shape.
4. Read the actual implementation under `univa/mcp_tools/` only when maintaining tool contracts, adding/changing a tool, debugging an observed contract mismatch, or when the task-specific core skill lacks the required contract. Normal planning/execution should not repeatedly inspect source code just to learn signatures.
5. Read relevant creative, pipeline, prompt, reviewer, quality-gate, checkpoint, and user-preference skills.
6. Record loaded paths and, when a runner supports it, hashes/full text in skill_context.json and skill_context_full.json.

Do not infer a tool contract from memory when the repository skill contract is available. Do not create a second provider client or media runtime. If a skill contract and implementation disagree, stop or mark the plan blocked, then update the contract from source before executing.

## Pipeline

Use this stage sequence for every in-scope task:

    discover → research/analyze → plan/proposal → validate/review → explicit approval
             → execute approved request → validate output → deliver

### 1. Discover

- Classify generate, edit, compound, or read-only understand.
- Identify media type, source assets, exact UniVA tool, configuration, costs, and unsupported requirements.
- If no registered tool can perform the requested mutation, mark the proposal blocked; do not invent a fallback runtime.

### 2. Research or Analyze

- For factual, current, branded, product, place, event, cultural, technical, or reference-sensitive generation, gather relevant source notes before planning.
- For editing, inspect the source with repository understanding tools when useful and state what must change and what must be preserved.
- Record missing research or unavailable analysis as a review issue. Do not hide degraded context.

### 3. Create the Executable Plan

Use the domain artifact while preserving an equivalent contract:

| Task | Plan artifact | Required execution contract |
|---|---|---|
| Video generation | shot_plan.json | approved shots[*].expanded_generation_prompt, duration, aspect ratio, references, transitions/audio policy |
| Image generation | media_plan.json | approved tool, exact expanded prompt per image, references, count, aspect/composition, style and negative constraints |
| Audio/speech generation | media_plan.json | approved tool, exact audio prompt or spoken text, duration, role, voice/emotion/speed, timing and exclusions |
| Media editing | edit_proposal.json | source path/hash when available, source analysis, exact tool, complete parameters, change list, preservation list, expected result |
| Compound task | parent plan plus per-subtask contracts | dependency order and a separate approval state for each expensive or mutating gate |

The plan must contain approval_required: true, the exact provider/tool request preview, quality checks, output policy, and a clear list of assumptions. Prompt refinement happens before review. Execution must not silently rewrite or shorten approved prompts, text, timing, references, or parameters.

Every plan/proposal must copy the exact MCP request shape from the task-specific core skill contract, including optional fields that materially change behavior such as `auto_audio`, `include_voiceover`, `transition_duration_seconds`, `aspect_ratio`, `label`, `image_path`, `images_num`, `type`, `return_mask`, `keep_original_audio`, and `mux_output_path`.

### 4. Validate and Present Review

Write a validation artifact and review artifact before tool execution:

- Video generation keeps storyboard_validation.json and storyboard_review.json.
- Video editing keeps edit_proposal_review.json.
- Other generation/editing tasks use media_plan_validation.json and media_plan_review.json, or an equivalent pipeline checkpoint with the same fields.

The review must show:

- user request, research/source analysis, assumptions, selected tool, and why;
- complete exact request(s) that will reach the MCP tool;
- references and source paths, duration/count/dimensions/timing, preservation and negative constraints;
- validation issues, estimated cost/side effects when known, and output location policy;
- explicit choices to approve, revise, or cancel.

Set the checkpoint to awaiting_human and stop. Do not call any covered tool in the review phase.

### 5. Approval Semantics

- Approval is per gate and applies only to the displayed plan version.
- A generic earlier “go ahead”, the original creation request, or approval of research is not approval of an unseen plan.
- Revisions invalidate prior approval and require a refreshed validation/review artifact.
- Auto-approve flags are allowed only for tests, benchmarks, or explicit full pre-approval recorded in the decision log.

### 6. Execute the Approved Contract

- Load the approved artifact and pass its exact request fields to the registered UniVA MCP function.
- Do not replace an approved expanded prompt with keywords, a title, a summary, or the original user request.
- Do not alter source files in place unless the approved proposal explicitly requires it. Default to a new output artifact.
- Preserve intermediate artifacts and media under data/, results/, or univa/results/.

### 7. Validate and Deliver

- Verify success, absolute output path, file existence, non-zero size, and format-specific quality checks.
- Compare the output with the approved intent; record deviations and failures honestly.
- Write delivery_report.json linking the approved plan, review/decision, tool result, and final artifacts.
- A plan without generated media is reported as planned, not generated. A failed or missing path is never reported as delivered.

## Self-Evaluate

- [ ] Repo skills and the task-specific core Tool Contract were read before planning; MCP implementation source was read only if maintaining/debugging contracts.
- [ ] The correct generate/edit pipeline and user preferences were applied.
- [ ] Research or source analysis is recorded, including limitations.
- [ ] Review exposes exact tool requests and validation issues.
- [ ] Covered tools did not run before explicit approval.
- [ ] Execution used the approved contract without silent rewriting.
- [ ] Output files and delivery report were verified.

## Common Pitfalls

- Treating a one-image or one-audio request as too simple for review.
- Generating a style frame during planning without approval; a prompt-only preview is safe, a generated preview is already a media call.
- Using image2image_generate as an unreviewed shortcut for image editing.
- Treating source analysis as permission to mutate the source.
- Claiming audio was added when only an audio plan exists.
- Falling back to an ad-hoc API when UniVA lacks the requested editor.
