---
skill_id: theme_sports_fitness
name: Sports and Fitness
description: Generation quality enhancement skill for sports, fitness, exercise, training, competitions, movement teaching, or sports montages; strengthens prompt detail, visual style, storyboard logic, content structure, scene design, and audio planning while preserving the main workflow.
trigger_keywords: [sports, fitness, exercise, training, competition]
match_rule:
  type: keyword_semantic_hybrid
  threshold: 0.8
  keyword_combinations:
    - [fitness, training]
    - [sports, competition]
    - [movement, breakdown]
  semantic_terms: [warm-up, stretching, muscle, explosive power, slow motion, equipment, running, court]
optimization_guide:
  prompt_enhancement: Emphasize athletic form, muscle tension, speed, breath timing, training goal, progression, safe posture, and performance stakes.
  visual_style: Dynamic tracking, slow-motion sweat or chalk, clear limb trajectories, court or field lines, and close-ups of equipment.
  storyboard_logic: warm-up or goal -> movement execution -> form detail -> intensity peak -> recovery or result.
  content_structure: Motivational but technique-focused language with simple cues for posture and breathing; avoid unsafe extremes.
  scene_design: Gyms, tracks, courts, fields, pools, rings, training halls, arenas, or outdoor routes.
  audio_design: Breath, footfalls, equipment impacts, whistles, crowd or coach cues, and high-energy BGM.
examples:
  - input: Generate a fitness training movement demo video
    output: Load the sports fitness theme and arrange warm-up, movement breakdown, slow motion, and stretching close.
---

# Sports and Fitness - Theme Skill

## When to Use

Load this skill when the user asks for sports, fitness, exercise, training, competitions, movement teaching, or sports montages.

## Process

### Step 1: Preserve Workflow
Only enhance generation quality. Do not change media review, approval, permissions, tool contracts, output policy, or explicit user instructions. Do not replace health/sports safety review or provide personalized medical advice.

### Step 2: Apply Optimization Guide
Inject the front matter `optimization_guide` into the creative brief, copywriting, styleframe, storyboard, scene design, and audio plan. Convert abstract style words into visible subjects, materials, actions, camera language, scene anchors, and audio cues, so the selected theme is legible without relying on the title or caption.

### Step 3: Theme Consistency Check
Before generation, check that the theme is visible in the subject, action/storyboard, scene, and audio plan. Conflicts with user instructions or safety requirements must be resolved in the review artifact before execution.

## Generation Detail Expansion

In the generation plan, storyboard, or final `expanded_generation_prompt`, add details around the "Sports and Fitness" theme. These details only improve generation quality and do not change the main process, review, approval, permissions, tool contracts, or explicit user instructions.

### Prompt Expansion Checklist
- Subject: specify identity, appearance, materials, start/end action states, and relationship to props, environment, or other subjects; choose details that are native to the matched theme.
- Theme reinforcement: Emphasize athletic form, muscle tension, speed, breath timing, training goal, progression, safe posture, and performance stakes.
- Cinematography: specify shot size, angle, camera movement, focus changes, foreground/midground/background layering, lighting, and transition context for each shot.
- Negative constraints: prevent drift such as unrelated styles, garbled text, watermarks, incorrect brand rendering, factual exaggeration, or scenes that conflict with the theme.

### Visual And Storyboard Expansion
- Visual details: Dynamic tracking, slow-motion sweat or chalk, clear limb trajectories, court or field lines, and close-ups of equipment.
- Storyboard rhythm: warm-up or goal -> movement execution -> form detail -> intensity peak -> recovery or result.
- Content structure: Motivational but technique-focused language with simple cues for posture and breathing; avoid unsafe extremes.
- Scene design: Gyms, tracks, courts, fields, pools, rings, training halls, arenas, or outdoor routes.
- Audio planning: Breath, footfalls, equipment impacts, whistles, crowd or coach cues, and high-energy BGM.

### Final Prompt Influence
- Each final prompt that matches this theme should include at least four explicit anchors: a theme-signature visual marker, an action/storyboard beat, a scene/material anchor, and a camera/lighting or audio cue.
- When multiple themes match, preserve the user's explicit theme first, then merge compatible elements; explain conflicting choices in `storyboard_review` or `media_plan_review`.
- Recommended `theme_consistency_score` is at least 0.8; if below threshold, revise the prompt, storyboard, scene, or audio plan before generation. Do not bypass `media-review-gate`.

## Common Pitfalls

- Vague theme labels without concrete theme-signature visual, action, scene, camera, material, and audio anchors.
- Unsupported factual claims. Do not replace health/sports safety review or provide personalized medical advice.
- Overloaded shots that ask one short clip to communicate too many actions or messages.
