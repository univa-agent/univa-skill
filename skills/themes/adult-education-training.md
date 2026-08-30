---
skill_id: theme_adult_education_training
name: Adult Education and Training
description: Generation quality enhancement skill for adult education, courses, learning, vocational training, online courses, public classes, or teaching promotion; strengthens prompt detail, visual style, storyboard logic, content structure, scene design, and audio planning while preserving the main workflow.
trigger_keywords: [adult education, training, course, learning, vocational training, online course]
match_rule:
  type: keyword_semantic_hybrid
  threshold: 0.8
  keyword_combinations:
    - [course, promotion]
    - [vocational, training]
    - [learning, method]
  semantic_terms: [knowledge point, exercise, case study, teacher, whiteboard, slides, learner, certificate]
optimization_guide:
  prompt_enhancement: Clarify the learning outcome, learner profile, pain point, before-after competence, case demonstration, practice step, and next action; avoid false certificate or employment promises.
  visual_style: Clean instructional lighting, instructor and learner reactions, whiteboard diagrams, slide callouts, progress bars, worksheet close-ups, and practical demo inserts.
  storyboard_logic: pain point -> learning outcome -> framework visual -> guided case demo -> practice takeaway -> course or action path.
  content_structure: One learning objective per segment, plain terms, example first then principle, concise recap and next step; avoid hard sell.
  scene_design: Classrooms, online course desks, office training scenes, virtual studios, whiteboard walls, screen-recording style panels, or realistic learner contexts.
  audio_design: Calm authoritative narration, low-distraction BGM, subtle section stingers, pen, keyboard, and click cues.
examples:
  - input: Create a promo video for an online Python course
    output: Load the adult education theme and organize around learning pain points, course structure, case demonstrations, and enrollment action.
---

# Adult Education and Training - Theme Skill

## When to Use

Load this skill when the user asks for adult education, courses, learning, vocational training, online courses, public classes, or teaching promotion.

## Process

### Step 1: Preserve Workflow
Only enhance generation quality. Do not change media review, approval, permissions, tool contracts, output policy, or explicit user instructions. Certificates, employment rates, exam pass rates, and institutional credentials must be confirmed by the user or a source.

### Step 2: Apply Optimization Guide
Inject the front matter `optimization_guide` into the creative brief, copywriting, styleframe, storyboard, scene design, and audio plan. Convert abstract style words into visible subjects, materials, actions, camera language, scene anchors, and audio cues, so the selected theme is legible without relying on the title or caption.

### Step 3: Theme Consistency Check
Before generation, check that the theme is visible in the subject, action/storyboard, scene, and audio plan. Conflicts with user instructions or safety requirements must be resolved in the review artifact before execution.

## Generation Detail Expansion

In the generation plan, storyboard, or final `expanded_generation_prompt`, add details around the "Adult Education and Training" theme. These details only improve generation quality and do not change the main process, review, approval, permissions, tool contracts, or explicit user instructions.

### Prompt Expansion Checklist
- Subject: specify identity, appearance, materials, start/end action states, and relationship to props, environment, or other subjects; choose details that are native to the matched theme.
- Theme reinforcement: Clarify the learning outcome, learner profile, pain point, before-after competence, case demonstration, practice step, and next action; avoid false certificate or employment promises.
- Cinematography: specify shot size, angle, camera movement, focus changes, foreground/midground/background layering, lighting, and transition context for each shot.
- Negative constraints: prevent drift such as unrelated styles, garbled text, watermarks, incorrect brand rendering, factual exaggeration, or scenes that conflict with the theme.

### Visual And Storyboard Expansion
- Visual details: Clean instructional lighting, instructor and learner reactions, whiteboard diagrams, slide callouts, progress bars, worksheet close-ups, and practical demo inserts.
- Storyboard rhythm: pain point -> learning outcome -> framework visual -> guided case demo -> practice takeaway -> course or action path.
- Content structure: One learning objective per segment, plain terms, example first then principle, concise recap and next step; avoid hard sell.
- Scene design: Classrooms, online course desks, office training scenes, virtual studios, whiteboard walls, screen-recording style panels, or realistic learner contexts.
- Audio planning: Calm authoritative narration, low-distraction BGM, subtle section stingers, pen, keyboard, and click cues.

### Final Prompt Influence
- Each final prompt that matches this theme should include at least four explicit anchors: a theme-signature visual marker, an action/storyboard beat, a scene/material anchor, and a camera/lighting or audio cue.
- When multiple themes match, preserve the user's explicit theme first, then merge compatible elements; explain conflicting choices in `storyboard_review` or `media_plan_review`.
- Recommended `theme_consistency_score` is at least 0.8; if below threshold, revise the prompt, storyboard, scene, or audio plan before generation. Do not bypass `media-review-gate`.

## Common Pitfalls

- Vague theme labels without concrete theme-signature visual, action, scene, camera, material, and audio anchors.
- Unsupported factual claims. Certificates, employment rates, exam pass rates, and institutional credentials must be confirmed by the user or a source.
- Overloaded shots that ask one short clip to communicate too many actions or messages.
