---
skill_id: theme_tech_product_review
name: Tech Product Review
description: Generation quality enhancement skill for technology, digital products, reviews, unboxing, specifications, experience, comparisons, or buying advice; strengthens prompt detail, visual style, storyboard logic, content structure, scene design, and audio planning while preserving the main workflow.
trigger_keywords: [technology, digital product, review, unboxing, specs]
match_rule:
  type: keyword_semantic_hybrid
  threshold: 0.8
  keyword_combinations:
    - [digital, review]
    - [tech, product]
    - [unboxing, specs]
  semantic_terms: [performance, benchmark, battery life, screen, chip, charging, comparison, experience]
optimization_guide:
  prompt_enhancement: Highlight exact device identity when provided, build material, specs with sources, test scenario, UX friction, pros and cons, and audience fit.
  visual_style: Clean desk or studio lighting, macro ports, buttons, and screens, rotation shots, benchmark or data cards, comparison layout, and screen reflections.
  storyboard_logic: unbox or context -> design tour -> spec or test -> real-use scenario -> pros and cons -> recommendation.
  content_structure: Objective evidence-supported review language that separates measured data from opinion and avoids unsourced rankings.
  scene_design: Review desks, lab benches, outdoor camera or battery tests, commute or work desks, and comparison table scenes.
  audio_design: Keyboard, click, notification, and unboxing sounds, light electronic BGM, and crisp transition cues.
examples:
  - input: Create an unboxing review video for a phone
    output: Load the tech product review theme and organize by unboxing, exterior, screen, performance, camera, and buying advice.
---

# Tech Product Review - Theme Skill

## When to Use

Load this skill when the user asks for technology, digital products, reviews, unboxing, specifications, experience, comparisons, or buying advice.

## Process

### Step 1: Preserve Workflow
Only enhance generation quality. Do not change media review, approval, permissions, tool contracts, output policy, or explicit user instructions. Specific specs, prices, release dates, benchmarks, and competitor conclusions must come from the user or current reliable sources.

### Step 2: Apply Optimization Guide
Inject the front matter `optimization_guide` into the creative brief, copywriting, styleframe, storyboard, scene design, and audio plan. Convert abstract style words into visible subjects, materials, actions, camera language, scene anchors, and audio cues, so the selected theme is legible without relying on the title or caption.

### Step 3: Theme Consistency Check
Before generation, check that the theme is visible in the subject, action/storyboard, scene, and audio plan. Conflicts with user instructions or safety requirements must be resolved in the review artifact before execution.

## Generation Detail Expansion

In the generation plan, storyboard, or final `expanded_generation_prompt`, add details around the "Tech Product Review" theme. These details only improve generation quality and do not change the main process, review, approval, permissions, tool contracts, or explicit user instructions.

### Prompt Expansion Checklist
- Subject: specify identity, appearance, materials, start/end action states, and relationship to props, environment, or other subjects; choose details that are native to the matched theme.
- Theme reinforcement: Highlight exact device identity when provided, build material, specs with sources, test scenario, UX friction, pros and cons, and audience fit.
- Cinematography: specify shot size, angle, camera movement, focus changes, foreground/midground/background layering, lighting, and transition context for each shot.
- Negative constraints: prevent drift such as unrelated styles, garbled text, watermarks, incorrect brand rendering, factual exaggeration, or scenes that conflict with the theme.

### Visual And Storyboard Expansion
- Visual details: Clean desk or studio lighting, macro ports, buttons, and screens, rotation shots, benchmark or data cards, comparison layout, and screen reflections.
- Storyboard rhythm: unbox or context -> design tour -> spec or test -> real-use scenario -> pros and cons -> recommendation.
- Content structure: Objective evidence-supported review language that separates measured data from opinion and avoids unsourced rankings.
- Scene design: Review desks, lab benches, outdoor camera or battery tests, commute or work desks, and comparison table scenes.
- Audio planning: Keyboard, click, notification, and unboxing sounds, light electronic BGM, and crisp transition cues.

### Final Prompt Influence
- Each final prompt that matches this theme should include at least four explicit anchors: a theme-signature visual marker, an action/storyboard beat, a scene/material anchor, and a camera/lighting or audio cue.
- When multiple themes match, preserve the user's explicit theme first, then merge compatible elements; explain conflicting choices in `storyboard_review` or `media_plan_review`.
- Recommended `theme_consistency_score` is at least 0.8; if below threshold, revise the prompt, storyboard, scene, or audio plan before generation. Do not bypass `media-review-gate`.

## Common Pitfalls

- Vague theme labels without concrete theme-signature visual, action, scene, camera, material, and audio anchors.
- Unsupported factual claims. Specific specs, prices, release dates, benchmarks, and competitor conclusions must come from the user or current reliable sources.
- Overloaded shots that ask one short clip to communicate too many actions or messages.
