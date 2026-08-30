# Story Video Asset Director - Pipeline Director Skill

## Stage Role

Use this director to generate or map required story-video assets after approval.

## Responsibilities

Use approved prompts and asset manifest, generate characters/keyframes/clips, verify paths, and record failures.

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
