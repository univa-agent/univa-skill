---
skill_id: theme_comic_style
name: Comic Style
description: Generation quality enhancement skill for comics, anime, cartoons, hand-drawn style, manga, or comic-like expression; strengthens prompt detail, visual style, storyboard logic, content structure, scene design, and audio planning while preserving the main workflow.
trigger_keywords: [comic, anime, cartoon, hand-drawn, manga]
match_rule:
  type: keyword_semantic_hybrid
  threshold: 0.8
  keyword_combinations:
    - [manga, comic]
    - [hand-drawn, animation]
    - [cartoon, character]
  semantic_terms: [screen tone, speed line, panel layout, onomatopoeia, speech bubble, hot-blooded, cute style, cel shading]
optimization_guide:
  prompt_enhancement: Add panel borders, screen tones, speed lines, impact frames, exaggerated expressions, pose silhouettes, speech bubble placement, and onomatopoeia.
  visual_style: Crisp inked outlines, flat fills or cel shading, readable bubbles, halftone texture, exaggerated perspective, and bold accent colors.
  storyboard_logic: establishing panel -> reaction close-up -> action panel -> impact freeze -> punchline or turning panel.
  content_structure: Short readable dialogue with strong emotion or action contrast and a clear panel-by-panel beat; avoid text-dense bubbles.
  scene_design: A consistent comic world with recurring backgrounds, props, panel layout, readable spatial continuity, and stylized exaggeration.
  audio_design: Page-turns, whooshes, impact hits, pop stingers, and cheerful or high-energy BGM.
examples:
  - input: Create an anime comic-style school confession short
    output: Load the comic style theme and use multi-panel shots, expression close-ups, speech bubbles, and speed-line transitions.
---

# Comic Style - Theme Skill

## When to Use

Load this skill when the user asks for comics, anime, cartoons, hand-drawn style, manga, or comic-like expression.

## Process

### Step 1: Preserve Workflow
Only enhance generation quality. Do not change media review, approval, permissions, tool contracts, output policy, or explicit user instructions. Use caption_plan or Remotion for real subtitles; do not rely on the generation model to draw long readable text.

### Step 2: Apply Optimization Guide
Inject the front matter `optimization_guide` into the creative brief, copywriting, styleframe, storyboard, scene design, and audio plan. Convert abstract style words into visible subjects, materials, actions, camera language, scene anchors, and audio cues, so the selected theme is legible without relying on the title or caption.

### Step 3: Theme Consistency Check
Before generation, check that the theme is visible in the subject, action/storyboard, scene, and audio plan. Conflicts with user instructions or safety requirements must be resolved in the review artifact before execution.

## Generation Detail Expansion

In the generation plan, storyboard, or final `expanded_generation_prompt`, add details around the "Comic Style" theme. These details only improve generation quality and do not change the main process, review, approval, permissions, tool contracts, or explicit user instructions.

### Prompt Expansion Checklist
- Subject: specify identity, appearance, materials, start/end action states, and relationship to props, environment, or other subjects; choose details that are native to the matched theme.
- Theme reinforcement: Add panel borders, screen tones, speed lines, impact frames, exaggerated expressions, pose silhouettes, speech bubble placement, and onomatopoeia.
- Cinematography: specify shot size, angle, camera movement, focus changes, foreground/midground/background layering, lighting, and transition context for each shot.
- Negative constraints: prevent drift such as unrelated styles, garbled text, watermarks, incorrect brand rendering, factual exaggeration, or scenes that conflict with the theme.

### Visual And Storyboard Expansion
- Visual details: Crisp inked outlines, flat fills or cel shading, readable bubbles, halftone texture, exaggerated perspective, and bold accent colors.
- Storyboard rhythm: establishing panel -> reaction close-up -> action panel -> impact freeze -> punchline or turning panel.
- Content structure: Short readable dialogue with strong emotion or action contrast and a clear panel-by-panel beat; avoid text-dense bubbles.
- Scene design: A consistent comic world with recurring backgrounds, props, panel layout, readable spatial continuity, and stylized exaggeration.
- Audio planning: Page-turns, whooshes, impact hits, pop stingers, and cheerful or high-energy BGM.

### Final Prompt Influence
- Each final prompt that matches this theme should include at least four explicit anchors: a theme-signature visual marker, an action/storyboard beat, a scene/material anchor, and a camera/lighting or audio cue.
- When multiple themes match, preserve the user's explicit theme first, then merge compatible elements; explain conflicting choices in `storyboard_review` or `media_plan_review`.
- Recommended `theme_consistency_score` is at least 0.8; if below threshold, revise the prompt, storyboard, scene, or audio plan before generation. Do not bypass `media-review-gate`.

## Common Pitfalls

- Vague theme labels without concrete theme-signature visual, action, scene, camera, material, and audio anchors.
- Unsupported factual claims. Use caption_plan or Remotion for real subtitles; do not rely on the generation model to draw long readable text.
- Overloaded shots that ask one short clip to communicate too many actions or messages.
