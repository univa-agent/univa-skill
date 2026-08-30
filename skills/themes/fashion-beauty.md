---
skill_id: theme_fashion_beauty
name: Fashion and Beauty
description: Generation quality enhancement skill for fashion, beauty, outfit styling, skincare, makeup, hair, or runway-like content; strengthens prompt detail, visual style, storyboard logic, content structure, scene design, and audio planning while preserving the main workflow.
trigger_keywords: [fashion, beauty, outfit, skincare, makeup]
match_rule:
  type: keyword_semantic_hybrid
  threshold: 0.8
  keyword_combinations:
    - [outfit, fashion]
    - [makeup, tutorial]
    - [skincare, product]
  semantic_terms: [lipstick, eyeshadow, foundation, fabric, runway, high-key lighting, texture, color matching]
optimization_guide:
  prompt_enhancement: Highlight fabric, finish, color coordination, skin or hair texture, application or styling steps, look transformation, trend context, and wearable scenario.
  visual_style: Flattering high-key or runway lighting, macro texture shots, clean backgrounds, mirrors, skin, lip, and eye close-ups, and full outfit movement.
  storyboard_logic: mood or look reveal -> material or application detail -> styling motion -> comparison -> final confident pose.
  content_structure: Tasteful concise copy focused on shade, material, fit, finish, and occasion; avoid unrealistic body or medical claims.
  scene_design: Vanities, dressing rooms, runways, editorial studios, city streets, wardrobe rails, or bathroom skincare setups.
  audio_design: Rhythmic fashion beat, brush, cap, spray, and fabric-rustle sounds, camera shutter cues, and light transition hits.
examples:
  - input: Generate an autumn outfit and beauty video
    output: Load the fashion and beauty theme and focus on color matching, fabric texture, makeup details, and full-look reveal.
---

# Fashion and Beauty - Theme Skill

## When to Use

Load this skill when the user asks for fashion, beauty, outfit styling, skincare, makeup, hair, or runway-like content.

## Process

### Step 1: Preserve Workflow
Only enhance generation quality. Do not change media review, approval, permissions, tool contracts, output policy, or explicit user instructions. Skincare and cosmeceutical claims must not be exaggerated without evidence.

### Step 2: Apply Optimization Guide
Inject the front matter `optimization_guide` into the creative brief, copywriting, styleframe, storyboard, scene design, and audio plan. Convert abstract style words into visible subjects, materials, actions, camera language, scene anchors, and audio cues, so the selected theme is legible without relying on the title or caption.

### Step 3: Theme Consistency Check
Before generation, check that the theme is visible in the subject, action/storyboard, scene, and audio plan. Conflicts with user instructions or safety requirements must be resolved in the review artifact before execution.

## Generation Detail Expansion

In the generation plan, storyboard, or final `expanded_generation_prompt`, add details around the "Fashion and Beauty" theme. These details only improve generation quality and do not change the main process, review, approval, permissions, tool contracts, or explicit user instructions.

### Prompt Expansion Checklist
- Subject: specify identity, appearance, materials, start/end action states, and relationship to props, environment, or other subjects; choose details that are native to the matched theme.
- Theme reinforcement: Highlight fabric, finish, color coordination, skin or hair texture, application or styling steps, look transformation, trend context, and wearable scenario.
- Cinematography: specify shot size, angle, camera movement, focus changes, foreground/midground/background layering, lighting, and transition context for each shot.
- Negative constraints: prevent drift such as unrelated styles, garbled text, watermarks, incorrect brand rendering, factual exaggeration, or scenes that conflict with the theme.

### Visual And Storyboard Expansion
- Visual details: Flattering high-key or runway lighting, macro texture shots, clean backgrounds, mirrors, skin, lip, and eye close-ups, and full outfit movement.
- Storyboard rhythm: mood or look reveal -> material or application detail -> styling motion -> comparison -> final confident pose.
- Content structure: Tasteful concise copy focused on shade, material, fit, finish, and occasion; avoid unrealistic body or medical claims.
- Scene design: Vanities, dressing rooms, runways, editorial studios, city streets, wardrobe rails, or bathroom skincare setups.
- Audio planning: Rhythmic fashion beat, brush, cap, spray, and fabric-rustle sounds, camera shutter cues, and light transition hits.

### Final Prompt Influence
- Each final prompt that matches this theme should include at least four explicit anchors: a theme-signature visual marker, an action/storyboard beat, a scene/material anchor, and a camera/lighting or audio cue.
- When multiple themes match, preserve the user's explicit theme first, then merge compatible elements; explain conflicting choices in `storyboard_review` or `media_plan_review`.
- Recommended `theme_consistency_score` is at least 0.8; if below threshold, revise the prompt, storyboard, scene, or audio plan before generation. Do not bypass `media-review-gate`.

## Common Pitfalls

- Vague theme labels without concrete theme-signature visual, action, scene, camera, material, and audio anchors.
- Unsupported factual claims. Skincare and cosmeceutical claims must not be exaggerated without evidence.
- Overloaded shots that ask one short clip to communicate too many actions or messages.
