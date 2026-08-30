---
skill_id: theme_festival_celebration
name: Festival and Celebration
description: Generation quality enhancement skill for festivals, celebrations, galas, blessings, event openings, annual meetings, or anniversaries; strengthens prompt detail, visual style, storyboard logic, content structure, scene design, and audio planning while preserving the main workflow.
trigger_keywords: [festival, celebration, gala, blessing, event]
match_rule:
  type: keyword_semantic_hybrid
  threshold: 0.8
  keyword_combinations:
    - [festival, blessing]
    - [event, opening]
    - [gala, celebration]
  semantic_terms: [fireworks, lantern, gift, stage, reunion, cheer, countdown, confetti]
optimization_guide:
  prompt_enhancement: Add signature festival symbols, decorations, lanterns, fireworks, stage lights, ritual action, greetings, group emotion, and a climactic blessing.
  visual_style: Warm gold, red, or bright accents, luminous decorations, confetti, crowd and stage depth, sparkle, and ceremonial props.
  storyboard_logic: environment reveal -> ritual or preparation -> crowd and emotional interaction -> peak celebration -> blessing or brand close.
  content_structure: Short warm wishes tied to the exact event; avoid a generic holiday collage when a specific festival is named.
  scene_design: Decorated streets, homes, banquet halls, stages, temples, fairs, city square countdowns, venues, or brand event sites.
  audio_design: Regional or festival music, applause, cheers, countdowns, fireworks, drums, and confetti pops.
examples:
  - input: Generate a Spring Festival blessing gala opener
    output: Load the festival celebration theme and use lanterns, fireworks, stage lights, reunion shots, and a blessing close.
---

# Festival and Celebration - Theme Skill

## When to Use

Load this skill when the user asks for festivals, celebrations, galas, blessings, event openings, annual meetings, or anniversaries.

## Process

### Step 1: Preserve Workflow
Only enhance generation quality. Do not change media review, approval, permissions, tool contracts, output policy, or explicit user instructions. Real event names, dates, people, and brand information need user input or research confirmation.

### Step 2: Apply Optimization Guide
Inject the front matter `optimization_guide` into the creative brief, copywriting, styleframe, storyboard, scene design, and audio plan. Convert abstract style words into visible subjects, materials, actions, camera language, scene anchors, and audio cues, so the selected theme is legible without relying on the title or caption.

### Step 3: Theme Consistency Check
Before generation, check that the theme is visible in the subject, action/storyboard, scene, and audio plan. Conflicts with user instructions or safety requirements must be resolved in the review artifact before execution.

## Generation Detail Expansion

In the generation plan, storyboard, or final `expanded_generation_prompt`, add details around the "Festival and Celebration" theme. These details only improve generation quality and do not change the main process, review, approval, permissions, tool contracts, or explicit user instructions.

### Prompt Expansion Checklist
- Subject: specify identity, appearance, materials, start/end action states, and relationship to props, environment, or other subjects; choose details that are native to the matched theme.
- Theme reinforcement: Add signature festival symbols, decorations, lanterns, fireworks, stage lights, ritual action, greetings, group emotion, and a climactic blessing.
- Cinematography: specify shot size, angle, camera movement, focus changes, foreground/midground/background layering, lighting, and transition context for each shot.
- Negative constraints: prevent drift such as unrelated styles, garbled text, watermarks, incorrect brand rendering, factual exaggeration, or scenes that conflict with the theme.

### Visual And Storyboard Expansion
- Visual details: Warm gold, red, or bright accents, luminous decorations, confetti, crowd and stage depth, sparkle, and ceremonial props.
- Storyboard rhythm: environment reveal -> ritual or preparation -> crowd and emotional interaction -> peak celebration -> blessing or brand close.
- Content structure: Short warm wishes tied to the exact event; avoid a generic holiday collage when a specific festival is named.
- Scene design: Decorated streets, homes, banquet halls, stages, temples, fairs, city square countdowns, venues, or brand event sites.
- Audio planning: Regional or festival music, applause, cheers, countdowns, fireworks, drums, and confetti pops.

### Final Prompt Influence
- Each final prompt that matches this theme should include at least four explicit anchors: a theme-signature visual marker, an action/storyboard beat, a scene/material anchor, and a camera/lighting or audio cue.
- When multiple themes match, preserve the user's explicit theme first, then merge compatible elements; explain conflicting choices in `storyboard_review` or `media_plan_review`.
- Recommended `theme_consistency_score` is at least 0.8; if below threshold, revise the prompt, storyboard, scene, or audio plan before generation. Do not bypass `media-review-gate`.

## Common Pitfalls

- Vague theme labels without concrete theme-signature visual, action, scene, camera, material, and audio anchors.
- Unsupported factual claims. Real event names, dates, people, and brand information need user input or research confirmation.
- Overloaded shots that ask one short clip to communicate too many actions or messages.
