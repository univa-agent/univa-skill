---
skill_id: theme_chinese_ink_guochao
name: Chinese Ink and Guochao
description: Generation quality enhancement skill for guochao, ink wash, Chinese style, ancient style, landscape painting, traditional culture visuals, or East Asian poetic mood; strengthens prompt detail, visual style, storyboard logic, content structure, scene design, and audio planning while preserving the main workflow.
trigger_keywords: [guochao, ink wash, Chinese style, ancient style, landscape painting, 国潮, 水墨, 中国风, 古风, 山水画]
match_rule:
  type: keyword_semantic_hybrid
  threshold: 0.8
  keyword_combinations:
    - [Chinese, style]
    - [ink wash, landscape]
    - [ancient style, mood]
  semantic_terms: [negative space, calligraphy, rice paper, blue-green landscape, pavilion, garden, guqin, traditional pattern]
optimization_guide:
  prompt_enhancement: Use ink-wash brush edges, rice-paper grain, negative space（留白）, layered ink gradients, calligraphy rhythm, traditional motifs, and poetic weather.
  visual_style: Monochrome ink layers, restrained cinnabar, jade, or gold accents, visible brush texture, misted depth, and scroll-like composition.
  storyboard_logic: empty frame or brush reveal -> slow push or pull -> motif appears -> mist or ink transition -> poetic hold.
  content_structure: Subtle and elegant imagery with concrete symbols such as pavilion, river, pine, crane, moon, or lantern; avoid stacking archaic terms.
  scene_design: Layered mountains and water, gardens, ancient eaves, bridges, pavilions, river mist, folding screens, or scroll spaces.
  audio_design: Guqin, flute, xiao motifs, bianzhong accents, brush-on-paper sounds, water, wind ambience, and restrained drums.
examples:
  - input: Generate a guochao ink-wash landscape promo short
    output: Load the Chinese ink theme and plan shots with negative space, layered ink tones, slow push-ins, and traditional instruments.
---

# Chinese Ink and Guochao - Theme Skill

## When to Use

Load this skill when the user asks for guochao, ink wash, Chinese style, ancient style, landscape painting, traditional culture visuals, or East Asian poetic mood.

## Process

### Step 1: Preserve Workflow
Only enhance generation quality. Do not change media review, approval, permissions, tool contracts, output policy, or explicit user instructions. For real history, intangible heritage, artifacts, or brand collaborations, record sources and uncertainty through the media review gate.

### Step 2: Apply Optimization Guide
Inject the front matter `optimization_guide` into the creative brief, copywriting, styleframe, storyboard, scene design, and audio plan. Convert abstract style words into visible subjects, materials, actions, camera language, scene anchors, and audio cues, so the selected theme is legible without relying on the title or caption.

### Step 3: Theme Consistency Check
Before generation, check that the theme is visible in the subject, action/storyboard, scene, and audio plan. Conflicts with user instructions or safety requirements must be resolved in the review artifact before execution.

## Generation Detail Expansion

In the generation plan, storyboard, or final `expanded_generation_prompt`, add details around the "Chinese Ink and Guochao" theme. These details only improve generation quality and do not change the main process, review, approval, permissions, tool contracts, or explicit user instructions.

### Prompt Expansion Checklist
- Subject: specify identity, appearance, materials, start/end action states, and relationship to props, environment, or other subjects; choose details that are native to the matched theme.
- Theme reinforcement: Use ink-wash brush edges, rice-paper grain, negative space, layered ink gradients, calligraphy rhythm, traditional motifs, and poetic weather.
- Cinematography: specify shot size, angle, camera movement, focus changes, foreground/midground/background layering, lighting, and transition context for each shot.
- Negative constraints: prevent drift such as unrelated styles, garbled text, watermarks, incorrect brand rendering, factual exaggeration, or scenes that conflict with the theme.

### Visual And Storyboard Expansion
- Visual details: Monochrome ink layers, restrained cinnabar, jade, or gold accents, visible brush texture, misted depth, and scroll-like composition.
- Storyboard rhythm: empty frame or brush reveal -> slow push or pull -> motif appears -> mist or ink transition -> poetic hold.
- Content structure: Subtle and elegant imagery with concrete symbols such as pavilion, river, pine, crane, moon, or lantern; avoid stacking archaic terms.
- Scene design: Layered mountains and water, gardens, ancient eaves, bridges, pavilions, river mist, folding screens, or scroll spaces.
- Audio planning: Guqin, flute, xiao motifs, bianzhong accents, brush-on-paper sounds, water, wind ambience, and restrained drums.

### Final Prompt Influence
- Each final prompt that matches this theme should include at least four explicit anchors: a theme-signature visual marker, an action/storyboard beat, a scene/material anchor, and a camera/lighting or audio cue.
- When multiple themes match, preserve the user's explicit theme first, then merge compatible elements; explain conflicting choices in `storyboard_review` or `media_plan_review`.
- Recommended `theme_consistency_score` is at least 0.8; if below threshold, revise the prompt, storyboard, scene, or audio plan before generation. Do not bypass `media-review-gate`.

## Common Pitfalls

- Vague theme labels without concrete theme-signature visual, action, scene, camera, material, and audio anchors.
- Unsupported factual claims. For real history, intangible heritage, artifacts, or brand collaborations, record sources and uncertainty through the media review gate.
- Overloaded shots that ask one short clip to communicate too many actions or messages.
