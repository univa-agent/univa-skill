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

from univa.utils.budget_tracker import BudgetTracker
from univa.utils.skill_loader import SkillLoader

logger = logging.getLogger(__name__)


@dataclass
class PipelineState:
    """Complete state of a pipeline execution."""
    pipeline_name: str
    session_id: str
    current_stage_index: int = 0
    status: str = "initialized"  # initialized → running → awaiting_human → completed → failed

    # Artifacts produced by each stage
    artifacts: Dict[str, Any] = field(default_factory=dict)

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

    def __init__(self, skill_loader: SkillLoader):
        self.skill_loader = skill_loader
        self._active_states: Dict[str, PipelineState] = {}

    # ── Public API ──────────────────────────────────────────────────────

    async def start(
        self,
        pipeline_name: str,
        user_request: str,
        plan_act_system,  # PlanActSystem instance
        session_id: Optional[str] = None,
        budget_limit_usd: float = 1.50,
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
                return state

            # Execute non-interactive stage
            state.start_stage(stage_name)
            try:
                result = await self._execute_stage(
                    stage_def, state, user_request, plan_act_system
                )
                state.artifacts[stage_name] = result
                state.end_stage(stage_name, "completed")
                logger.info(f"Stage '{stage_name}' completed successfully")
            except Exception as e:
                logger.error(f"Stage '{stage_name}' failed: {e}")
                state.end_stage(stage_name, "failed")
                state.status = "failed"
                return state

        # All stages completed without interaction (shouldn't happen for creative-proposal)
        state.status = "completed"
        return state

    async def resume(
        self,
        user_input: str,
        plan_act_system,  # PlanActSystem instance
        session_id: str,
    ) -> PipelineState:
        """
        Resume a pipeline from an interactive gate. Applies user input,
        then continues executing remaining stages to the next gate or completion.
        """
        state = self._active_states.get(session_id)
        if not state:
            raise ValueError(f"No active pipeline for session '{session_id}'")

        if state.status != "awaiting_human":
            raise ValueError(
                f"Pipeline session '{session_id}' is not awaiting input "
                f"(status: {state.status})"
            )

        stage_name = state.interaction_stage
        logger.info(f"Resuming pipeline '{state.pipeline_name}' at '{stage_name}'")

        # Process user input for the interaction stage
        state.start_stage(stage_name)
        try:
            processed = self._process_interaction(stage_name, user_input, state)
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
                return state
            state.artifacts[stage_name] = processed
            state.end_stage(stage_name, "completed")
        except Exception as e:
            logger.error(f"Interaction stage '{stage_name}' failed: {e}")
            state.end_stage(stage_name, "failed")
            state.status = "failed"
            return state

        # Clear interaction state
        state.interaction_stage = None
        state.interaction_prompt = None
        state.interaction_data = None
        state.status = "running"

        # Continue with remaining stages
        pipeline_def = self.skill_loader.load_pipeline(state.pipeline_name)
        stages = pipeline_def.get('stages', [])

        for idx in range(state.current_stage_index + 1, len(stages)):
            stage_def = stages[idx]
            state.current_stage_index = idx
            next_stage_name = stage_def['name']

            # Check for next interactive gate
            if stage_def.get('human_approval_default') and next_stage_name in ('selection', 'confirm'):
                state.interaction_stage = next_stage_name
                state.interaction_data = self._build_interaction_data(next_stage_name, state)
                state.interaction_prompt = self._build_interaction_prompt(next_stage_name, state)
                state.status = "awaiting_human"
                return state

            state.start_stage(next_stage_name)
            try:
                result = await self._execute_stage(
                    stage_def, state, user_input, plan_act_system
                )
                state.artifacts[next_stage_name] = result
                state.end_stage(next_stage_name, "completed")
            except Exception as e:
                logger.error(f"Stage '{next_stage_name}' failed: {e}")
                state.end_stage(next_stage_name, "failed")
                state.status = "failed"
                return state

        state.status = "completed"
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
        return self._active_states.get(session_id)

    def remove_state(self, session_id: str) -> None:
        """Clean up pipeline state after completion."""
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
                            state.budget.record_tool_call(
                                tool_name=tool_name,
                                duration_seconds=float(planned_duration),
                                stage=stage_name,
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
        wrapper_keys = {'plan', 'stage', 'execution_results'}
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
                    checks.append({
                        'type': 'schema_validate',
                        'target': artifact_name,
                        'status': 'SKIP',
                        'detail': f"No structured payload found for '{artifact_name}'",
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
                checks.append({
                    'type': 'schema_validate',
                    'target': artifact_name,
                    'status': 'SKIP',
                    'detail': f"Could not validate: {e}",
                })

        # ── Check 2: File existence for generation stages ──
        stage_tools = set(stage_def.get("required_tools") or []) | set(stage_def.get("tools_available") or [])
        read_only_or_planning_tools = {"vision2text_gen", "video_referring_segmentation", "plan_audio_for_video"}
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

        if quality_score >= 1.0:
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

        return result
