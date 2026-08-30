# FFmpeg Merge - Core Skill

## When to Use

Use when merging multiple video clips, applying per-edge transitions, performing real crossfades, handling final audio, or handing off to Remotion packaging.

## Execution-Time Contract Source

For normal task execution, this file is the MCP contract source for function name, parameters, defaults, return fields, output path policy, and failure shape. Read `univa/mcp_tools` implementation only when maintaining this contract, adding/changing a tool, debugging an observed mismatch, or when this skill lacks the required contract.

## Covered Tools

- `merge2videos`

## Tool Contract Rules

- Build the MCP request from the approved plan or proposal artifact.
- Include optional fields that materially affect behavior, such as `duration_seconds`, `aspect_ratio`, `auto_audio`, `include_voiceover`, `audio_prompt`, `transition_plan`, `transition_duration_seconds`, `image_path`, `images_num`, `type`, `return_mask`, `keep_original_audio`, `mux_output_path`, and output directory fields when relevant.
- Return handling must check `success`, `output_path` or content fields, `message`, and `error` fields. A missing or empty output path is not a delivered artifact.
- Output files must be placed under `data/`, `results/`, or `univa/results/` unless the approved request specifies another safe project-local location.

## Required Behavior

Write temporary concat/filter files under the output directory and clean them after completion. Validate every input path, transition plan, duration policy, final path, and optional audio/remotion behavior. Do not pollute the repository root with temporary files.

Final audio handling must preserve source/native video API audio when present. If the merged output has no audio stream and `auto_audio` is enabled, use the dedicated audio API first. If that path is unavailable or fails, use the local FFmpeg synthetic audio fallback and report that the fallback is non-semantic ambience/BGM rather than generated voiceover or precise scene SFX.

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
