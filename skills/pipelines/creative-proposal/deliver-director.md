# Creative Proposal Deliver Director - Pipeline Director Skill

## Stage Role

Use this director to validate and deliver final creative proposal outputs.

## Responsibilities

Verify files, summarize outputs, list deviations/failures, and write delivery reporting.

## Required Inputs

- User request and current pipeline state.
- Relevant core, creative, meta, theme, and user preference skills.
- Source assets, references, constraints, and prior artifacts when applicable.
- Pipeline YAML success criteria and checkpoint requirements.

## Required Outputs

- Stage artifact or checkpoint named by the active pipeline.
- English assumptions, decisions, validation issues, and next-step status.
- Exact MCP request preview for any future media-producing or media-mutating step.
- `awaiting_human` checkpoint whenever approval or user choice is required.

## Invariants

- Do not call generation/editing/mux/merge tools before the media review gate is approved for the displayed plan version.
- Execute only approved prompts, parameters, timing, references, and source paths.
- Preserve project artifacts and verify real files before delivery.
- Do not weaken safety, factual research, user preference precedence, or tool contracts.
