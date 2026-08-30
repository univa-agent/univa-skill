---
skill_id: theme_medical_health
name: Medical and Health
description: Generation quality enhancement skill for medical, health, wellness, disease, medicine, care, or medical science content; strengthens prompt detail, visual style, storyboard logic, content structure, scene design, and audio planning while preserving the main workflow.
trigger_keywords: [medical, health, wellness, disease, medicine]
match_rule:
  type: keyword_semantic_hybrid
  threshold: 0.8
  keyword_combinations:
    - [disease, prevention]
    - [medicine, instruction]
    - [health, explainer]
  semantic_terms: [doctor, hospital, symptom, human body model, care, examination, treatment, authoritative source]
optimization_guide:
  prompt_enhancement: Use careful accessible explanations, symptoms as general information, anatomy or chart visuals, prevention and care steps, source limits, and no diagnostic assertions.
  visual_style: Bright clinical style, calm colors, anatomical diagrams or models, clear labels, non-graphic imagery, and supportive human scenes.
  storyboard_logic: question or problem -> mechanism visual -> safe options or prevention -> warning signs -> consult-professional reminder.
  content_structure: Evidence-bounded and non-personalized guidance, clear definitions, stated limits, and no miracle cures or fear tactics.
  scene_design: Clinics, hospital corridors, doctor offices, home care scenes, healthy lifestyle settings, or virtual medical studios.
  audio_design: Soft reassuring BGM, clear measured narration, and gentle cues for key cautions.
examples:
  - input: Create a health explainer video about hypertension
    output: Load the medical health theme, record authoritative sources first, then organize by problem, cause, advice, and doctor-consult reminder.
---

# Medical and Health - Theme Skill

## When to Use

Load this skill when the user asks for medical, health, wellness, disease, medicine, care, or medical science content.

## Process

### Step 1: Preserve Workflow
Only enhance generation quality. Do not change media review, approval, permissions, tool contracts, output policy, or explicit user instructions. Do not bypass medical safety review, generate individual diagnosis, or promise treatment outcomes.

### Step 2: Apply Optimization Guide
Inject the front matter `optimization_guide` into the creative brief, copywriting, styleframe, storyboard, scene design, and audio plan. Convert abstract style words into visible subjects, materials, actions, camera language, scene anchors, and audio cues, so the selected theme is legible without relying on the title or caption.

### Step 3: Theme Consistency Check
Before generation, check that the theme is visible in the subject, action/storyboard, scene, and audio plan. Conflicts with user instructions or safety requirements must be resolved in the review artifact before execution.

## Generation Detail Expansion

In the generation plan, storyboard, or final `expanded_generation_prompt`, add details around the "Medical and Health" theme. These details only improve generation quality and do not change the main process, review, approval, permissions, tool contracts, or explicit user instructions.

### Prompt Expansion Checklist
- Subject: specify identity, appearance, materials, start/end action states, and relationship to props, environment, or other subjects; choose details that are native to the matched theme.
- Theme reinforcement: Use careful accessible explanations, symptoms as general information, anatomy or chart visuals, prevention and care steps, source limits, and no diagnostic assertions.
- Cinematography: specify shot size, angle, camera movement, focus changes, foreground/midground/background layering, lighting, and transition context for each shot.
- Negative constraints: prevent drift such as unrelated styles, garbled text, watermarks, incorrect brand rendering, factual exaggeration, or scenes that conflict with the theme.

### Visual And Storyboard Expansion
- Visual details: Bright clinical style, calm colors, anatomical diagrams or models, clear labels, non-graphic imagery, and supportive human scenes.
- Storyboard rhythm: question or problem -> mechanism visual -> safe options or prevention -> warning signs -> consult-professional reminder.
- Content structure: Evidence-bounded and non-personalized guidance, clear definitions, stated limits, and no miracle cures or fear tactics.
- Scene design: Clinics, hospital corridors, doctor offices, home care scenes, healthy lifestyle settings, or virtual medical studios.
- Audio planning: Soft reassuring BGM, clear measured narration, and gentle cues for key cautions.

### Final Prompt Influence
- Each final prompt that matches this theme should include at least four explicit anchors: a theme-signature visual marker, an action/storyboard beat, a scene/material anchor, and a camera/lighting or audio cue.
- When multiple themes match, preserve the user's explicit theme first, then merge compatible elements; explain conflicting choices in `storyboard_review` or `media_plan_review`.
- Recommended `theme_consistency_score` is at least 0.8; if below threshold, revise the prompt, storyboard, scene, or audio plan before generation. Do not bypass `media-review-gate`.

## Common Pitfalls

- Vague theme labels without concrete theme-signature visual, action, scene, camera, material, and audio anchors.
- Unsupported factual claims. Do not bypass medical safety review, generate individual diagnosis, or promise treatment outcomes.
- Overloaded shots that ask one short clip to communicate too many actions or messages.
