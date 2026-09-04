# Video Understand Analyze Director - Pipeline Director Skill

## Stage Role

Use this director to perform source video analysis. When the pipeline stage is
`index`, create or reuse the local time-coded index before deep analysis.

## Responsibilities

Capture content, style, rhythm, camera, audio, structure, reusable prompts, and limitations.

## Required Inputs

- User request and current pipeline state.
- Relevant core, creative, meta, theme, and user preference skills.
- Source assets, references, constraints, and prior artifacts when applicable.
- For the `index` stage, a readable local video path and the requested segment
  duration.
- Pipeline YAML success criteria and checkpoint requirements.

## Required Outputs

- Stage artifact or checkpoint named by the active pipeline.
- English assumptions, decisions, validation issues, and next-step status.
- Exact MCP request preview for any future media-producing or media-mutating step.
- `awaiting_human` checkpoint whenever approval or user choice is required.
- Index results must report exact time ranges and must not claim captions,
  transcripts, OCR, speakers, or embeddings unless an enrichment backend has
  actually populated those fields.
- When analysis or imported captions provide trusted time-coded text, call
  `update_video_index_segments` so later search uses the public index contract.

## Invariants

- Do not call generation/editing/mux/merge tools before the media review gate is approved for the displayed plan version.
- Execute only approved prompts, parameters, timing, references, and source paths.
- Preserve project artifacts and verify real files before delivery.
- Do not weaken safety, factual research, user preference precedence, or tool contracts.
