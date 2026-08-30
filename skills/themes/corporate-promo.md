---
skill_id: theme_corporate_promo
name: Corporate Promotion
description: Generation quality enhancement skill for corporate, brand, promo films, company profiles, culture showcases, investment promotion, or team stories; strengthens prompt detail, visual style, storyboard logic, content structure, scene design, and audio planning while preserving the main workflow.
trigger_keywords: [corporate, brand, promo film, company profile, culture]
match_rule:
  type: keyword_semantic_hybrid
  threshold: 0.8
  keyword_combinations:
    - [company, profile]
    - [corporate, promotion]
    - [brand, culture]
  semantic_terms: [mission, vision, team, office, factory, achievement, milestone, partnership]
optimization_guide:
  prompt_enhancement: Highlight mission through concrete operations, team collaboration, product capability, customer proof, scale, innovation, and credible achievements; real data needs sources.
  visual_style: Steady premium camera language, clean offices, factories, labs, real workflows, team close-ups, product or service demos, and city exteriors.
  storyboard_logic: challenge or context -> capability proof -> people and process -> customer scenario -> sourced achievement -> future vision.
  content_structure: Specific business nouns and outcomes, restrained confident tone, and no empty slogan stacking or unsupported rankings.
  scene_design: Offices, factory lines, conference rooms, laboratories, customer sites, logistics scenes, city skylines, or reception areas.
  audio_design: Cinematic corporate BGM, workplace ambience, subtle transition whooshes, and steady narration.
examples:
  - input: Create a company profile promo film
    output: Load the corporate promotion theme and organize around mission, team, business, achievements, and future vision.
---

# Corporate Promotion - Theme Skill

## When to Use

Load this skill when the user asks for corporate, brand, promo films, company profiles, culture showcases, investment promotion, or team stories.

## Process

### Step 1: Preserve Workflow
Only enhance generation quality. Do not change media review, approval, permissions, tool contracts, output policy, or explicit user instructions. Company data, awards, customer names, and credentials must come from the user or sources.

### Step 2: Apply Optimization Guide
Inject the front matter `optimization_guide` into the creative brief, copywriting, styleframe, storyboard, scene design, and audio plan. Convert abstract style words into visible subjects, materials, actions, camera language, scene anchors, and audio cues, so the selected theme is legible without relying on the title or caption.

### Step 3: Theme Consistency Check
Before generation, check that the theme is visible in the subject, action/storyboard, scene, and audio plan. Conflicts with user instructions or safety requirements must be resolved in the review artifact before execution.

## Generation Detail Expansion

In the generation plan, storyboard, or final `expanded_generation_prompt`, add details around the "Corporate Promotion" theme. These details only improve generation quality and do not change the main process, review, approval, permissions, tool contracts, or explicit user instructions.

### Prompt Expansion Checklist
- Subject: specify identity, appearance, materials, start/end action states, and relationship to props, environment, or other subjects; choose details that are native to the matched theme.
- Theme reinforcement: Highlight mission through concrete operations, team collaboration, product capability, customer proof, scale, innovation, and credible achievements; real data needs sources.
- Cinematography: specify shot size, angle, camera movement, focus changes, foreground/midground/background layering, lighting, and transition context for each shot.
- Negative constraints: prevent drift such as unrelated styles, garbled text, watermarks, incorrect brand rendering, factual exaggeration, or scenes that conflict with the theme.

### Visual And Storyboard Expansion
- Visual details: Steady premium camera language, clean offices, factories, labs, real workflows, team close-ups, product or service demos, and city exteriors.
- Storyboard rhythm: challenge or context -> capability proof -> people and process -> customer scenario -> sourced achievement -> future vision.
- Content structure: Specific business nouns and outcomes, restrained confident tone, and no empty slogan stacking or unsupported rankings.
- Scene design: Offices, factory lines, conference rooms, laboratories, customer sites, logistics scenes, city skylines, or reception areas.
- Audio planning: Cinematic corporate BGM, workplace ambience, subtle transition whooshes, and steady narration.

### Final Prompt Influence
- Each final prompt that matches this theme should include at least four explicit anchors: a theme-signature visual marker, an action/storyboard beat, a scene/material anchor, and a camera/lighting or audio cue.
- When multiple themes match, preserve the user's explicit theme first, then merge compatible elements; explain conflicting choices in `storyboard_review` or `media_plan_review`.
- Recommended `theme_consistency_score` is at least 0.8; if below threshold, revise the prompt, storyboard, scene, or audio plan before generation. Do not bypass `media-review-gate`.

## Common Pitfalls

- Vague theme labels without concrete theme-signature visual, action, scene, camera, material, and audio anchors.
- Unsupported factual claims. Company data, awards, customer names, and credentials must come from the user or sources.
- Overloaded shots that ask one short clip to communicate too many actions or messages.
