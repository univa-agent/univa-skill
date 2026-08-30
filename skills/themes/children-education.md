---
skill_id: theme_children_education
name: Children Education
description: Generation quality enhancement skill for children, early education, preschool, parent-child content, nursery rhymes, children animation, or young-audience education; strengthens prompt detail, visual style, storyboard logic, content structure, scene design, and audio planning while preserving the main workflow.
trigger_keywords: [children, early education, preschool, parent-child, nursery rhyme]
match_rule:
  type: keyword_semantic_hybrid
  threshold: 0.8
  keyword_combinations:
    - [children, education]
    - [parent-child, interaction]
    - [preschool, animation]
  semantic_terms: [child voice, cartoon character, color recognition, numbers, letters, animal sounds, fairy tale, repeated sentence]
optimization_guide:
  prompt_enhancement: Use simple cute language, repeated sentences, onomatopoeia, visible cause-effect actions, friendly questions, and safety or comfort cues.
  visual_style: Bright varied colors, rounded silhouettes, large readable props, warm expressions, soft motion, and low-stimulation backgrounds.
  storyboard_logic: introduce friendly character -> show action -> repeat concept visually -> child interaction -> reward or recap.
  content_structure: One age-appropriate concept per segment, repeated phrase, short positive question, and no dense text or frightening stakes.
  scene_design: Kindergartens, bedrooms, playrooms, storybook gardens, toy tables, lawns, or soft animal park scenes.
  audio_design: Cheerful nursery-rhyme melody, gentle child-safe voices, soft animal and toy sounds, and clear answer chimes.
examples:
  - input: Generate a nursery-rhyme video that teaches children colors
    output: Load the children education theme and use repeated sentences, rounded cartoon characters, slow pacing, and child-friendly audio.
---

# Children Education - Theme Skill

## When to Use

Load this skill when the user asks for children, early education, preschool, parent-child content, nursery rhymes, children animation, or young-audience education.

## Process

### Step 1: Preserve Workflow
Only enhance generation quality. Do not change media review, approval, permissions, tool contracts, output policy, or explicit user instructions. Dangerous actions, medical advice, privacy information, and age-inappropriate content must follow the main process.

### Step 2: Apply Optimization Guide
Inject the front matter `optimization_guide` into the creative brief, copywriting, styleframe, storyboard, scene design, and audio plan. Convert abstract style words into visible subjects, materials, actions, camera language, scene anchors, and audio cues, so the selected theme is legible without relying on the title or caption.

### Step 3: Theme Consistency Check
Before generation, check that the theme is visible in the subject, action/storyboard, scene, and audio plan. Conflicts with user instructions or safety requirements must be resolved in the review artifact before execution.

## Generation Detail Expansion

In the generation plan, storyboard, or final `expanded_generation_prompt`, add details around the "Children Education" theme. These details only improve generation quality and do not change the main process, review, approval, permissions, tool contracts, or explicit user instructions.

### Prompt Expansion Checklist
- Subject: specify identity, appearance, materials, start/end action states, and relationship to props, environment, or other subjects; choose details that are native to the matched theme.
- Theme reinforcement: Use simple cute language, repeated sentences, onomatopoeia, visible cause-effect actions, friendly questions, and safety or comfort cues.
- Cinematography: specify shot size, angle, camera movement, focus changes, foreground/midground/background layering, lighting, and transition context for each shot.
- Negative constraints: prevent drift such as unrelated styles, garbled text, watermarks, incorrect brand rendering, factual exaggeration, or scenes that conflict with the theme.

### Visual And Storyboard Expansion
- Visual details: Bright varied colors, rounded silhouettes, large readable props, warm expressions, soft motion, and low-stimulation backgrounds.
- Storyboard rhythm: introduce friendly character -> show action -> repeat concept visually -> child interaction -> reward or recap.
- Content structure: One age-appropriate concept per segment, repeated phrase, short positive question, and no dense text or frightening stakes.
- Scene design: Kindergartens, bedrooms, playrooms, storybook gardens, toy tables, lawns, or soft animal park scenes.
- Audio planning: Cheerful nursery-rhyme melody, gentle child-safe voices, soft animal and toy sounds, and clear answer chimes.

### Final Prompt Influence
- Each final prompt that matches this theme should include at least four explicit anchors: a theme-signature visual marker, an action/storyboard beat, a scene/material anchor, and a camera/lighting or audio cue.
- When multiple themes match, preserve the user's explicit theme first, then merge compatible elements; explain conflicting choices in `storyboard_review` or `media_plan_review`.
- Recommended `theme_consistency_score` is at least 0.8; if below threshold, revise the prompt, storyboard, scene, or audio plan before generation. Do not bypass `media-review-gate`.

## Common Pitfalls

- Vague theme labels without concrete theme-signature visual, action, scene, camera, material, and audio anchors.
- Unsupported factual claims. Dangerous actions, medical advice, privacy information, and age-inappropriate content must follow the main process.
- Overloaded shots that ask one short clip to communicate too many actions or messages.
