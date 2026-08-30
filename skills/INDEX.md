# UniVA Skill Index

> For the complete project overview, see the repository `README.md`. This index only records skills, pipelines, and MCP tool mappings that exist in this repository.

## Three-Layer Skill Architecture

```text
Layer 1: Atomic Capability Skills
  skills/core/*
  Define MCP tool inputs, outputs, pre-call checks, post-call validation, output policy, and failure shape.

Layer 2: Governance and Creative Constraint Skills
  skills/creative/*
  Cover prompt construction, creative briefs, copy, styleframes, energy arcs, shot recipes, durations, materials, captions, audio, and creative quality gates.
  skills/themes/*
  Theme-specific generation quality enhancers. When a task matches product advertising, comics, Chinese ink/guochao, sci-fi anime, or other themes, these skills add themed prompt, visual, storyboard, content, scene, and audio guidance. They do not change safety review, approval, permissions, tool contracts, or explicit user instructions.
  skills/meta/*
  Provide planning/acting protocols, pipeline loading, review, checkpoints, quality gates, media review, clarification, output formatting, user help, preference management, skill creation, and frontend-editor behavior.

Layer 3: Task-Driven Collaboration Skills
  skills/pipelines/**/*
  pipeline_defs/*.yaml
  Route full user tasks, orchestrate stages, and coordinate cross-layer execution.

External Agent Integration:
  skills/agent-integrations/*
  AGENTS.md / CLAUDE.md / scripts/codex_video_runner.py / scripts/codex_video_task_runner.py / scripts/univa_agent_client.py
  Let Codex, Claude Code, and other terminal-first agents reuse UniVA skills, pipelines, backend behavior, user preferences, and MCP tools for media generation, understanding, editing, review, approval, and delivery verification.
```

## Capability Domains and MCP Tools

| Capability Domain | MCP Server | Atomic Tools / Workflows |
|---|---|---|
| `video_generation` | `video_gen` | `text2video_gen`, `image2video_gen`, `frame2frame_video_gen`, `video_extension`, `storyvideo_gen`, `entity2video`, `merge2videos`, `remotion_compose_video` |
| `image_generation` | `image_gen` | `text2image_generate`, `image2image_generate`, `sequential_image_gen` |
| `video_editing` | `video_editing` | `depth_modify`, `style_transfer`, `repainting`, `pose_reference` |
| `video_understanding` | `video_understanding` | `vision2text_gen` |
| `video_tracking` | `video_tracking` | `video_referring_segmentation` |
| `audio_generation` | `audio_gen` | `audio_gen`, `speech_gen` |

Default video delivery includes non-voice audio such as BGM, ambience, SFX, and transitions. Voiceover, dubbing, speech, or character dialogue is generated only when the user explicitly asks for voice content. When video audio is requested or enabled, use this priority order: preserve audio returned by the video generation API first, use the dedicated audio generation API second, and use local FFmpeg synthetic audio fallback only when the generated video has no audio stream and no dedicated audio API path succeeds. Remotion is an approved final packaging layer for captions, title cards, lower thirds, CTA, brand marks, progress bars, and data cards.

## MCP Tool Contract Rule

At execution time, the function name, required and optional parameters, defaults, return fields, output path policy, and failure shape come from the matching `skills/core/*.md` Tool Contract. Do not reread `univa/mcp_tools/*.py` for ordinary task execution. Read implementation source only when maintaining a contract, adding/changing a tool, debugging a mismatch, or when the required core skill lacks the contract.

Use `python scripts/export_mcp_tool_contracts.py` to export current MCP signatures while maintaining contracts.

| MCP Tool | Contract Skill |
|---|---|
| `plan_video_shots`, `text2video_gen`, `image2video_gen`, `frame2frame_video_gen`, `video_extension`, `storyvideo_gen`, `entity2video` | `skills/core/wavespeed-video-gen.md` |
| `merge2videos` | `skills/core/ffmpeg-merge.md`; optional Remotion fields: `skills/core/remotion-compose.md` |
| `text2image_generate`, `image2image_generate`, `sequential_image_gen` | `skills/core/wavespeed-image-gen.md` |
| `plan_audio_for_video`, `audio_gen`, `speech_gen`, `generate_audio_assets_from_plan`, `mux_audio_timeline` | `skills/core/audio-gen.md` |
| `depth_modify`, `style_transfer`, `repainting`, `pose_reference` | `skills/core/video-editing.md` |
| `vision2text_gen` | `skills/core/video-understanding.md` |
| `video_referring_segmentation` | `skills/core/video-tracking.md` |

## Core Skills

| Skill | File | Covered Tools / Purpose |
|---|---|---|
| Wavespeed Video Gen | `core/wavespeed-video-gen.md` | Video planning and generation tools |
| Wavespeed Image Gen | `core/wavespeed-image-gen.md` | Image generation and image-to-image tools |
| Video Editing | `core/video-editing.md` | Depth, style transfer, repainting, and pose-reference editing |
| Ark Video Reference Upload | `core/ark-video-reference-upload.md` | Local video to HTTP(S) reference URL for Ark editing |
| Video Understanding | `core/video-understanding.md` | `vision2text_gen` analysis |
| Video Tracking | `core/video-tracking.md` | Referring segmentation |
| Audio Gen | `core/audio-gen.md` | Audio, speech, audio planning, asset generation, and muxing |
| FFmpeg Merge | `core/ffmpeg-merge.md` | Merge, per-edge transitions, crossfade, and final audio handling |
| Remotion Compose | `core/remotion-compose.md` | Approved final packaging layer |
| Prompt Validator | `core/prompt-validator.md` | Required validation before generation calls |

## Creative, Meta, Theme, and Pipeline Skills

Creative skills define briefs, copy, styleframes, energy arcs, shot planning, material mapping, durations, timeline/audio/caption plans, Remotion packaging, story video structure, editing strategy, analysis, breakdown, generation, and quality checks.

Meta skills define chat/work routing, output judging, plan/act behavior, pipeline loading, review, quality gates, checkpoints, clarification, help/pause flows, media review, user preference creation/management, output formatting, frontend editor behavior, and skill creation.

Theme skills are generation quality enhancers loaded by `SkillLoader.find_theme_skills_for_task()` from front matter triggers. They may enrich prompts and planning, but they must never change intent type, pipeline choice, media review, human checkpoints, permissions, tool contracts, explicit instructions, or approved handoff content.

Pipeline director skills live under `skills/pipelines/**` and correspond to YAML pipeline stages in `pipeline_defs/*.yaml`.
