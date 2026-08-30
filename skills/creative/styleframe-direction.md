# Styleframe Direction - Creative Skill

## When to Use

Use this skill when defining visual direction before generation.

## Role

This skill shapes creative planning quality. It does not authorize media generation, mutation, provider calls, or source overwrites. For any media-producing or media-mutating step, the media review gate still requires a concrete plan, validation artifact, review artifact, explicit approval, exact execution, output validation, and delivery reporting.

## Guidance

Define style tokens, color palette, lighting, composition, texture, reference treatment, negative style constraints, and low-cost keyframe confirmation when appropriate. Styleframes are planning artifacts until approved.

## Required Outputs When Applicable

- Clear assumptions and constraints.
- Per-shot or per-asset decisions when the task has multiple beats.
- References, source paths, and preservation rules when relevant.
- Negative constraints to prevent style drift, factual overclaiming, unreadable text, watermarks, unsafe content, or duplicated shots.
- A validation checklist that can be copied into `storyboard_validation.json`, `media_plan_validation.json`, `edit_proposal_review.json`, or the active pipeline checkpoint.

## Review Questions

- Does the artifact preserve the user's explicit request and constraints?
- Are missing details represented as assumptions or clarification needs instead of silent guesses?
- Is every shot/action/material/time allocation justified by the objective?
- Are factual, branded, current, medical, legal, financial, or reference-sensitive claims sourced or bounded?
- Can the next stage execute without changing approved prompt text, timing, references, or parameters?

## Common Pitfalls

- Treating creative planning as approval to call a media tool.
- Replacing the user's objective with a new concept.
- Overloading one short shot with too many actions or messages.
- Letting generated text carry critical readable copy instead of using captions or Remotion packaging.
- Failing to record limitations, missing assets, or uncertainty.
