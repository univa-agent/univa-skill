---
skill_id: theme_finance_business
name: Finance and Business
description: Generation quality enhancement skill for finance, business, investment, wealth management, market commentary, or earnings reports; strengthens prompt detail, visual style, storyboard logic, content structure, scene design, and audio planning while preserving the main workflow.
trigger_keywords: [finance, business, investment, wealth management, market analysis]
match_rule:
  type: keyword_semantic_hybrid
  threshold: 0.8
  keyword_combinations:
    - [finance, commentary]
    - [investment, analysis]
    - [wealth management, explainer]
  semantic_terms: [stock market, fund, interest rate, inflation, earnings report, risk, return, chart]
optimization_guide:
  prompt_enhancement: Emphasize data source cues, chart timeframe, trend logic, risk boundary, neutral visual metaphors, clear charts, and non-investment-advice framing.
  visual_style: Clean charts, ticker and data cards, host desk, market footage, restrained palette, readable numbers, and visible risk labels.
  storyboard_logic: question or market context -> data snapshot -> driver breakdown -> scenario and risk -> prudent takeaway.
  content_structure: Objective evidence-linked language that separates facts from interpretation; avoid return promises, urgency bait, and inflammatory trading advice.
  scene_design: Finance studios, analyst desks, trading screens, business meetings, chart walls, or data visualization spaces.
  audio_design: Steady low-key BGM, clear narration, subtle chart ticks, and notification cues for data transitions.
examples:
  - input: Generate a finance commentary video about interest-rate changes
    output: Load the finance theme, research data sources first, then organize around context, charts, causes, risks, and summary.
---

# Finance and Business - Theme Skill

## When to Use

Load this skill when the user asks for finance, business, investment, wealth management, market commentary, or earnings reports.

## Process

### Step 1: Preserve Workflow
Only enhance generation quality. Do not change media review, approval, permissions, tool contracts, output policy, or explicit user instructions. Prices, market data, policies, and company information must be currently verified.

### Step 2: Apply Optimization Guide
Inject the front matter `optimization_guide` into the creative brief, copywriting, styleframe, storyboard, scene design, and audio plan. Convert abstract style words into visible subjects, materials, actions, camera language, scene anchors, and audio cues, so the selected theme is legible without relying on the title or caption.

### Step 3: Theme Consistency Check
Before generation, check that the theme is visible in the subject, action/storyboard, scene, and audio plan. Conflicts with user instructions or safety requirements must be resolved in the review artifact before execution.

## Generation Detail Expansion

In the generation plan, storyboard, or final `expanded_generation_prompt`, add details around the "Finance and Business" theme. These details only improve generation quality and do not change the main process, review, approval, permissions, tool contracts, or explicit user instructions.

### Prompt Expansion Checklist
- Subject: specify identity, appearance, materials, start/end action states, and relationship to props, environment, or other subjects; choose details that are native to the matched theme.
- Theme reinforcement: Emphasize data source cues, chart timeframe, trend logic, risk boundary, neutral visual metaphors, clear charts, and non-investment-advice framing.
- Cinematography: specify shot size, angle, camera movement, focus changes, foreground/midground/background layering, lighting, and transition context for each shot.
- Negative constraints: prevent drift such as unrelated styles, garbled text, watermarks, incorrect brand rendering, factual exaggeration, or scenes that conflict with the theme.

### Visual And Storyboard Expansion
- Visual details: Clean charts, ticker and data cards, host desk, market footage, restrained palette, readable numbers, and visible risk labels.
- Storyboard rhythm: question or market context -> data snapshot -> driver breakdown -> scenario and risk -> prudent takeaway.
- Content structure: Objective evidence-linked language that separates facts from interpretation; avoid return promises, urgency bait, and inflammatory trading advice.
- Scene design: Finance studios, analyst desks, trading screens, business meetings, chart walls, or data visualization spaces.
- Audio planning: Steady low-key BGM, clear narration, subtle chart ticks, and notification cues for data transitions.

### Final Prompt Influence
- Each final prompt that matches this theme should include at least four explicit anchors: a theme-signature visual marker, an action/storyboard beat, a scene/material anchor, and a camera/lighting or audio cue.
- When multiple themes match, preserve the user's explicit theme first, then merge compatible elements; explain conflicting choices in `storyboard_review` or `media_plan_review`.
- Recommended `theme_consistency_score` is at least 0.8; if below threshold, revise the prompt, storyboard, scene, or audio plan before generation. Do not bypass `media-review-gate`.

## Common Pitfalls

- Vague theme labels without concrete theme-signature visual, action, scene, camera, material, and audio anchors.
- Unsupported factual claims. Prices, market data, policies, and company information must be currently verified.
- Overloaded shots that ask one short clip to communicate too many actions or messages.
