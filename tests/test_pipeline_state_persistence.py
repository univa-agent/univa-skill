import tempfile
import time
import unittest

from univa.utils.budget_tracker import BudgetTracker
from univa.utils.pipeline_orchestrator import PipelineOrchestrator, PipelineState
from univa.utils.pipeline_state_store import PipelineStateStore


class _Loader:
    def __init__(self, stages):
        self.pipeline = {"stages": stages}

    def load_pipeline(self, name):
        return self.pipeline

    def load_skill(self, path):
        return ""

    def validate_artifact_against_schema(self, name, value):
        return {"valid": True, "errors": []}


class _PlanAgent:
    class _Agent:
        model = type("Model", (), {"id": "test"})()

    agent = _Agent()
    budget_tracker = None

    async def generate_plan(self, session_id, request):
        return {"plan": "test"}


class _ActAgent:
    budget_tracker = None

    async def execute_plan(self, request, plan):
        return {}


class _System:
    plan_agent = _PlanAgent()
    act_agent = _ActAgent()


class PipelineStatePersistenceTests(unittest.IsolatedAsyncioTestCase):
    def make_store(self):
        self.db = tempfile.NamedTemporaryFile(suffix=".db")
        return PipelineStateStore(self.db.name)

    def tearDown(self):
        self.db.close()

    def test_state_round_trip_and_token_hash(self):
        store = self.make_store()
        state = PipelineState(
            pipeline_name="test",
            session_id="session",
            owner_id="user",
            project_id="project",
            original_user_request="make a test",
            budget=BudgetTracker(model="test-model"),
        )
        state.budget.record_llm_call(tokens_in=2, tokens_out=3, stage="proposal")
        store.save(state)

        raw = store.load("session")
        restored = PipelineState.from_persisted(raw)
        self.assertEqual("user", restored.owner_id)
        self.assertEqual("project", restored.project_id)
        self.assertEqual("make a test", restored.original_user_request)
        self.assertEqual(1, restored.budget.total_api_calls)
        self.assertEqual("", restored.continuation_token)
        self.assertTrue(store.validate_token("session", state.continuation_token))
        self.assertFalse(store.validate_token("session", "wrong"))

    async def test_restart_recovery_owner_and_token_are_enforced(self):
        store = self.make_store()
        loader = _Loader([
            {"name": "proposal"},
            {"name": "confirm", "human_approval_default": True},
            {"name": "deliver"},
        ])
        first = PipelineOrchestrator(loader, state_store=store)
        state = await first.start("test", "make a test", _System(), session_id="restart", owner_id="u")
        token = state.continuation_token
        second = PipelineOrchestrator(loader, state_store=store)

        recovered = second.get_state("restart")
        self.assertEqual("awaiting_human", recovered.status)
        with self.assertRaises(PermissionError):
            await second.resume("confirm", _System(), "restart", continuation_token="bad", owner_id="u")
        with self.assertRaises(PermissionError):
            await second.resume("confirm", _System(), "restart", continuation_token=token, owner_id="other")

        completed = await second.resume(
            "confirm", _System(), "restart", continuation_token=token, owner_id="u"
        )
        self.assertEqual("completed", completed.status)
        self.assertIsNotNone(second.get_state("restart"))

    async def test_pre_generation_approval_resumes_same_stage(self):
        store = self.make_store()
        loader = _Loader([{"name": "proposal"}, {"name": "generate"}])
        orchestrator = PipelineOrchestrator(loader, state_store=store)
        state = PipelineState(
            pipeline_name="test",
            session_id="pre-generation",
            owner_id="u",
            original_user_request="generate",
            current_stage_index=1,
            status="awaiting_human",
            interaction_stage="pre_generation",
            budget=BudgetTracker(),
        )
        orchestrator._active_states[state.session_id] = state
        store.save(state)

        resumed = await orchestrator.resume("/go", _System(), state.session_id)
        self.assertEqual("completed", resumed.status)
        self.assertIn("generate", resumed.artifacts)

    async def test_declared_human_stage_pauses_after_output_and_revision_reruns_it(self):
        store = self.make_store()
        loader = _Loader([
            {"name": "proposal", "human_approval_default": True},
            {"name": "deliver"},
        ])
        orchestrator = PipelineOrchestrator(loader, state_store=store)
        state = await orchestrator.start("test", "request", _System(), session_id="generic-gate")
        self.assertEqual("awaiting_human", state.status)
        self.assertEqual("approval:proposal", state.interaction_stage)
        self.assertIn("plan", state.artifacts["proposal"])

        revised = await orchestrator.resume("change the proposal", _System(), state.session_id)
        self.assertEqual("awaiting_human", revised.status)
        self.assertEqual("approval:proposal", revised.interaction_stage)
        self.assertIn("plan", revised.artifacts["proposal"])

        completed = await orchestrator.resume("confirm", _System(), state.session_id)
        self.assertEqual("completed", completed.status)
        self.assertIn("proposal", completed.artifacts)
        self.assertIn("proposal_approval", completed.artifacts)
        self.assertTrue(completed.artifacts["proposal_approval"]["confirmed"])

    def test_expired_state_is_not_recoverable(self):
        store = self.make_store()
        state = PipelineState("test", "expired")
        state.expires_at = time.time() - 1
        store.save(state)
        self.assertIsNone(store.load("expired"))

    def test_resume_claim_is_atomic_and_stale_claim_can_recover(self):
        store = self.make_store()
        state = PipelineState("test", "claim", owner_id="u", status="awaiting_human")
        store.save(state)
        claimed = store.claim_resume("claim", state.continuation_token, "u")
        self.assertEqual("resuming", claimed["status"])
        with self.assertRaises(ValueError):
            store.claim_resume("claim", state.continuation_token, "u")

        with store._connect() as connection:
            connection.execute(
                "UPDATE pipeline_states SET updated_at = ? WHERE session_id = ?",
                (time.time() - store.resume_lease_seconds - 1, "claim"),
            )
        recovered = store.claim_resume("claim", state.continuation_token, "u")
        self.assertEqual("resuming", recovered["status"])


if __name__ == "__main__":
    unittest.main()
