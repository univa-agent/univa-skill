# Intent Decomposer - Meta Skill

## When to Use

Use this skill when UniVA breaks compound user requests into ordered sub-intents.

## Responsibilities

Separate generate, edit, understand, preference, and chat parts. Each expensive or mutating media subtask needs its own approval state unless a parent approval explicitly covers it.

## Invariants

- All user-facing output must be English.
- Media generation and media mutation must pass through `skills/meta/media-review-gate.md` unless the task is read-only planning or understanding.
- Tool signatures and return fields come from the relevant `skills/core/*.md` Tool Contract.
- User preferences may guide style and defaults, but they must not override safety, approval, explicit user instructions, tool contracts, or factual constraints.
- Preserve generated artifacts under `data/`, `results/`, or `univa/results/` and verify real files before delivery.

## Process

1. Classify the request and load required skills.
2. Identify missing inputs, assumptions, source assets, preferences, and output policy.
3. Produce the proper plan, proposal, checkpoint, or direct chat response.
4. For gated work, write validation/review artifacts and stop at `awaiting_human`.
5. Resume only with explicit approval or user input that matches the current checkpoint.
6. Format final output in concise English with artifact paths and failure details when relevant.

## Common Pitfalls

- Showing raw backend JSON to end users.
- Treating the original request as approval for an unseen plan.
- Hiding missing research, missing assets, or unsupported tool requirements.
- Applying stored preferences against explicit user instructions.
- Reporting generated media before checking files on disk.
