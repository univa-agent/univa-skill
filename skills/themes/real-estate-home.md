---
skill_id: theme_real_estate_home
name: Real Estate and Home
description: Generation quality enhancement skill for real estate, property, renovation, interior design, home, show homes, or space makeover content; strengthens prompt detail, visual style, storyboard logic, content structure, scene design, and audio planning while preserving the main workflow.
trigger_keywords: [real estate, property, renovation, interior design, home tour, show home]
match_rule:
  type: keyword_semantic_hybrid
  threshold: 0.8
  keyword_combinations:
    - [property, promotion]
    - [interior, design]
    - [renovation, makeover]
  semantic_terms: [floor plan, living room, bedroom, daylight, storage, material, soft furnishing, show home]
optimization_guide:
  prompt_enhancement: Emphasize spatial layout, room flow, daylight direction, materials, storage, functional zones, human scale, lifestyle use, and verified property info; real property information needs sources.
  visual_style: Stable wide shots without distortion, natural daylight, material texture close-ups, clean staging, doorway transitions, window views, and warm lived-in feeling.
  storyboard_logic: exterior or entry -> circulation path -> core living area -> functional detail -> lifestyle moment -> selling-point close.
  content_structure: Describe spatial experience and functional benefits; mark area, price, location, and school-district claims only when sourced.
  scene_design: Facades, foyers, living rooms, kitchens, bedrooms, bathrooms, balconies, community amenities, or before-after renovation scenes.
  audio_design: Soft lifestyle BGM, door, window, and footstep sounds, room tone, and outdoor ambience.
examples:
  - input: Generate a modern show-home promo video
    output: Load the real estate and home theme and organize by entrance, living room, kitchen, bedroom, storage, and lifestyle scenes.
---

# Real Estate and Home - Theme Skill

## When to Use

Load this skill when the user asks for real estate, property, renovation, interior design, home, show homes, or space makeover content.

## Process

### Step 1: Preserve Workflow
Only enhance generation quality. Do not change media review, approval, permissions, tool contracts, output policy, or explicit user instructions. Real prices, area, ownership, school districts, delivery dates, and developer information must be source-confirmed.

### Step 2: Apply Optimization Guide
Inject the front matter `optimization_guide` into the creative brief, copywriting, styleframe, storyboard, scene design, and audio plan. Convert abstract style words into visible subjects, materials, actions, camera language, scene anchors, and audio cues, so the selected theme is legible without relying on the title or caption.

### Step 3: Theme Consistency Check
Before generation, check that the theme is visible in the subject, action/storyboard, scene, and audio plan. Conflicts with user instructions or safety requirements must be resolved in the review artifact before execution.

## Generation Detail Expansion

In the generation plan, storyboard, or final `expanded_generation_prompt`, add details around the "Real Estate and Home" theme. These details only improve generation quality and do not change the main process, review, approval, permissions, tool contracts, or explicit user instructions.

### Prompt Expansion Checklist
- Subject: specify identity, appearance, materials, start/end action states, and relationship to props, environment, or other subjects; choose details that are native to the matched theme.
- Theme reinforcement: Emphasize spatial layout, room flow, daylight direction, materials, storage, functional zones, human scale, lifestyle use, and verified property info; real property information needs sources.
- Cinematography: specify shot size, angle, camera movement, focus changes, foreground/midground/background layering, lighting, and transition context for each shot.
- Negative constraints: prevent drift such as unrelated styles, garbled text, watermarks, incorrect brand rendering, factual exaggeration, or scenes that conflict with the theme.

### Visual And Storyboard Expansion
- Visual details: Stable wide shots without distortion, natural daylight, material texture close-ups, clean staging, doorway transitions, window views, and warm lived-in feeling.
- Storyboard rhythm: exterior or entry -> circulation path -> core living area -> functional detail -> lifestyle moment -> selling-point close.
- Content structure: Describe spatial experience and functional benefits; mark area, price, location, and school-district claims only when sourced.
- Scene design: Facades, foyers, living rooms, kitchens, bedrooms, bathrooms, balconies, community amenities, or before-after renovation scenes.
- Audio planning: Soft lifestyle BGM, door, window, and footstep sounds, room tone, and outdoor ambience.

### Final Prompt Influence
- Each final prompt that matches this theme should include at least four explicit anchors: a theme-signature visual marker, an action/storyboard beat, a scene/material anchor, and a camera/lighting or audio cue.
- When multiple themes match, preserve the user's explicit theme first, then merge compatible elements; explain conflicting choices in `storyboard_review` or `media_plan_review`.
- Recommended `theme_consistency_score` is at least 0.8; if below threshold, revise the prompt, storyboard, scene, or audio plan before generation. Do not bypass `media-review-gate`.

## Common Pitfalls

- Vague theme labels without concrete theme-signature visual, action, scene, camera, material, and audio anchors.
- Unsupported factual claims. Real prices, area, ownership, school districts, delivery dates, and developer information must be source-confirmed.
- Overloaded shots that ask one short clip to communicate too many actions or messages.
