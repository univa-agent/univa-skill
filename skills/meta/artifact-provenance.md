# Artifact Provenance - Meta Skill

## When to Use

Use this skill when UniVA or an external agent records, resumes, audits, or
delivers versioned plans, approvals, media results, costs, and execution
receipts.

## Storage Modes

### Backend Pipeline

- Prefer the backend when the task needs durable pause/resume, authenticated
  ownership, multi-worker resume protection, or automatic stage artifacts.
- `PipelineOrchestrator` automatically writes canonical records through
  `PipelineStateStore` and `ArtifactStore`; an external agent must not edit the
  SQLite databases or JSON records directly.
- Keep the `session_id` and current `continuation_token` returned by the
  checkpoint. A token is single-use and rotates after every resume decision.
- Use `scripts/univa_agent_client.py pipeline-state` to inspect state and
  `scripts/univa_agent_client.py resume` to submit the current token.

### Direct External-Agent Execution

- Prefer repo runners or existing `univa.mcp_tools` functions for ordinary
  terminal-first work that does not need service sessions.
- Preserve domain artifacts such as plan, validation, review, decision, tool
  result, QA, and delivery report under `results/`.
- When canonical provenance is required, call `ArtifactStore.write_artifact`
  and `ArtifactStore.write_receipt`; do not insert into their SQLite tables.
- Link derived records with `parent_artifact_ids`. Record the exact approved
  plan hash, tool arguments, provider task ID, provider/model, output paths,
  file hashes, and actual cost when the provider returns it.
- Execution receipts are append-only. Generate a new operation ID for every
  attempt, including retries and failures; never reuse an operation ID.

## Approval Binding

- Approval applies to the displayed Artifact ID, version, and content hash.
- A revision creates a new Artifact version and invalidates approval of the
  prior version.
- Do not execute a mutating tool when the approved record is missing, stale,
  or does not match the request to be sent.

## Cost Rules

- Use provider-reported `actual_cost_usd` when available.
- Otherwise record the configured estimate and label it as estimated.
- Stage cost includes both LLM and tool cost. Never present an estimate as an
  invoice or an actual provider charge.

## Delivery Checks

1. Verify every declared output exists and is non-empty.
2. Record output hashes and the exact tool status.
3. Link the approved plan, approval decision, execution receipt, QA result,
   and final output from `delivery_report.json`.
4. Report failed or unavailable backends as failures, not empty success.

## Common Pitfalls

- Editing `data/.univa/*.db` directly.
- Reusing a consumed continuation token or receipt operation ID.
- Treating a filename as sufficient provenance without a content hash.
- Recording only LLM cost while omitting media-provider cost.
- Claiming that direct runner JSON was automatically added to the canonical
  Artifact store when no `ArtifactStore` call occurred.
