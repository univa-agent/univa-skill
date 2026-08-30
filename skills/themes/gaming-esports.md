---
skill_id: theme_gaming_esports
name: Gaming and Esports
description: Generation quality enhancement skill for games, esports, battles, guides, tournaments, streams, or high-energy game montages; strengthens prompt detail, visual style, storyboard logic, content structure, scene design, and audio planning while preserving the main workflow.
trigger_keywords: [game, esports, battle, guide, tournament]
match_rule:
  type: keyword_semantic_hybrid
  threshold: 0.8
  keyword_combinations:
    - [esports, tournament]
    - [game, guide]
    - [battle, commentary]
  semantic_terms: [skill, combo, health bar, HUD, first person, high frame rate, replay, stream room]
optimization_guide:
  prompt_enhancement: Add game mode or objective, character class or loadout, HUD markers, skill combo, tactical movement, replay angle, and input feedback.
  visual_style: High-frame-rate feel, readable HUD, ability VFX, damage and score cues, arena lighting, motion blur, and energetic color contrast.
  storyboard_logic: pre-match objective -> engage or rotation -> combo highlight -> slow replay or killcam -> result or tactical tip.
  content_structure: Concise commentary tied to mechanics, timing, map control, and outcome; avoid inaccessible jargon when addressing a broad audience.
  scene_design: Game maps, esports arenas, streamer desks, training rooms, virtual battlegrounds, or scoreboard moments.
  audio_design: Game SFX, ability casts, keyboard and mouse clicks, caster calls, crowd swells, and impact transitions.
examples:
  - input: Create a high-energy esports battle montage
    output: Load the gaming esports theme and plan HUD, skill effects, fast cuts, replays, and energetic commentary.
---

# Gaming and Esports - Theme Skill

## When to Use

Load this skill when the user asks for games, esports, battles, guides, tournaments, streams, or high-energy game montages.

## Process

### Step 1: Preserve Workflow
Only enhance generation quality. Do not change media review, approval, permissions, tool contracts, output policy, or explicit user instructions. Real games, teams, or tournaments require research or recorded reference limits.

### Step 2: Apply Optimization Guide
Inject the front matter `optimization_guide` into the creative brief, copywriting, styleframe, storyboard, scene design, and audio plan. Convert abstract style words into visible subjects, materials, actions, camera language, scene anchors, and audio cues, so the selected theme is legible without relying on the title or caption.

### Step 3: Theme Consistency Check
Before generation, check that the theme is visible in the subject, action/storyboard, scene, and audio plan. Conflicts with user instructions or safety requirements must be resolved in the review artifact before execution.

## Generation Detail Expansion

In the generation plan, storyboard, or final `expanded_generation_prompt`, add details around the "Gaming and Esports" theme. These details only improve generation quality and do not change the main process, review, approval, permissions, tool contracts, or explicit user instructions.

### Prompt Expansion Checklist
- Subject: specify identity, appearance, materials, start/end action states, and relationship to props, environment, or other subjects; choose details that are native to the matched theme.
- Theme reinforcement: Add game mode or objective, character class or loadout, HUD markers, skill combo, tactical movement, replay angle, and input feedback.
- Cinematography: specify shot size, angle, camera movement, focus changes, foreground/midground/background layering, lighting, and transition context for each shot.
- Negative constraints: prevent drift such as unrelated styles, garbled text, watermarks, incorrect brand rendering, factual exaggeration, or scenes that conflict with the theme.

### Visual And Storyboard Expansion
- Visual details: High-frame-rate feel, readable HUD, ability VFX, damage and score cues, arena lighting, motion blur, and energetic color contrast.
- Storyboard rhythm: pre-match objective -> engage or rotation -> combo highlight -> slow replay or killcam -> result or tactical tip.
- Content structure: Concise commentary tied to mechanics, timing, map control, and outcome; avoid inaccessible jargon when addressing a broad audience.
- Scene design: Game maps, esports arenas, streamer desks, training rooms, virtual battlegrounds, or scoreboard moments.
- Audio planning: Game SFX, ability casts, keyboard and mouse clicks, caster calls, crowd swells, and impact transitions.

### Final Prompt Influence
- Each final prompt that matches this theme should include at least four explicit anchors: a theme-signature visual marker, an action/storyboard beat, a scene/material anchor, and a camera/lighting or audio cue.
- When multiple themes match, preserve the user's explicit theme first, then merge compatible elements; explain conflicting choices in `storyboard_review` or `media_plan_review`.
- Recommended `theme_consistency_score` is at least 0.8; if below threshold, revise the prompt, storyboard, scene, or audio plan before generation. Do not bypass `media-review-gate`.

## Common Pitfalls

- Vague theme labels without concrete theme-signature visual, action, scene, camera, material, and audio anchors.
- Unsupported factual claims. Real games, teams, or tournaments require research or recorded reference limits.
- Overloaded shots that ask one short clip to communicate too many actions or messages.
