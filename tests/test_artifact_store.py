import tempfile
import unittest
from pathlib import Path

from univa.utils.artifact_store import ArtifactStore, content_sha256
from univa.utils.budget_tracker import BudgetTracker
from univa.utils.pipeline_orchestrator import PipelineOrchestrator, PipelineState


class _Loader:
    def validate_artifact_against_schema(self, name, value):
        return {"valid": True, "errors": []}


class _UsagePlanAgent:
    budget_tracker = None

    async def generate_plan(self, session_id, request):
        self.budget_tracker.record_llm_call(100, 20, stage="plan")
        return {
            "execution_plan": {
                "steps": [
                    {
                        "tool": {
                            "name": "text2video_gen",
                            "arguments": {"prompt": "approved prompt"},
                        }
                    }
                ]
            }
        }


class _UsageActAgent:
    budget_tracker = None

    async def execute_plan(self, request, plan):
        self.budget_tracker.record_llm_call(80, 10, stage="act")
        return {
            1: {
                "success": True,
                "media_result": {"status": "ready"},
                "actual_cost_usd": 0.3,
                "task_id": "provider-task-2",
                "provider": "provider-2",
                "model": "video-model-2",
                "duration_seconds": 5,
            }
        }


class _UsageSystem:
    def __init__(self):
        self.plan_agent = _UsagePlanAgent()
        self.act_agent = _UsageActAgent()


class ArtifactStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        root = Path(self.temp_dir.name) / "records"
        self.store = ArtifactStore(str(root), str(Path(self.temp_dir.name) / "index.db"))

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_artifact_hash_parent_and_version_are_durable(self):
        first = self.store.write_artifact("brief", {"title": "one"}, project_id="p", job_id="j")
        second = self.store.write_artifact(
            "brief", {"title": "two"}, project_id="p", job_id="j",
            parent_artifact_ids=[first["artifact_id"]],
        )
        self.assertEqual(1, first["version"])
        self.assertEqual(2, second["version"])
        self.assertEqual(content_sha256({"title": "one"}), first["content_sha256"])
        self.assertEqual([first["artifact_id"]], second["parent_artifact_ids"])
        self.assertEqual(first, self.store.get_artifact(first["artifact_id"]) | {"record_path": first["record_path"]})

    def test_receipt_hashes_existing_outputs(self):
        output = Path(self.temp_dir.name) / "output.bin"
        output.write_bytes(b"output")
        receipt = self.store.write_receipt({
            "job_id": "job",
            "operation_id": "operation-test",
            "input": {"prompt": "x"},
            "output_paths": [str(output)],
        })
        self.assertEqual(content_sha256({"prompt": "x"}), receipt["input_sha256"])
        self.assertEqual(str(output.resolve()), receipt["output_paths"][0]["path"])
        self.assertTrue(receipt["output_paths"][0]["sha256"])

    def test_receipt_is_append_only(self):
        first = self.store.write_receipt({
            "operation_id": "operation-fixed",
            "job_id": "job",
            "status": "success",
        })
        with self.assertRaises(ValueError):
            self.store.write_receipt({
                "operation_id": "operation-fixed",
                "job_id": "job",
                "status": "failed",
            })
        self.assertEqual(first, self.store.get_receipt("operation-fixed"))

    def test_missing_declared_output_blocks_quality_gate(self):
        orchestrator = PipelineOrchestrator(_Loader(), artifact_store=self.store)
        state = PipelineState("test", "job", budget=BudgetTracker())
        report = orchestrator._run_quality_gate(
            {"name": "proposal", "produces": ["required_plan"]},
            state,
            {"plan": {"other": "value"}},
        )
        self.assertEqual("BLOCKED", report["decision"])
        self.assertIn("required_plan", report["failures"][0])

    def test_alternative_outputs_require_at_least_one(self):
        orchestrator = PipelineOrchestrator(_Loader(), artifact_store=self.store)
        state = PipelineState("test", "job", budget=BudgetTracker())
        passed = orchestrator._run_quality_gate(
            {"name": "proposal", "produces_any": [["media_plan", "edit_proposal"]]},
            state,
            {"media_plan": {"approval_required": True}},
        )
        failed = orchestrator._run_quality_gate(
            {"name": "proposal", "produces_any": [["media_plan", "edit_proposal"]]},
            state,
            {"plan": {}},
        )
        self.assertEqual("PASS", passed["decision"])
        self.assertEqual("BLOCKED", failed["decision"])

    def test_tool_receipt_captures_provider_task_and_output_hash(self):
        output = Path(self.temp_dir.name) / "tool-output.mp4"
        output.write_bytes(b"video")
        orchestrator = PipelineOrchestrator(_Loader(), artifact_store=self.store)
        state = PipelineState("test", "job", budget=BudgetTracker())
        records = orchestrator._record_stage_artifacts(
            state,
            {"name": "generate", "produces": ["media_result"]},
            {
                "media_result": {"output_path": str(output)},
                "plan": {"execution_plan": {"steps": [{"tool": {"name": "text2video_gen", "arguments": {"prompt": "x"}}}]}},
                "execution_results": {1: {"success": True, "output_path": str(output), "task_id": "provider-1", "model": "model-1"}},
            },
            "request",
            {"decision": "PASS"},
        )
        receipt = records["tool_execution_receipts"][0]
        self.assertEqual("text2video_gen", receipt["tool_name"])
        self.assertEqual("provider-1", receipt["provider_task_id"])
        self.assertTrue(receipt["output_paths"][0]["sha256"])

    def test_artifact_and_stage_receipt_include_effective_stage_cost(self):
        orchestrator = PipelineOrchestrator(_Loader(), artifact_store=self.store)
        budget = BudgetTracker(model="test-model")
        budget.record_llm_call(tokens_in=100, tokens_out=20, stage="generate")
        budget.record_tool_call(
            "text2video_gen",
            3.0,
            stage="generate",
            actual_cost_usd=0.25,
        )
        state = PipelineState("test", "job", budget=budget)
        records = orchestrator._record_stage_artifacts(
            state,
            {"name": "generate", "produces": ["media_result"]},
            {"media_result": {"status": "ready"}},
            "request",
            {"decision": "PASS"},
        )

        expected = budget.stage_breakdown()["generate"]
        expected_total = expected["llm_cost"] + expected["tool_cost"]
        self.assertAlmostEqual(expected_total, records["media_result"]["cost_usd"])
        self.assertAlmostEqual(
            expected_total, records["execution_receipt"]["estimated_cost_usd"]
        )
        self.assertAlmostEqual(
            0.25, records["execution_receipt"]["actual_tool_cost_usd"]
        )


class PipelineCostIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_execution_connects_provider_cost_to_budget_and_artifact(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "records"
            store = ArtifactStore(str(root), str(Path(temp_dir) / "index.db"))
            orchestrator = PipelineOrchestrator(_Loader(), artifact_store=store)
            state = PipelineState("test", "job", budget=BudgetTracker())

            result = await orchestrator._execute_stage(
                {
                    "name": "generate",
                    "tools_available": ["text2video_gen"],
                    "produces": ["media_result"],
                },
                state,
                "generate a video",
                _UsageSystem(),
            )

            self.assertEqual(
                ["generate", "generate"],
                [call.stage for call in state.budget.llm_calls],
            )
            tool_call = state.budget.tool_calls[0]
            self.assertAlmostEqual(0.3, tool_call.actual_cost_usd)
            self.assertEqual("provider-task-2", tool_call.provider_task_id)
            self.assertEqual("provider-2", tool_call.provider)
            expected = state.budget.stage_breakdown()["generate"]
            self.assertAlmostEqual(
                expected["llm_cost"] + expected["tool_cost"],
                result["artifact_records"]["media_result"]["cost_usd"],
            )


if __name__ == "__main__":
    unittest.main()
