---
skill_id: theme_automotive_mobility
name: Automotive and Mobility
description: Generation quality enhancement skill for cars, new vehicles, test drives, mobility, transportation, car reviews, or automotive ads; strengthens prompt detail, visual style, storyboard logic, content structure, scene design, and audio planning while preserving the main workflow.
trigger_keywords: [cars, car video, car ad, car review, automotive, new vehicle, test drive, mobility, transportation]
match_rule:
  type: keyword_semantic_hybrid
  threshold: 0.8
  keyword_combinations:
    - [automotive, advertising]
    - [vehicle, advertising]
    - [new vehicle, launch]
    - [test drive, experience]
  semantic_terms: [cabin, powertrain, range, wheels, headlights, road, driver assistance, engine sound]
optimization_guide:
  prompt_enhancement: Highlight silhouette, grille and light signature, wheel and body motion, cabin ergonomics, road condition, use scenario, and verified specs; real vehicle specifications require sources.
  visual_style: Low-angle tracking, rolling shots, controlled body reflections, headlight and taillight signatures, interior controls, road and weather interaction, and speed ramps.
  storyboard_logic: exterior silhouette reveal -> signature detail -> dynamic road move -> cabin interaction -> scenario proof -> value summary.
  content_structure: Balance emotional driving impressions with concrete feature callouts; mark parameters as assumptions when specs are uncertain.
  scene_design: City dusk roads, mountain hairpins, coastal highways, showrooms, charging stations, vehicle cabins, parking-assist scenes, or rain and night roads.
  audio_design: Engine or motor ramps, tire texture, door, indicator, and seatbelt sounds, wind passes, and energetic BGM.
examples:
  - input: Create a short test-drive film for a new energy vehicle
    output: Load the automotive theme and plan around exterior, cabin, driver assistance, range scenarios, and road motion.
---

# Automotive and Mobility - Theme Skill

## When to Use

Load this skill when the user asks for cars, new vehicles, test drives, mobility, transportation, car reviews, or automotive ads.

## Process

### Step 1: Preserve Workflow
Only enhance generation quality. Do not change media review, approval, permissions, tool contracts, output policy, or explicit user instructions. Model specs, prices, safety ratings, subsidies, and regulations must come from the user or reliable sources.

### Step 2: Apply Optimization Guide
Inject the front matter `optimization_guide` into the creative brief, copywriting, styleframe, storyboard, scene design, and audio plan. Convert abstract style words into visible subjects, materials, actions, camera language, scene anchors, and audio cues, so the selected theme is legible without relying on the title or caption.

### Step 3: Theme Consistency Check
Before generation, check that the theme is visible in the subject, action/storyboard, scene, and audio plan. Conflicts with user instructions or safety requirements must be resolved in the review artifact before execution.

## Generation Detail Expansion

In the generation plan, storyboard, or final `expanded_generation_prompt`, add details around the "Automotive and Mobility" theme. These details only improve generation quality and do not change the main process, review, approval, permissions, tool contracts, or explicit user instructions.

### Prompt Expansion Checklist
- Subject: specify identity, appearance, materials, start/end action states, and relationship to props, environment, or other subjects; choose details that are native to the matched theme.
- Theme reinforcement: Highlight silhouette, grille and light signature, wheel and body motion, cabin ergonomics, road condition, use scenario, and verified specs; real vehicle specifications require sources.
- Cinematography: specify shot size, angle, camera movement, focus changes, foreground/midground/background layering, lighting, and transition context for each shot.
- Negative constraints: prevent drift such as unrelated styles, garbled text, watermarks, incorrect brand rendering, factual exaggeration, or scenes that conflict with the theme.

### Visual And Storyboard Expansion
- Visual details: Low-angle tracking, rolling shots, controlled body reflections, headlight and taillight signatures, interior controls, road and weather interaction, and speed ramps.
- Storyboard rhythm: exterior silhouette reveal -> signature detail -> dynamic road move -> cabin interaction -> scenario proof -> value summary.
- Content structure: Balance emotional driving impressions with concrete feature callouts; mark parameters as assumptions when specs are uncertain.
- Scene design: City dusk roads, mountain hairpins, coastal highways, showrooms, charging stations, vehicle cabins, parking-assist scenes, or rain and night roads.
- Audio planning: Engine or motor ramps, tire texture, door, indicator, and seatbelt sounds, wind passes, and energetic BGM.

### Final Prompt Influence
- Each final prompt that matches this theme should include at least four explicit anchors: a theme-signature visual marker, an action/storyboard beat, a scene/material anchor, and a camera/lighting or audio cue.
- When multiple themes match, preserve the user's explicit theme first, then merge compatible elements; explain conflicting choices in `storyboard_review` or `media_plan_review`.
- Recommended `theme_consistency_score` is at least 0.8; if below threshold, revise the prompt, storyboard, scene, or audio plan before generation. Do not bypass `media-review-gate`.

## Common Pitfalls

- Vague theme labels without concrete theme-signature visual, action, scene, camera, material, and audio anchors.
- Unsupported factual claims. Model specs, prices, safety ratings, subsidies, and regulations must come from the user or reliable sources.
- Overloaded shots that ask one short clip to communicate too many actions or messages.
