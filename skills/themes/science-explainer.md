---
skill_id: theme_science_explainer
name: Science Explainer
description: Generation quality enhancement skill for science, explanation, knowledge, principles, tutorials, course clips, or explanatory content; strengthens prompt detail, visual style, storyboard logic, content structure, scene design, and audio planning while preserving the main workflow.
trigger_keywords: [science explainer, explanation, knowledge, principle, tutorial]
match_rule:
  type: keyword_semantic_hybrid
  threshold: 0.8
  keyword_combinations:
    - [knowledge, explanation]
    - [principle, animation]
    - [tutorial, steps]
  semantic_terms: [chart, annotation, experiment, formula, from basics to advanced, example, summary, voiceover]
optimization_guide:
  prompt_enhancement: Use accurate terms, definitions, visible cause-effect chains, analogies, experiment or demo moments, key variables, and source limitations.
  visual_style: Diagrams, arrows, labels, animated layers, magnified process views, demo props, and highlighted variables.
  storyboard_logic: question hook -> concept definition -> mechanism breakdown -> example or test -> misconception correction -> summary.
  content_structure: One concept per beat, defined jargon, analogy tied back to the real mechanism, and no overclaiming.
  scene_design: Labs, classrooms, whiteboards, virtual 3D model spaces, field demos, or infographic environments.
  audio_design: Clear explanatory narration, soft study BGM, and subtle transition beeps or clicks for key points.
examples:
  - input: Create a science explainer video about black holes
    output: Load the science explainer theme and plan by question, concept, diagram, example, and summary.
---

# Science Explainer - Theme Skill

## When to Use

Load this skill when the user asks for science, explanation, knowledge, principles, tutorials, course clips, or explanatory content.

## Process

### Step 1: Preserve Workflow
Only enhance generation quality. Do not change media review, approval, permissions, tool contracts, output policy, or explicit user instructions. Factual, medical, legal, financial, and current-events topics still need research sources recorded through the media review gate.

### Step 2: Apply Optimization Guide
Inject the front matter `optimization_guide` into the creative brief, copywriting, styleframe, storyboard, scene design, and audio plan. Convert abstract style words into visible subjects, materials, actions, camera language, scene anchors, and audio cues, so the selected theme is legible without relying on the title or caption.

### Step 3: Theme Consistency Check
Before generation, check that the theme is visible in the subject, action/storyboard, scene, and audio plan. Conflicts with user instructions or safety requirements must be resolved in the review artifact before execution.

## Generation Detail Expansion

In the generation plan, storyboard, or final `expanded_generation_prompt`, add details around the "Science Explainer" theme. These details only improve generation quality and do not change the main process, review, approval, permissions, tool contracts, or explicit user instructions.

### Prompt Expansion Checklist
- Subject: specify identity, appearance, materials, start/end action states, and relationship to props, environment, or other subjects; choose details that are native to the matched theme.
- Theme reinforcement: Use accurate terms, definitions, visible cause-effect chains, analogies, experiment or demo moments, key variables, and source limitations.
- Cinematography: specify shot size, angle, camera movement, focus changes, foreground/midground/background layering, lighting, and transition context for each shot.
- Negative constraints: prevent drift such as unrelated styles, garbled text, watermarks, incorrect brand rendering, factual exaggeration, or scenes that conflict with the theme.

### Visual And Storyboard Expansion
- Visual details: Diagrams, arrows, labels, animated layers, magnified process views, demo props, and highlighted variables.
- Storyboard rhythm: question hook -> concept definition -> mechanism breakdown -> example or test -> misconception correction -> summary.
- Content structure: One concept per beat, defined jargon, analogy tied back to the real mechanism, and no overclaiming.
- Scene design: Labs, classrooms, whiteboards, virtual 3D model spaces, field demos, or infographic environments.
- Audio planning: Clear explanatory narration, soft study BGM, and subtle transition beeps or clicks for key points.

### Final Prompt Influence
- Each final prompt that matches this theme should include at least four explicit anchors: a theme-signature visual marker, an action/storyboard beat, a scene/material anchor, and a camera/lighting or audio cue.
- When multiple themes match, preserve the user's explicit theme first, then merge compatible elements; explain conflicting choices in `storyboard_review` or `media_plan_review`.
- Recommended `theme_consistency_score` is at least 0.8; if below threshold, revise the prompt, storyboard, scene, or audio plan before generation. Do not bypass `media-review-gate`.

## Common Pitfalls

- Vague theme labels without concrete theme-signature visual, action, scene, camera, material, and audio anchors.
- Unsupported factual claims. Factual, medical, legal, financial, and current-events topics still need research sources recorded through the media review gate.
- Overloaded shots that ask one short clip to communicate too many actions or messages.
