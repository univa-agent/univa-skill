---
skill_id: theme_scifi_anime
name: Sci-Fi Anime
description: Generation quality enhancement skill for science fiction, cyberpunk, mecha, future, interstellar, or high-tech anime visuals; strengthens prompt detail, visual style, storyboard logic, content structure, scene design, and audio planning while preserving the main workflow.
trigger_keywords: [science fiction, cyberpunk, mecha, future, interstellar]
match_rule:
  type: keyword_semantic_hybrid
  threshold: 0.8
  keyword_combinations:
    - [future, city]
    - [interstellar, spaceship]
    - [mechanical, armor]
  semantic_terms: [hologram, neon, space station, artificial intelligence, exoskeleton, lightsaber, energy core, aircraft]
optimization_guide:
  prompt_enhancement: Add signature tech objects, neon or hologram cues, mechanical joints, energy source, world scale, mission objective, and material contrast.
  visual_style: High-contrast anime or cinematic look, glowing edges, metal, carbon, and glass textures, volumetric light, UI overlays, and grand spatial scale.
  storyboard_logic: world or mission hook -> tech activation -> high-motion effect -> scale reveal -> character or mecha detail.
  content_structure: Clear conflict or mission with concise technical terms; avoid noun-stacked pseudo-science.
  scene_design: Neon cities, orbital stations, hangars, cockpits, laboratories, alien terrain, or starship corridors.
  audio_design: Synth arpeggios, servo and mecha sounds, UI beeps, energy hums, bass impacts, and space ambience.
examples:
  - input: Create a cyberpunk mecha chase video
    output: Load the sci-fi anime theme and use neon streets, mecha structure close-ups, fast chase shots, and electronic sound effects.
---

# Sci-Fi Anime - Theme Skill

## When to Use

Load this skill when the user asks for science fiction, cyberpunk, mecha, future, interstellar, or high-tech anime visuals.

## Process

### Step 1: Preserve Workflow
Only enhance generation quality. Do not change media review, approval, permissions, tool contracts, output policy, or explicit user instructions. Break abstract tech feeling into visible materials, lights, energy, interfaces, mechanical layers, scale, and action causality.

### Step 2: Apply Optimization Guide
Inject the front matter `optimization_guide` into the creative brief, copywriting, styleframe, storyboard, scene design, and audio plan. Convert abstract style words into visible subjects, materials, actions, camera language, scene anchors, and audio cues, so the selected theme is legible without relying on the title or caption.

### Step 3: Theme Consistency Check
Before generation, check that the theme is visible in the subject, action/storyboard, scene, and audio plan. Conflicts with user instructions or safety requirements must be resolved in the review artifact before execution.

## Generation Detail Expansion

In the generation plan, storyboard, or final `expanded_generation_prompt`, add details around the "Sci-Fi Anime" theme. These details only improve generation quality and do not change the main process, review, approval, permissions, tool contracts, or explicit user instructions.

### Prompt Expansion Checklist
- Subject: specify identity, appearance, materials, start/end action states, and relationship to props, environment, or other subjects; choose details that are native to the matched theme.
- Theme reinforcement: Add signature tech objects, neon or hologram cues, mechanical joints, energy source, world scale, mission objective, and material contrast.
- Cinematography: specify shot size, angle, camera movement, focus changes, foreground/midground/background layering, lighting, and transition context for each shot.
- Negative constraints: prevent drift such as unrelated styles, garbled text, watermarks, incorrect brand rendering, factual exaggeration, or scenes that conflict with the theme.

### Visual And Storyboard Expansion
- Visual details: High-contrast anime or cinematic look, glowing edges, metal, carbon, and glass textures, volumetric light, UI overlays, and grand spatial scale.
- Storyboard rhythm: world or mission hook -> tech activation -> high-motion effect -> scale reveal -> character or mecha detail.
- Content structure: Clear conflict or mission with concise technical terms; avoid noun-stacked pseudo-science.
- Scene design: Neon cities, orbital stations, hangars, cockpits, laboratories, alien terrain, or starship corridors.
- Audio planning: Synth arpeggios, servo and mecha sounds, UI beeps, energy hums, bass impacts, and space ambience.

### Final Prompt Influence
- Each final prompt that matches this theme should include at least four explicit anchors: a theme-signature visual marker, an action/storyboard beat, a scene/material anchor, and a camera/lighting or audio cue.
- When multiple themes match, preserve the user's explicit theme first, then merge compatible elements; explain conflicting choices in `storyboard_review` or `media_plan_review`.
- Recommended `theme_consistency_score` is at least 0.8; if below threshold, revise the prompt, storyboard, scene, or audio plan before generation. Do not bypass `media-review-gate`.

## Common Pitfalls

- Vague theme labels without concrete theme-signature visual, action, scene, camera, material, and audio anchors.
- Unsupported factual claims. Break abstract tech feeling into visible materials, lights, energy, interfaces, mechanical layers, scale, and action causality.
- Overloaded shots that ask one short clip to communicate too many actions or messages.
