# Wavespeed Video Gen - Core Skill

## When to Use

Use when calling Wavespeed/Ark-compatible APIs for video planning and generation.

## Execution-Time Contract Source

For normal task execution, this file is the MCP contract source for function name, parameters, defaults, return fields, output path policy, and failure shape. Read `univa/mcp_tools` implementation only when maintaining this contract, adding/changing a tool, debugging an observed mismatch, or when this skill lacks the required contract.

## Covered Tools

- `plan_video_shots`
- `text2video_gen`
- `image2video_gen`
- `frame2frame_video_gen`
- `video_extension`
- `storyvideo_gen`
- `entity2video`
- `merge2videos`

## Tool Contract Rules

- Build the MCP request from the approved plan or proposal artifact.
- Include optional fields that materially affect behavior, such as `duration_seconds`, `aspect_ratio`, `auto_audio`, `include_voiceover`, `audio_prompt`, `transition_plan`, `transition_duration_seconds`, `image_path`, `images_num`, `type`, `return_mask`, `keep_original_audio`, `mux_output_path`, and output directory fields when relevant.
- Return handling must check `success`, `output_path` or content fields, `message`, and `error` fields. A missing or empty output path is not a delivered artifact.
- Output files must be placed under `data/`, `results/`, or `univa/results/` unless the approved request specifies another safe project-local location.

## Required Behavior

Video generation must plan shots before generation when the request has multiple beats, transformations, scene changes, continuity needs, or user-facing delivery. Each generated shot prompt must be the approved `expanded_generation_prompt`; do not replace it with keywords, `visual_prompt`, a title, or the original request. Generated shots must respect provider minimum duration; current local Ark Seedance rejects 3-second requests, so planned model calls must be at least 4 seconds or merged/rebalanced first.

Video/audio generation must follow this priority order whenever `auto_audio` is enabled and the user did not request silence:

1. Preserve the audio stream returned by the video generation API. If the generated file already has an audio stream, do not replace it with a separate BGM/SFX mix.
2. If the generated video has no audio stream, use the registered dedicated audio generation API (`plan_audio_for_video` plus `generate_audio_assets_from_plan`) to create and mux BGM/SFX/ambience, and voiceover only when explicitly approved.
3. If no dedicated audio API is configured or the dedicated audio API path fails, use the local FFmpeg fallback to synthesize a simple ambience/BGM bed and mux it into the video. Record the fallback and any limitations in the delivery report.

For multi-shot workflows, keep intermediate clips from receiving independent full mixes; apply the cohesive audio policy at `merge2videos`. For single-shot workflows, pass the approved `auto_audio` and audio options directly to `text2video_gen` or `image2video_gen`.

## Process

1. Load the media review gate and the task-specific pipeline/creative/user preference skills.
2. Validate source assets, required keys, configured provider/model, local dependencies, and output directories before tool execution.
3. Create or consume the approved plan/proposal artifact. The request sent to the MCP tool must match the approved contract exactly.
4. Call the existing UniVA MCP tool; do not create a parallel provider runtime.
5. Verify real output files, non-zero size, readable format, and task-specific quality checks.
6. Write or update delivery reporting with the approved plan path, review/decision path, tool result, final artifacts, deviations, and failures.

## Common Pitfalls

- Calling a media-producing or media-mutating tool before the review artifact is approved.
- Sending the user's short prompt when an approved expanded prompt exists.
- Dropping optional fields that change audio, duration, transition, source preservation, or output behavior.
- Reporting a path as delivered before checking that the file exists and is usable.
- Inventing an alternate runtime when UniVA already has a registered MCP tool.
