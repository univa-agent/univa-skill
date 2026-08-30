---
skill_id: theme_travel_landscape
name: Travel and Landscape
description: Generation quality enhancement skill for travel, landscapes, scenery, travelogues, destination recommendations, or city/nature videos; strengthens prompt detail, visual style, storyboard logic, content structure, scene design, and audio planning while preserving the main workflow.
trigger_keywords: [travel, landscape, scenery, travelogue, destination]
match_rule:
  type: keyword_semantic_hybrid
  threshold: 0.8
  keyword_combinations:
    - [travel, destination]
    - [city, landscape]
    - [nature, scenery]
  semantic_terms: [aerial shot, landmark, sunrise, waves, mountains, old town, local culture, local music]
optimization_guide:
  prompt_enhancement: Emphasize destination-specific landmarks or geography, season, weather, route movement, local culture details, time of day, and reference limits; real destinations need reference research.
  visual_style: Golden-hour or blue-hour light, aerial and wide depth, natural colors, local texture close-ups, people-in-place, and transit motion.
  storyboard_logic: arrival or landmark panorama -> route details -> food, culture, or nature -> personal experience or emotional close.
  content_structure: Lyrical but factual travel copy with no invented routes, prices, or opening hours; tie mood to real visible details.
  scene_design: Viewpoints, markets, streets, transit nodes, hotels or lodging, trails, coasts, mountains, or cultural sites.
  audio_design: Wind, waves, street ambience, footsteps, transit sounds, and local music atmosphere.
examples:
  - input: Create a Yunnan travel landscape short film
    output: Load the travel landscape theme, research references first, then organize landmarks, local markets, mountains/water, and relaxed music.
---

# Travel and Landscape - Theme Skill

## When to Use

Load this skill when the user asks for travel, landscapes, scenery, travelogues, destination recommendations, or city/nature videos.

## Process

### Step 1: Preserve Workflow
Only enhance generation quality. Do not change media review, approval, permissions, tool contracts, output policy, or explicit user instructions. Real places, attractions, transportation, and events must be recorded as references or limits before generation.

### Step 2: Apply Optimization Guide
Inject the front matter `optimization_guide` into the creative brief, copywriting, styleframe, storyboard, scene design, and audio plan. Convert abstract style words into visible subjects, materials, actions, camera language, scene anchors, and audio cues, so the selected theme is legible without relying on the title or caption.

### Step 3: Theme Consistency Check
Before generation, check that the theme is visible in the subject, action/storyboard, scene, and audio plan. Conflicts with user instructions or safety requirements must be resolved in the review artifact before execution.

## Generation Detail Expansion

In the generation plan, storyboard, or final `expanded_generation_prompt`, add details around the "Travel and Landscape" theme. These details only improve generation quality and do not change the main process, review, approval, permissions, tool contracts, or explicit user instructions.

### Prompt Expansion Checklist
- Subject: specify identity, appearance, materials, start/end action states, and relationship to props, environment, or other subjects; choose details that are native to the matched theme.
- Theme reinforcement: Emphasize destination-specific landmarks or geography, season, weather, route movement, local culture details, time of day, and reference limits; real destinations need reference research.
- Cinematography: specify shot size, angle, camera movement, focus changes, foreground/midground/background layering, lighting, and transition context for each shot.
- Negative constraints: prevent drift such as unrelated styles, garbled text, watermarks, incorrect brand rendering, factual exaggeration, or scenes that conflict with the theme.

### Visual And Storyboard Expansion
- Visual details: Golden-hour or blue-hour light, aerial and wide depth, natural colors, local texture close-ups, people-in-place, and transit motion.
- Storyboard rhythm: arrival or landmark panorama -> route details -> food, culture, or nature -> personal experience or emotional close.
- Content structure: Lyrical but factual travel copy with no invented routes, prices, or opening hours; tie mood to real visible details.
- Scene design: Viewpoints, markets, streets, transit nodes, hotels or lodging, trails, coasts, mountains, or cultural sites.
- Audio planning: Wind, waves, street ambience, footsteps, transit sounds, and local music atmosphere.

### Final Prompt Influence
- Each final prompt that matches this theme should include at least four explicit anchors: a theme-signature visual marker, an action/storyboard beat, a scene/material anchor, and a camera/lighting or audio cue.
- When multiple themes match, preserve the user's explicit theme first, then merge compatible elements; explain conflicting choices in `storyboard_review` or `media_plan_review`.
- Recommended `theme_consistency_score` is at least 0.8; if below threshold, revise the prompt, storyboard, scene, or audio plan before generation. Do not bypass `media-review-gate`.

## Common Pitfalls

- Vague theme labels without concrete theme-signature visual, action, scene, camera, material, and audio anchors.
- Unsupported factual claims. Real places, attractions, transportation, and events must be recorded as references or limits before generation.
- Overloaded shots that ask one short clip to communicate too many actions or messages.
