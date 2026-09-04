---
skill_id: theme_product_advertising
name: Product Advertising
description: Generation quality enhancement skill for product ads, product promotion, commerce videos, advertising films, and conversion-oriented marketing videos; strengthens prompt detail, visual style, storyboard logic, content structure, scene design, and audio planning while preserving the main workflow.
trigger_keywords: [product ad, product promotion, commerce video, advertisement, marketing video, 商品广告, 产品广告, 广告视频, 推广, 宣传]
match_rule:
  type: keyword_semantic_hybrid
  threshold: 0.8
  keyword_combinations:
    - [product, promotion]
    - [product, advertisement]
    - [brand, marketing]
  semantic_terms: [selling point, purchase, order, discount, conversion, recommendation, word of mouth, promotion]
optimization_guide:
  prompt_enhancement: Highlight hero product identity, the single strongest benefit, material or function close-up, use scenario, proof cue, brand tone, and clear CTA; do not invent unsupported efficacy, specifications, or certifications.
  visual_style: Packshot and hero close-ups, tactile material detail, macro feature demo, supported before-after contrast, hand or use interaction, packaging, and brand-color lighting.
  storyboard_logic: thumb-stopping visual hook -> problem or use case -> feature proof -> benefit in action -> trust cue -> CTA.
  content_structure: One benefit per shot, short conversion copy, exact product name only if provided, and a clear but not pushy CTA（行动号召）.
  scene_design: Tabletop studio, lifestyle use, lab or proof setup, unboxing, retail/package display, or customer scenario based on product type.
  audio_design: Bright branded BGM, product handling clicks, swipes, pours or opening sounds, and emphasis stingers on claims or CTA.
examples:
  - input: Generate a commerce ad video for a skincare product
    output: Load the product advertising theme and organize shots by pain point, texture close-up, application, effect impression, and CTA.
---

# Product Advertising - Theme Skill

## When to Use

Load this skill when the user asks for product ads, product promotion, commerce videos, advertising films, and conversion-oriented marketing videos.

## Process

### Step 1: Preserve Workflow
Only enhance generation quality. Do not change media review, approval, permissions, tool contracts, output policy, or explicit user instructions. Unsupported product efficacy, certifications, prices, warranties, sales volume, and competitor claims must be marked as assumptions or removed.

### Step 2: Apply Optimization Guide
Inject the front matter `optimization_guide` into the creative brief, copywriting, styleframe, storyboard, scene design, and audio plan. Convert abstract style words into visible subjects, materials, actions, camera language, scene anchors, and audio cues, so the selected theme is legible without relying on the title or caption.

### Step 3: Theme Consistency Check
Before generation, check that the theme is visible in the subject, action/storyboard, scene, and audio plan. Conflicts with user instructions or safety requirements must be resolved in the review artifact before execution.

## Generation Detail Expansion

In the generation plan, storyboard, or final `expanded_generation_prompt`, add details around the "Product Advertising" theme. These details only improve generation quality and do not change the main process, review, approval, permissions, tool contracts, or explicit user instructions.

### Prompt Expansion Checklist
- Subject: specify identity, appearance, materials, start/end action states, and relationship to props, environment, or other subjects; choose details that are native to the matched theme.
- Theme reinforcement: Highlight hero product identity, the single strongest benefit, material or function close-up, use scenario, proof cue, brand tone, and clear CTA; do not invent unsupported efficacy, specifications, or certifications.
- Cinematography: specify shot size, angle, camera movement, focus changes, foreground/midground/background layering, lighting, and transition context for each shot.
- Negative constraints: prevent drift such as unrelated styles, garbled text, watermarks, incorrect brand rendering, factual exaggeration, or scenes that conflict with the theme.

### Visual And Storyboard Expansion
- Visual details: Packshot and hero close-ups, tactile material detail, macro feature demo, supported before-after contrast, hand or use interaction, packaging, and brand-color lighting.
- Storyboard rhythm: thumb-stopping visual hook -> problem or use case -> feature proof -> benefit in action -> trust cue -> CTA.
- Content structure: One benefit per shot, short conversion copy, exact product name only if provided, and a clear but not pushy CTA.
- Scene design: Tabletop studio, lifestyle use, lab or proof setup, unboxing, retail/package display, or customer scenario based on product type.
- Audio planning: Bright branded BGM, product handling clicks, swipes, pours or opening sounds, and emphasis stingers on claims or CTA.

### Final Prompt Influence
- Each final prompt that matches this theme should include at least four explicit anchors: a theme-signature visual marker, an action/storyboard beat, a scene/material anchor, and a camera/lighting or audio cue.
- When multiple themes match, preserve the user's explicit theme first, then merge compatible elements; explain conflicting choices in `storyboard_review` or `media_plan_review`.
- Recommended `theme_consistency_score` is at least 0.8; if below threshold, revise the prompt, storyboard, scene, or audio plan before generation. Do not bypass `media-review-gate`.

## Common Pitfalls

- Vague theme labels without concrete theme-signature visual, action, scene, camera, material, and audio anchors.
- Unsupported factual claims. Unsupported product efficacy, certifications, prices, warranties, sales volume, and competitor claims must be marked as assumptions or removed.
- Overloaded shots that ask one short clip to communicate too many actions or messages.
