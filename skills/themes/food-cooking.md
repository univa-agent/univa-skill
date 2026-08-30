---
skill_id: theme_food_cooking
name: Food and Cooking
description: Generation quality enhancement skill for food, cooking, recipes, kitchens, baking, restaurant dish showcases, or ingredient videos; strengthens prompt detail, visual style, storyboard logic, content structure, scene design, and audio planning while preserving the main workflow.
trigger_keywords: [food, cooking, recipe, kitchen, baking]
match_rule:
  type: keyword_semantic_hybrid
  threshold: 0.8
  keyword_combinations:
    - [kitchen, cooking]
    - [baking, cake]
    - [ingredient, cooking]
  semantic_terms: [chopping, frying, steam, cheese pull, sauce, plating, texture, recipe]
optimization_guide:
  prompt_enhancement: Emphasize ingredient freshness, texture, knife and cooking motions, heat, steam, sauce behavior, transformation moment, plating, and appetite appeal.
  visual_style: Warm natural light, macro texture, steam and sizzle, glossy sauce pours, clean surfaces, color contrast, and hand interaction.
  storyboard_logic: ingredient beauty -> prep action -> heat transformation -> sauce or plating -> bite, reveal, or tip.
  content_structure: Clear step names and sensory words with one cooking action per shot; mark uncertain quantities and times as illustrative.
  scene_design: Home kitchens, restaurant passes, wooden tables, baking counters, street-food stalls, or market ingredient scenes.
  audio_design: Chopping, frying, bubbling, stirring, pouring, crunch or bite sounds, and light upbeat kitchen BGM.
examples:
  - input: Generate a short baking tutorial for a cake
    output: Load the food and cooking theme and organize by prep, mixing, baking, decoration, and final slice.
---

# Food and Cooking - Theme Skill

## When to Use

Load this skill when the user asks for food, cooking, recipes, kitchens, baking, restaurant dish showcases, or ingredient videos.

## Process

### Step 1: Preserve Workflow
Only enhance generation quality. Do not change media review, approval, permissions, tool contracts, output policy, or explicit user instructions. For real recipes, avoid inventing dangerous methods or unverified health effects.

### Step 2: Apply Optimization Guide
Inject the front matter `optimization_guide` into the creative brief, copywriting, styleframe, storyboard, scene design, and audio plan. Convert abstract style words into visible subjects, materials, actions, camera language, scene anchors, and audio cues, so the selected theme is legible without relying on the title or caption.

### Step 3: Theme Consistency Check
Before generation, check that the theme is visible in the subject, action/storyboard, scene, and audio plan. Conflicts with user instructions or safety requirements must be resolved in the review artifact before execution.

## Generation Detail Expansion

In the generation plan, storyboard, or final `expanded_generation_prompt`, add details around the "Food and Cooking" theme. These details only improve generation quality and do not change the main process, review, approval, permissions, tool contracts, or explicit user instructions.

### Prompt Expansion Checklist
- Subject: specify identity, appearance, materials, start/end action states, and relationship to props, environment, or other subjects; choose details that are native to the matched theme.
- Theme reinforcement: Emphasize ingredient freshness, texture, knife and cooking motions, heat, steam, sauce behavior, transformation moment, plating, and appetite appeal.
- Cinematography: specify shot size, angle, camera movement, focus changes, foreground/midground/background layering, lighting, and transition context for each shot.
- Negative constraints: prevent drift such as unrelated styles, garbled text, watermarks, incorrect brand rendering, factual exaggeration, or scenes that conflict with the theme.

### Visual And Storyboard Expansion
- Visual details: Warm natural light, macro texture, steam and sizzle, glossy sauce pours, clean surfaces, color contrast, and hand interaction.
- Storyboard rhythm: ingredient beauty -> prep action -> heat transformation -> sauce or plating -> bite, reveal, or tip.
- Content structure: Clear step names and sensory words with one cooking action per shot; mark uncertain quantities and times as illustrative.
- Scene design: Home kitchens, restaurant passes, wooden tables, baking counters, street-food stalls, or market ingredient scenes.
- Audio planning: Chopping, frying, bubbling, stirring, pouring, crunch or bite sounds, and light upbeat kitchen BGM.

### Final Prompt Influence
- Each final prompt that matches this theme should include at least four explicit anchors: a theme-signature visual marker, an action/storyboard beat, a scene/material anchor, and a camera/lighting or audio cue.
- When multiple themes match, preserve the user's explicit theme first, then merge compatible elements; explain conflicting choices in `storyboard_review` or `media_plan_review`.
- Recommended `theme_consistency_score` is at least 0.8; if below threshold, revise the prompt, storyboard, scene, or audio plan before generation. Do not bypass `media-review-gate`.

## Common Pitfalls

- Vague theme labels without concrete theme-signature visual, action, scene, camera, material, and audio anchors.
- Unsupported factual claims. For real recipes, avoid inventing dangerous methods or unverified health effects.
- Overloaded shots that ask one short clip to communicate too many actions or messages.
