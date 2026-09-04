"""
Pipeline Orchestrator — Manages multi-stage pipeline execution with pause/resume
semantics for interactive creative pipelines.

Mirrors the EP_STATE pattern from executive-producer skills but moves state
management from LLM context into server-side Python objects.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional, AsyncGenerator
import time
import logging
import uuid
import os

from univa.utils.budget_tracker import BudgetTracker
from univa.utils.pipeline_state_store import PipelineStateStore
from univa.utils.artifact_store import ArtifactStore, content_sha256
from univa.utils.skill_loader import SkillLoader

logger = logging.getLogger(__name__)


@dataclass
class PipelineState:
    """Complete state of a pipeline execution."""
    pipeline_name: str
    session_id: str
    owner_id: str = ""
    project_id: str = ""
    original_user_request: str = ""
    current_stage_index: int = 0
    status: str = "initialized"  # initialized → running → awaiting_human → completed → failed

    # Artifacts produced by each stage
    artifacts: Dict[str, Any] = field(default_factory=dict)
    # Canonical envelopes keyed by artifact type. ``artifacts`` stays intact
    # for compatibility with existing skills and clients.
    artifact_records: Dict[str, Any] = field(default_factory=dict)

    # Budget tracking
    budget: Optional[BudgetTracker] = None

    # Interaction state (for selection/confirm stages)
    interaction_stage: Optional[str] = None
    interaction_prompt: Optional[str] = None
    interaction_data: Optional[Dict] = None  # proposals, storyboard, etc.

    # Timeline
    stage_timeline: List[Dict] = field(default_factory=list)
    _stage_start_time: float = 0.0

    # Quality gate tracking (per quality-gate skill)
    quality_reports: Dict[str, Dict] = field(default_factory=dict)
    send_back_count: int = 0

    # Continuation token for resume
    continuation_token: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    expires_at: float = 0.0

    def start_stage(self, stage_name: str) -> None:
        """Mark the start of a stage for timing."""
        self._stage_start_time = time.time()

    def end_stage(self, stage_name: str, status: str = "completed") -> None:
        """Mark the end of a stage, recording duration."""
        duration = time.time() - self._stage_start_time
        self.stage_timeline.append({
            "stage": stage_name,
            "status": status,
            "duration_seconds": round(duration, 1),
        })

    @classmethod
    def from_persisted(cls, data: Dict[str, Any]) -> "PipelineState":
        """Rehydrate a state without exposing its persisted token hash."""
        state = cls(
            pipeline_name=str(data.get("pipeline_name", "")),
            session_id=str(data.get("session_id", "")),
            owner_id=str(data.get("owner_id", "")),
            project_id=str(data.get("project_id", "")),
            original_user_request=str(data.get("original_user_request", "")),
            current_stage_index=int(data.get("current_stage_index", 0)),
            status=str(data.get("status", "initialized")),
            artifacts=data.get("artifacts") or {},
            artifact_records=data.get("artifact_records") or {},
            budget=BudgetTracker.from_dict(data.get("budget")),
            interaction_stage=data.get("interaction_stage"),
            interaction_prompt=data.get("interaction_prompt"),
            interaction_data=data.get("interaction_data"),
            stage_timeline=data.get("stage_timeline") or [],
            quality_reports=data.get("quality_reports") or {},
            send_back_count=int(data.get("send_back_count", 0)),
            # The raw token is intentionally not persisted. The store verifies
            # the caller's token against its hash before resuming this state.
            continuation_token="",
            created_at=float(data.get("created_at", time.time())),
            updated_at=float(data.get("updated_at", time.time())),
            expires_at=float(data.get("expires_at", 0.0)),
        )
        return state


class PipelineOrchestrator:
    """
    Manages multi-stage pipeline execution.

    Usage:
        orchestrator = PipelineOrchestrator(skill_loader)
        state = await orchestrator.start(pipeline_name, user_request, plan_act_system)
        # If state.status == "awaiting_human", present interaction prompt
        state = await orchestrator.resume(user_input, plan_act_system)
        # Continue until status == "completed"
    """

    def __init__(
        self,
        skill_loader: SkillLoader,
        state_store: Optional[PipelineStateStore] = None,
        artifact_store: Optional[ArtifactStore] = None,
    ):
        self.skill_loader = skill_loader
        self._active_states: Dict[str, PipelineState] = {}
        self.state_store = state_store or PipelineStateStore()
        self.artifact_store = artifact_store or ArtifactStore()

    def _persist_state(self, state: PipelineState) -> None:
        """Keep the cache and durable state synchronized."""
        try:
            self.state_store.save(state)
        except Exception:
            # A transient persistence problem must not corrupt the in-memory
            # execution. It is logged loudly so operators can repair storage.
            logger.exception("Could not persist pipeline state %s", state.session_id)

    def _load_state(self, session_id: str) -> Optional[PipelineState]:
        record = self.state_store.load(session_id)
        if not record:
            return None
        state = PipelineState.from_persisted(record)
        self._active_states[session_id] = state
        return state

    def _pause_for_stage_approval(self, state: PipelineState, stage_name: str) -> None:
        """Pause after a productive stage that declares human approval."""
        state.status = "awaiting_human"
        state.interaction_stage = f"approval:{stage_name}"
        state.interaction_data = {
            "type": "user_approval",
            "stage": stage_name,
            "review_summary": str(state.artifacts.get(stage_name, {}))[:3000],
        }
        state.interaction_prompt = (
            f"Review the '{stage_name}' stage output. Enter 'confirm' to continue, "
            "or describe revisions."
        )

    # ── Public API ──────────────────────────────────────────────────────

    async def start(
        self,
        pipeline_name: str,
        user_request: str,
        plan_act_system,  # PlanActSystem instance
        session_id: Optional[str] = None,
        budget_limit_usd: float = 1.50,
        owner_id: str = "",
        project_id: str = "",
    ) -> PipelineState:
        """
        Start a new pipeline execution. Runs from the first stage to the first
        interactive gate, then returns with status='awaiting_human'.
        """
        # Load pipeline definition
        pipeline_def = self.skill_loader.load_pipeline(pipeline_name)
        if not pipeline_def:
            raise ValueError(f"Pipeline '{pipeline_name}' not found")

        # Initialize state
        state = PipelineState(
            pipeline_name=pipeline_name,
            session_id=session_id or str(uuid.uuid4()),
            owner_id=owner_id or "",
            project_id=project_id or "",
            original_user_request=user_request,
            budget=BudgetTracker(
                budget_limit_usd=budget_limit_usd,
                model=plan_act_system.plan_agent.agent.model.id
                if hasattr(plan_act_system.plan_agent.agent, 'model')
                else "gpt-5",
            ),
        )

        # Load budget from pipeline manifest if specified
        orch = pipeline_def.get('orchestration', {})
        if orch.get('budget_default_usd'):
            state.budget.budget_limit_usd = float(orch['budget_default_usd'])

        state.status = "running"
        self._active_states[state.session_id] = state
        self._persist_state(state)

        # Execute stages until an interactive gate or completion
        stages = pipeline_def.get('stages', [])
        for idx, stage_def in enumerate(stages):
            state.current_stage_index = idx
            stage_name = stage_def['name']

            # Check if this is an interactive stage
            if stage_def.get('human_approval_default') and stage_name in ('selection', 'confirm'):
                # Prepare interaction data
                state.interaction_stage = stage_name
                state.interaction_data = self._build_interaction_data(stage_name, state)
                state.interaction_prompt = self._build_interaction_prompt(stage_name, state)
                state.status = "awaiting_human"
                self._persist_state(state)
                return state

            # Execute non-interactive stage
            state.start_stage(stage_name)
            try:
                result = await self._execute_stage(
                    stage_def, state, user_request, plan_act_system
                )
                state.artifacts[stage_name] = result
                state.end_stage(stage_name, "completed")
                self._persist_state(state)
                logger.info(f"Stage '{stage_name}' completed successfully")
                if stage_def.get('human_approval_default'):
                    self._pause_for_stage_approval(state, stage_name)
                    self._persist_state(state)
                    return state
            except Exception as e:
                logger.error(f"Stage '{stage_name}' failed: {e}")
                state.end_stage(stage_name, "failed")
                state.status = "failed"
                self._persist_state(state)
                return state

        # All stages completed without interaction (shouldn't happen for creative-proposal)
        state.status = "completed"
        self._persist_state(state)
        return state

    async def resume(
        self,
        user_input: str,
        plan_act_system,  # PlanActSystem instance
        session_id: str,
        continuation_token: Optional[str] = None,
        owner_id: Optional[str] = None,
    ) -> PipelineState:
        """
        Resume a pipeline from an interactive gate. Applies user input,
        then continues executing remaining stages to the next gate or completion.
        """
        if continuation_token is not None:
            claimed = self.state_store.claim_resume(session_id, continuation_token, owner_id)
            state = PipelineState.from_persisted(claimed)
            # Keep the submitted token only until the decision is processed;
            # every resulting checkpoint receives a newly generated token.
            state.continuation_token = continuation_token
            self._active_states[session_id] = state
        else:
            state = self._active_states.get(session_id) or self._load_state(session_id)
        if not state:
            raise ValueError(f"No active pipeline for session '{session_id}'")

        if owner_id is not None and state.owner_id and state.owner_id != owner_id:
            raise PermissionError(f"Pipeline session '{session_id}' does not belong to this user")

        # Existing in-process callers historically omitted the token. Keep that
        # API compatible, while all durable/API callers must provide it. A
        # hydrated state has no raw token and therefore always requires one.
        if continuation_token is None and not state.continuation_token:
            raise PermissionError("A continuation token is required to resume this session")

        if state.status not in {"awaiting_human", "resuming"}:
            raise ValueError(
                f"Pipeline session '{session_id}' is not awaiting input "
                f"(status: {state.status})"
            )

        stage_name = state.interaction_stage
        approval_target = (
            stage_name.split(":", 1)[1]
            if isinstance(stage_name, str) and stage_name.startswith("approval:")
            else None
        )
        logger.info(f"Resuming pipeline '{state.pipeline_name}' at '{stage_name}'")

        # Process user input for the interaction stage
        state.start_stage(stage_name)
        try:
            processed = self._process_interaction(stage_name, user_input, state)
            if stage_name == "pre_generation" and not processed.get("confirmed"):
                state.artifacts["pre_generation_revision"] = processed
                state.interaction_data = {
                    **(state.interaction_data or {}),
                    "revision_request": user_input,
                }
                state.continuation_token = uuid.uuid4().hex[:12]
                state.status = "awaiting_human"
                self._persist_state(state)
                return state
            if approval_target and not processed.get("confirmed"):
                pipeline_def = self.skill_loader.load_pipeline(state.pipeline_name) or {}
                stages = pipeline_def.get("stages", [])
                target_def = (
                    stages[state.current_stage_index]
                    if 0 <= state.current_stage_index < len(stages)
                    else None
                )
                if not target_def or target_def.get("name") != approval_target:
                    raise RuntimeError(f"Approval target '{approval_target}' no longer matches the pipeline")
                revised = await self._execute_stage(
                    target_def,
                    state,
                    f"{state.original_user_request}\n\nRevision requested for '{approval_target}': {user_input}",
                    plan_act_system,
                )
                state.artifacts[approval_target] = revised
                state.artifacts[f"{approval_target}_revision_request"] = processed
                self._pause_for_stage_approval(state, approval_target)
                state.continuation_token = uuid.uuid4().hex[:12]
                self._persist_state(state)
                return state
            if stage_name == "confirm" and not processed.get("confirmed"):
                pipeline_def = self.skill_loader.load_pipeline(state.pipeline_name) or {}
                stages = pipeline_def.get("stages", [])
                previous_index = max(0, state.current_stage_index - 1)
                previous_stage = stages[previous_index] if stages else None
                if previous_stage:
                    previous_name = previous_stage["name"]
                    revised = await self._execute_stage(
                        previous_stage, state,
                        f"{user_input}\n\nRevision requested at the approval gate. Produce a refreshed plan and review; do not call media generation or mutation tools.",
                        plan_act_system,
                    )
                    state.artifacts[previous_name] = revised
                state.artifacts["revision_request"] = processed
                state.status = "awaiting_human"
                state.interaction_data = self._build_interaction_data("confirm", state)
                state.interaction_prompt = self._build_interaction_prompt("confirm", state)
                state.continuation_token = uuid.uuid4().hex[:12]
                self._persist_state(state)
                return state
            pipeline_def = self.skill_loader.load_pipeline(state.pipeline_name) or {}
            stages = pipeline_def.get("stages", [])
            interaction_def = (
                stages[state.current_stage_index]
                if 0 <= state.current_stage_index < len(stages)
                else {}
            )
            if processed.get("confirmed") or stage_name == "selection":
                approved_records = [
                    {
                        "artifact_id": record.get("artifact_id"),
                        "artifact_type": record.get("artifact_type"),
                        "version": record.get("version"),
                        "content_sha256": record.get("content_sha256"),
                    }
                    for record in state.artifact_records.values()
                    if isinstance(record, dict) and record.get("artifact_id")
                ]
                for produced_name in interaction_def.get("produces", []):
                    processed[produced_name] = {
                        "approved": bool(processed.get("confirmed", True)),
                        "decision": processed,
                        "approved_artifacts": approved_records,
                        "approved_at": time.time(),
                    }
            decision_key = f"{approval_target}_approval" if approval_target else stage_name
            state.artifacts[decision_key] = processed
            if approval_target:
                approval_record = self.artifact_store.write_artifact(
                    decision_key,
                    processed,
                    project_id=state.project_id,
                    job_id=state.session_id,
                    parent_artifact_ids=[
                        record.get("artifact_id")
                        for record in state.artifact_records.values()
                        if isinstance(record, dict) and record.get("artifact_id")
                    ],
                    status="approved",
                    created_by="user",
                    approved_by=state.owner_id or "user",
                    provenance={"pipeline": state.pipeline_name, "stage": approval_target},
                )
                state.artifact_records[decision_key] = approval_record
            self._record_stage_artifacts(
                state, interaction_def, processed, user_input,
                {"decision": "PASS", "stage": stage_name},
            )
            state.end_stage(stage_name, "completed")
        except Exception as e:
            logger.error(f"Interaction stage '{stage_name}' failed: {e}")
            state.end_stage(stage_name, "failed")
            state.status = "failed"
            self._persist_state(state)
            return state

        # Consume the token before any subsequent stage can execute. A retry
        # of the same approval therefore cannot duplicate paid work.
        state.continuation_token = uuid.uuid4().hex[:12]

        # Clear interaction state
        state.interaction_stage = None
        state.interaction_prompt = None
        state.interaction_data = None
        state.status = "running"

        # Continue with remaining stages
        pipeline_def = self.skill_loader.load_pipeline(state.pipeline_name)
        stages = pipeline_def.get('stages', [])

        # A pre-generation gate is placed immediately before the expensive
        # stage, so approval resumes that same index. Normal selection/confirm
        # gates resume with the following stage.
        first_stage_index = (
            state.current_stage_index
            if stage_name == "pre_generation"
            else state.current_stage_index + 1
        )
        for idx in range(first_stage_index, len(stages)):
            stage_def = stages[idx]
            state.current_stage_index = idx
            next_stage_name = stage_def['name']

            # Check for next interactive gate
            if stage_def.get('human_approval_default') and next_stage_name in ('selection', 'confirm'):
                state.interaction_stage = next_stage_name
                state.interaction_data = self._build_interaction_data(next_stage_name, state)
                state.interaction_prompt = self._build_interaction_prompt(next_stage_name, state)
                state.status = "awaiting_human"
                self._persist_state(state)
                return state

            state.start_stage(next_stage_name)
            try:
                result = await self._execute_stage(
                    stage_def,
                    state,
                    state.original_user_request or user_input,
                    plan_act_system,
                )
                state.artifacts[next_stage_name] = result
                state.end_stage(next_stage_name, "completed")
                self._persist_state(state)
                if stage_def.get('human_approval_default'):
                    self._pause_for_stage_approval(state, next_stage_name)
                    self._persist_state(state)
                    return state
            except Exception as e:
                logger.error(f"Stage '{next_stage_name}' failed: {e}")
                state.end_stage(next_stage_name, "failed")
                state.status = "failed"
                self._persist_state(state)
                return state

        state.status = "completed"
        self._persist_state(state)
        logger.info(f"Pipeline '{state.pipeline_name}' completed")
        return state

    async def execute_full(
        self,
        pipeline_name: str,
        user_request: str,
        plan_act_system,
        session_id: Optional[str] = None,
    ) -> PipelineState:
        """
        Execute the full pipeline non-interactively (for pipelines without
        interactive stages, or when all stages are pre-approved).
        """
        state = await self.start(pipeline_name, user_request, plan_act_system, session_id)

        while state.status == "awaiting_human":
            # Auto-approve (used for testing or when user pre-approved all stages)
            logger.warning(
                f"Pipeline '{pipeline_name}' hit interactive gate '{state.interaction_stage}' "
                f"in non-interactive mode. Auto-approving with defaults."
            )
            state = await self.resume(
                '{"confirmed": true, "choice": "proposal_1"}',
                plan_act_system,
                state.session_id,
            )

        return state

    def get_state(self, session_id: str) -> Optional[PipelineState]:
        """Get the current pipeline state for a session."""
        return self._active_states.get(session_id) or self._load_state(session_id)

    def remove_state(self, session_id: str) -> None:
        """Remove only the memory cache; durable history remains queryable."""
        self._active_states.pop(session_id, None)

    # ── Internal helpers ────────────────────────────────────────────────

    async def _execute_stage(
        self,
        stage_def: Dict,
        state: PipelineState,
        user_request: str,
        plan_act_system,
    ) -> Dict:
        """
        Execute a single non-interactive stage using PlanAgent + ActAgent.

        After execution, runs the quality gate (per quality-gate skill)
        to validate stage outputs against pipeline success_criteria.
        """
        stage_name = stage_def['name']
        skill_path = stage_def.get('skill', '')

        missing_inputs = [
            artifact_name
            for artifact_name in stage_def.get("required_artifacts_in", [])
            if not any(
                self._extract_artifact_payload(previous, artifact_name) is not None
                for previous in state.artifacts.values()
            )
        ]
        if missing_inputs:
            raise RuntimeError(
                f"Stage '{stage_name}' is missing required artifacts: {', '.join(missing_inputs)}"
            )

        # Load stage director skill for context
        skill_content = ""
        if skill_path:
            try:
                skill_content = self.skill_loader.load_skill(skill_path)
            except Exception as e:
                logger.warning(f"Could not load skill '{skill_path}': {e}")

        # Build stage-specific request for PlanAgent
        stage_request = self._build_stage_request(
            stage_name, stage_def, state, user_request, skill_content
        )

        # Let PlanAgent/ActAgent record usage consistently for both initial
        # streaming execution and /chat/resume continuation. Restore previous
        # trackers so nested callers do not inherit this pipeline budget.
        previous_plan_budget = getattr(plan_act_system.plan_agent, 'budget_tracker', None)
        previous_act_budget = getattr(plan_act_system.act_agent, 'budget_tracker', None)
        attached_plan_budget = False
        attached_act_budget = False
        stage_llm_start = len(state.budget.llm_calls) if state.budget else 0
        if state.budget and previous_plan_budget is None:
            plan_act_system.plan_agent.budget_tracker = state.budget
            attached_plan_budget = True
        if state.budget and previous_act_budget is None:
            plan_act_system.act_agent.budget_tracker = state.budget
            attached_act_budget = True

        try:
            # Generate plan for this stage
            plan = await plan_act_system.plan_agent.generate_plan(
                state.session_id, stage_request
            )
        except Exception:
            if attached_act_budget:
                plan_act_system.act_agent.budget_tracker = previous_act_budget
            raise
        finally:
            if attached_plan_budget:
                plan_act_system.plan_agent.budget_tracker = previous_plan_budget
            if state.budget:
                for call in state.budget.llm_calls[stage_llm_start:]:
                    call.stage = stage_name

        # If no tool calls needed (proposal, storyboard stages), return plan as artifact
        if not stage_def.get('tools_available') and not stage_def.get('required_tools'):
            if attached_act_budget:
                plan_act_system.act_agent.budget_tracker = previous_act_budget
            result = {"plan": plan, "stage": stage_name}
        else:
            # Execute plan with ActAgent for tool-calling stages
            if isinstance(plan, dict) and 'execution_plan' in plan:
                try:
                    results = await plan_act_system.act_agent.execute_plan(
                        stage_request, plan
                    )
                finally:
                    if attached_act_budget:
                        plan_act_system.act_agent.budget_tracker = previous_act_budget
                    if state.budget:
                        for call in state.budget.llm_calls[stage_llm_start:]:
                            call.stage = stage_name

                # Record tool usage from results
                for step_idx, step_result in (results or {}).items():
                    if isinstance(step_result, dict):
                        steps = plan.get('execution_plan', {}).get('steps', [])
                        step_def = steps[int(step_idx) - 1] if int(step_idx) - 1 < len(steps) else {}
                        tool_name = step_def.get('tool', {}).get('name', 'unknown')
                        planned_duration = (
                            step_result.get('duration_seconds')
                            or step_result.get('planned_duration_seconds')
                            or step_def.get('duration_seconds')
                            or step_def.get('tool', {}).get('arguments', {}).get('duration_seconds')
                            or 0.0
                        )
                        if state.budget:
                            actual_cost = self._find_first_value(
                                step_result, {"actual_cost_usd"}
                            )
                            if actual_cost is None:
                                actual_cost = self._find_first_value(
                                    step_result, {"cost_usd"}
                                )
                            state.budget.record_tool_call(
                                tool_name=tool_name,
                                duration_seconds=float(planned_duration),
                                stage=stage_name,
                                actual_cost_usd=actual_cost,
                                provider_task_id=self._find_first_value(
                                    step_result,
                                    {"provider_task_id", "task_id", "request_id"},
                                ),
                                provider=self._find_first_value(
                                    step_result, {"provider"}
                                ),
                                model=self._find_first_value(
                                    step_result, {"model"}
                                ),
                            )

                result = {
                    "plan": plan,
                    "execution_results": results,
                    "stage": stage_name,
                }
            else:
                if attached_act_budget:
                    plan_act_system.act_agent.budget_tracker = previous_act_budget
                result = {"plan": plan, "stage": stage_name}

        # ── Quality Gate (per quality-gate skill) ──
        qg_result = self._run_quality_gate(stage_def, state, result)
        state.quality_reports[stage_name] = qg_result
        result = dict(result)
        result["artifact_records"] = self._record_stage_artifacts(
            state, stage_def, result, stage_request, qg_result
        )

        if qg_result['decision'] == 'SEND_BACK':
            pipeline_def = self.skill_loader.load_pipeline(state.pipeline_name)
            max_send_backs = (
                pipeline_def.get('orchestration', {}).get('max_send_backs', 3)
                if pipeline_def else 3
            )
            if state.send_back_count < max_send_backs:
                logger.warning(
                    f"Quality gate SEND_BACK for '{stage_name}' "
                    f"(attempt {state.send_back_count + 1}/{max_send_backs}): "
                    f"score={qg_result['quality_score']:.0%}"
                )
                state.send_back_count += 1
                # Re-execute with quality report injected as context
                return await self._execute_stage(
                    stage_def, state,
                    f"{user_request}\n\n[Quality Gate Feedback: {qg_result['failures']}]",
                    plan_act_system,
                )
            else:
                logger.error(
                    f"Quality gate BLOCKED for '{stage_name}': "
                    f"max send-backs ({max_send_backs}) exceeded"
                )
                qg_result['decision'] = 'BLOCKED'

        if qg_result['decision'] == 'BLOCKED':
            state.status = 'blocked'
            raise RuntimeError(
                f"Pipeline blocked at '{stage_name}': quality gate failed. "
                f"Failures: {qg_result['failures']}"
            )

        logger.info(
            f"Quality gate for '{stage_name}': {qg_result['decision']} "
            f"(score: {qg_result['quality_score']:.0%})"
        )

        return result

    def _record_stage_artifacts(
        self,
        state: PipelineState,
        stage_def: Dict[str, Any],
        stage_result: Dict[str, Any],
        request: str = "",
        quality_report: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Write canonical envelopes while preserving the legacy stage result."""
        records: Dict[str, Any] = {}
        stage_name = stage_def.get("name", "")
        stage_cost = (
            state.budget.stage_breakdown().get(stage_name, {})
            if state.budget else {}
        )
        effective_stage_cost = (
            stage_cost.get("llm_cost", 0.0) + stage_cost.get("tool_cost", 0.0)
        )
        parent_ids = [
            record.get("artifact_id")
            for record in state.artifact_records.values()
            if isinstance(record, dict) and record.get("artifact_id")
        ]
        artifact_names = list(stage_def.get("produces", []))
        artifact_names.extend(stage_def.get("optional_produces", []))
        for alternatives in stage_def.get("produces_any", []):
            artifact_names.extend(alternatives if isinstance(alternatives, list) else [alternatives])
        for artifact_name in dict.fromkeys(artifact_names):
            payload = self._extract_artifact_payload(stage_result, artifact_name)
            if payload is None:
                continue
            record = self.artifact_store.write_artifact(
                artifact_name,
                payload,
                project_id=state.project_id,
                job_id=state.session_id,
                parent_artifact_ids=parent_ids,
                status=(
                    "validated"
                    if quality_report and quality_report.get("decision") == "PASS"
                    else "draft"
                ),
                model=state.budget.model if state.budget else None,
                cost_usd=effective_stage_cost,
                provenance={"pipeline": state.pipeline_name, "stage": stage_def.get("name", "")},
            )
            state.artifact_records[artifact_name] = record
            records[artifact_name] = record

        if quality_report is not None:
            quality_record = self.artifact_store.write_artifact(
                f"{stage_def.get('name', 'stage')}_quality_report",
                quality_report,
                project_id=state.project_id,
                job_id=state.session_id,
                parent_artifact_ids=parent_ids,
                status=(
                    "validated"
                    if quality_report.get("decision") in {"PASS", "PASS_WITH_WARNINGS"}
                    else "blocked"
                ),
                model=state.budget.model if state.budget else None,
                provenance={"pipeline": state.pipeline_name, "stage": stage_def.get("name", "")},
            )
            state.artifact_records[f"{stage_def.get('name', 'stage')}_quality_report"] = quality_record
            records["quality_report"] = quality_record
            receipt = self.artifact_store.write_receipt({
                "job_id": state.session_id,
                "stage": stage_def.get("name", ""),
                "tool_name": "stage_execution",
                "input_sha256": content_sha256(request),
                "approved_plan_sha256": content_sha256(state.artifacts.get("confirm", {})),
                "status": quality_report.get("decision", "unknown").lower(),
                "estimated_cost_usd": effective_stage_cost,
                "llm_cost_usd": stage_cost.get("llm_cost", 0.0),
                "tool_cost_usd": stage_cost.get("tool_cost", 0.0),
                "actual_tool_cost_usd": stage_cost.get("tool_actual_cost", 0.0),
                "fallback_estimated_tool_cost_usd": stage_cost.get(
                    "tool_fallback_estimated_cost", 0.0
                ),
                "output_paths": list(self._collect_output_paths(stage_result)),
            })
            records["execution_receipt"] = receipt
            tool_receipts = []
            plan = stage_result.get("plan") if isinstance(stage_result, dict) else None
            execution_results = stage_result.get("execution_results") if isinstance(stage_result, dict) else None
            steps = (
                plan.get("execution_plan", {}).get("steps", [])
                if isinstance(plan, dict) else []
            )
            if isinstance(execution_results, dict):
                for index, step in enumerate(steps, start=1):
                    tool = step.get("tool", {}) if isinstance(step, dict) else {}
                    tool_name = tool.get("name") or "unknown"
                    step_result = execution_results.get(index, execution_results.get(str(index), {}))
                    tool_receipts.append(self.artifact_store.write_receipt({
                        "job_id": state.session_id,
                        "stage": stage_def.get("name", ""),
                        "tool_name": tool_name,
                        "input": tool.get("arguments", {}),
                        "approved_plan_sha256": content_sha256(state.artifacts.get("confirm", {})),
                        "provider_task_id": self._find_first_value(
                            step_result, {"provider_task_id", "task_id", "request_id"}
                        ),
                        "provider": self._find_first_value(step_result, {"provider"}),
                        "model": self._find_first_value(step_result, {"model"}),
                        "status": "success" if self._result_succeeded(step_result) else "failed",
                        "actual_cost_usd": self._find_first_value(
                            step_result, {"actual_cost_usd", "cost_usd"}
                        ),
                        "output_paths": list(self._collect_output_paths(step_result)),
                    }))
            if tool_receipts:
                records["tool_execution_receipts"] = tool_receipts
        return records

    @staticmethod
    def _collect_output_paths(value: Any):
        if isinstance(value, str) and os.path.isfile(value):
            yield value
        elif isinstance(value, dict):
            for item in value.values():
                yield from PipelineOrchestrator._collect_output_paths(item)
        elif isinstance(value, list):
            for item in value:
                yield from PipelineOrchestrator._collect_output_paths(item)

    @staticmethod
    def _find_first_value(value: Any, keys: set[str]):
        if isinstance(value, dict):
            for key in keys:
                if value.get(key) is not None:
                    return value[key]
            for item in value.values():
                found = PipelineOrchestrator._find_first_value(item, keys)
                if found is not None:
                    return found
        elif isinstance(value, list):
            for item in value:
                found = PipelineOrchestrator._find_first_value(item, keys)
                if found is not None:
                    return found
        return None

    @staticmethod
    def _result_succeeded(value: Any) -> bool:
        if isinstance(value, dict):
            if "success" in value:
                return bool(value["success"])
            if value.get("error"):
                return False
        return value is not None

    @staticmethod
    def _extract_artifact_payload(stage_result: Dict, artifact_name: str):
        """Return the structured payload for an artifact, if present."""
        if not isinstance(stage_result, dict):
            return None
        if artifact_name in stage_result:
            return stage_result[artifact_name]

        plan = stage_result.get('plan')
        if isinstance(plan, dict):
            if artifact_name in plan:
                return plan[artifact_name]
            artifacts = plan.get('artifacts')
            if isinstance(artifacts, dict) and artifact_name in artifacts:
                return artifacts[artifact_name]

        execution_results = stage_result.get('execution_results')
        if isinstance(execution_results, dict):
            for result in execution_results.values():
                if isinstance(result, dict) and artifact_name in result:
                    return result[artifact_name]

        # Do not validate wrapper dicts like {'plan': ..., 'stage': ...} as artifacts.
        wrapper_keys = {'plan', 'stage', 'execution_results', 'artifact_records'}
        if set(stage_result).issubset(wrapper_keys):
            return None
        return stage_result

    def _run_quality_gate(
        self, stage_def: Dict, state: PipelineState, stage_result: Dict
    ) -> dict:
        """
        Run automated quality checks on stage output.

        Per the quality-gate skill, checks include:
        - Schema validation
        - File existence
        - Count/duration matching
        - Budget threshold
        - Non-empty required fields

        Returns a quality report dict with decision, score, checks.
        """
        import os as _os
        stage_name = stage_def['name']
        produces = stage_def.get('produces', [])
        optional_produces = stage_def.get('optional_produces', [])
        produces_any = stage_def.get('produces_any', [])
        review_focus = stage_def.get('review_focus', [])
        success_criteria = stage_def.get('success_criteria', [])

        checks = []
        passed = 0
        total = 0

        # ── Check 1: Schema validation for produced artifacts ──
        for artifact_name in produces:
            try:
                artifact_data = self._extract_artifact_payload(stage_result, artifact_name)
                if artifact_data is None:
                    total += 1
                    checks.append({
                        'type': 'schema_validate',
                        'target': artifact_name,
                        'status': 'FAIL',
                        'detail': f"Required produced artifact '{artifact_name}' is missing",
                    })
                    continue

                total += 1
                schema_result = self.skill_loader.validate_artifact_against_schema(
                    artifact_name, artifact_data
                )
                if schema_result['valid']:
                    passed += 1
                    checks.append({
                        'type': 'schema_validate',
                        'target': artifact_name,
                        'status': 'PASS',
                        'detail': f"'{artifact_name}' conforms to schema",
                    })
                else:
                    checks.append({
                        'type': 'schema_validate',
                        'target': artifact_name,
                        'status': 'FAIL',
                        'detail': f"Schema validation failed: {schema_result['errors'][:3]}",
                    })
            except Exception as e:
                total += 1
                checks.append({
                    'type': 'schema_validate',
                    'target': artifact_name,
                    'status': 'FAIL',
                    'detail': f"Could not validate required artifact: {e}",
                })

        # Optional outputs are validated only when present. ``produces_any``
        # expresses alternatives such as media_plan OR edit_proposal.
        for artifact_name in optional_produces:
            artifact_data = self._extract_artifact_payload(stage_result, artifact_name)
            if artifact_data is None:
                continue
            total += 1
            schema_result = self.skill_loader.validate_artifact_against_schema(
                artifact_name, artifact_data
            )
            status = 'PASS' if schema_result['valid'] else 'FAIL'
            passed += int(status == 'PASS')
            checks.append({
                'type': 'schema_validate',
                'target': artifact_name,
                'status': status,
                'detail': (
                    f"Optional artifact '{artifact_name}' conforms to schema"
                    if status == 'PASS'
                    else f"Schema validation failed: {schema_result['errors'][:3]}"
                ),
            })

        for alternatives in produces_any:
            names = alternatives if isinstance(alternatives, list) else [alternatives]
            present = [
                name for name in names
                if self._extract_artifact_payload(stage_result, name) is not None
            ]
            total += 1
            if present:
                passed += 1
                checks.append({
                    'type': 'artifact_alternative',
                    'target': names,
                    'status': 'PASS',
                    'detail': f"Alternative output present: {', '.join(present)}",
                })
            else:
                checks.append({
                    'type': 'artifact_alternative',
                    'target': names,
                    'status': 'FAIL',
                    'detail': f"At least one output is required: {', '.join(names)}",
                })

        # ── Check 2: File existence for generation stages ──
        stage_tools = set(stage_def.get("required_tools") or []) | set(stage_def.get("tools_available") or [])
        read_only_or_planning_tools = {
            "vision2text_gen", "video_referring_segmentation", "plan_audio_for_video",
            "index_video_media", "search_video_moments", "get_video_moment",
            "transcribe_media", "translate_captions", "validate_localized_media",
        }
        media_output_tools = stage_tools - read_only_or_planning_tools
        if media_output_tools:
            total += 1
            missing_files = []
            found_files = []

            def _collect_paths(obj):
                if isinstance(obj, str) and _os.path.exists(obj):
                    found_files.append(obj)
                elif isinstance(obj, str) and any(
                    obj.endswith(ext) for ext in ['.mp4', '.jpg', '.png', '.mp3', '.wav']
                ):
                    missing_files.append(obj)
                elif isinstance(obj, dict):
                    for v in obj.values():
                        _collect_paths(v)
                elif isinstance(obj, list):
                    for v in obj:
                        _collect_paths(v)

            _collect_paths(stage_result)
            if not missing_files and found_files:
                passed += 1
                checks.append({
                    'type': 'file_exists',
                    'status': 'PASS',
                    'detail': f'All {len(found_files)} output files verified',
                })
            elif missing_files:
                checks.append({
                    'type': 'file_exists',
                    'status': 'FAIL',
                    'detail': f'{len(missing_files)} missing files: {missing_files[:3]}',
                })
            else:
                checks.append({
                    'type': 'file_exists',
                    'status': 'SKIP',
                    'detail': 'No file paths found in stage output',
                })

        # ── Check 3: Budget threshold ──
        if state.budget:
            total += 1
            usage = (
                state.budget.total_spent_usd / state.budget.budget_limit_usd
                if state.budget.budget_limit_usd > 0 else 0
            )
            if usage < 0.95:
                passed += 1
                checks.append({
                    'type': 'budget_threshold',
                    'status': 'PASS',
                    'detail': f'Budget at {usage:.0%} (${state.budget.total_spent_usd:.2f}/${state.budget.budget_limit_usd:.2f})',
                })
            elif usage < 1.0:
                checks.append({
                    'type': 'budget_threshold',
                    'status': 'WARN',
                    'detail': f'Budget at {usage:.0%} — approaching limit',
                })
            else:
                checks.append({
                    'type': 'budget_threshold',
                    'status': 'FAIL',
                    'detail': f'Budget exceeded: ${state.budget.total_spent_usd:.2f} > ${state.budget.budget_limit_usd:.2f}',
                })

        # ── Compute quality score and decision ──
        quality_score = passed / total if total > 0 else 1.0
        failures = [c for c in checks if c['status'] == 'FAIL']
        warnings = [c for c in checks if c['status'] == 'WARN']

        # A missing or invalid declared output is a contract violation. It
        # must block the stage even if another non-critical check passed.
        if any(c['type'] in {'schema_validate', 'artifact_alternative'} and c['status'] == 'FAIL' for c in failures):
            decision = 'BLOCKED'
        elif quality_score >= 1.0:
            decision = 'PASS'
        elif quality_score >= 0.6:
            decision = 'PASS_WITH_WARNINGS'
        elif quality_score >= 0.3:
            decision = 'SEND_BACK'
        else:
            decision = 'BLOCKED'

        return {
            'stage': stage_name,
            'pipeline': state.pipeline_name,
            'quality_score': round(quality_score, 2),
            'decision': decision,
            'checks': checks,
            'warnings': [w['detail'] for w in warnings],
            'failures': [f['detail'] for f in failures],
            'total_checks': total,
            'passed_checks': passed,
        }

    def _build_stage_request(
        self,
        stage_name: str,
        stage_def: Dict,
        state: PipelineState,
        original_user_request: str,
        skill_content: str,
    ) -> str:
        """Build a focused request for the PlanAgent for a specific stage."""
        parts = [
            f"### Pipeline Stage: {stage_name}",
            f"### Original User Request: {original_user_request}",
            "",
            f"### Stage Skill Reference:\n{skill_content[:2000]}" if skill_content else "",
            "",
            "### Previous Stage Results:",
        ]

        for artifact_name, artifact in state.artifacts.items():
            parts.append(f"- {artifact_name}: {str(artifact)[:500]}")

        if state.interaction_data:
            parts.append(f"\n### User Input: {state.interaction_data}")

        return '\n'.join(parts)

    def _build_interaction_data(
        self, stage_name: str, state: PipelineState
    ) -> Dict:
        """Build the data to present to the user at an interactive gate."""
        if stage_name == "selection":
            proposals_artifact = state.artifacts.get("proposal", {})
            proposals = []
            if isinstance(proposals_artifact, dict):
                plan = proposals_artifact.get("plan", {})
                if isinstance(plan, dict):
                    exec_plan = plan.get("execution_plan", {})
                    # Extract proposals from plan output
                    for step in exec_plan.get("steps", []):
                        output = step.get("output", "")
                        if output and isinstance(output, str) and "proposal" in output.lower():
                            proposals.append(output)
                    if not proposals:
                        proposals = [str(plan)[:1000]]
                else:
                    proposals = [str(proposals_artifact)[:1000]]

            return {
                "type": "user_choice",
                "stage": "selection",
                "proposals": proposals,
                "prompt": "Choose one proposal above (enter 1-3), or describe requested changes",
            }

        elif stage_name == "confirm":
            review_artifact = state.artifacts.get("storyboard") or state.artifacts.get("proposal") or next(reversed(state.artifacts.values()), {})
            return {
                "type": "user_approval",
                "stage": "confirm",
                "review_summary": str(review_artifact)[:2000],
                "prompt": "Review the creative/editing plan above. Enter 'confirm' to continue, or describe what needs adjustment",
            }

        return {}

    def _build_interaction_prompt(
        self, stage_name: str, state: PipelineState
    ) -> str:
        """Build the natural-language prompt for an interactive gate."""
        if stage_name == "selection":
            return (
                "Choose one creative proposal above, or describe requested changes.\n"
                "Example: 'I choose proposal 2' or 'proposal 1 but make the tone brighter'"
            )
        elif stage_name == "confirm":
            return (
                "Confirm whether the creative/editing plan above matches your expectations.\n"
                "Enter 'confirm' to continue, or describe what needs adjustment."
            )
        return ""

    def _process_interaction(
        self, stage_name: str, user_input: str, state: PipelineState
    ) -> Dict:
        """
        Process user input at an interactive gate and update state accordingly.
        """
        result = {
            "stage": stage_name,
            "user_input": user_input,
            "timestamp": time.time(),
        }

        if stage_name == "selection":
            # Parse user choice
            user_lower = user_input.lower().strip()
            # Try to detect proposal selection
            choice = None
            for i in range(1, 4):
                if f"proposal_{i}" in user_lower or f"proposal {i}" in user_lower:
                    choice = f"proposal_{i}"
                    break

            if not choice:
                # Default to first proposal if unclear
                choice = "proposal_1"

            result["selected_proposal_id"] = choice
            result["modifications"] = user_input if "change" in user_lower or "modify" in user_lower or "revise" in user_lower or "replace" in user_lower else ""

        elif stage_name == "confirm":
            confirmed = any(
                kw in user_input.lower()
                for kw in ["confirm", "ok", "yes", "go ahead", "approve", "approved", "continue"]
            )
            result["confirmed"] = confirmed
            result["adjustments"] = user_input if not confirmed else ""

        elif stage_name == "pre_generation":
            confirmed = any(
                kw in user_input.lower()
                for kw in ["/go", "go ahead", "confirm", "approve", "approved", "continue", "yes"]
            )
            result["confirmed"] = confirmed
            result["adjustments"] = user_input if not confirmed else ""

        elif stage_name.startswith("approval:"):
            confirmed = any(
                kw in user_input.lower()
                for kw in ["confirm", "ok", "yes", "go ahead", "approve", "approved", "continue"]
            )
            result["confirmed"] = confirmed
            result["approved_stage"] = stage_name.split(":", 1)[1]
            result["adjustments"] = user_input if not confirmed else ""

        return result
