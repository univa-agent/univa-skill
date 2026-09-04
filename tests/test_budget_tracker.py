import unittest

from univa.utils.budget_tracker import BudgetTracker


class BudgetTrackerTests(unittest.TestCase):
    def test_provider_cost_takes_precedence_over_estimate(self):
        tracker = BudgetTracker()
        tracker.record_tool_call(
            "text2video_gen",
            8.0,
            stage="generate",
            actual_cost_usd="$0.125",
            provider_task_id="task-1",
            provider="provider-1",
            model="video-model-1",
        )
        tracker.record_tool_call("image_gen", 2.0, stage="generate")

        self.assertAlmostEqual(0.135, tracker.tool_cost_usd)
        self.assertAlmostEqual(0.125, tracker.tool_actual_cost_usd)
        self.assertAlmostEqual(0.06, tracker.tool_estimated_cost_usd)
        self.assertAlmostEqual(0.01, tracker.tool_fallback_estimated_cost_usd)
        self.assertAlmostEqual(0.135, tracker.stage_breakdown()["generate"]["tool_cost"])

    def test_tool_billing_metadata_survives_round_trip(self):
        tracker = BudgetTracker(model="planner-model")
        tracker.record_tool_call(
            "text2video_gen",
            4.5,
            stage="render",
            actual_cost_usd=0.2,
            provider_task_id="provider-task",
            provider="wavespeed",
            model="provider-model",
        )

        restored = BudgetTracker.from_dict(tracker.to_dict())
        call = restored.tool_calls[0]
        self.assertEqual("provider-task", call.provider_task_id)
        self.assertEqual("wavespeed", call.provider)
        self.assertEqual("provider-model", call.model)
        self.assertAlmostEqual(0.2, call.actual_cost_usd)
        self.assertAlmostEqual(0.2, restored.tool_cost_usd)

    def test_invalid_actual_cost_falls_back_to_estimate(self):
        tracker = BudgetTracker()
        tracker.record_tool_call(
            "text2video_gen", 1.0, actual_cost_usd="not-a-number"
        )
        self.assertIsNone(tracker.tool_calls[0].actual_cost_usd)
        self.assertAlmostEqual(0.05, tracker.tool_cost_usd)

        tracker.record_tool_call("image_gen", 1.0, actual_cost_usd="nan")
        self.assertIsNone(tracker.tool_calls[1].actual_cost_usd)
        self.assertAlmostEqual(0.06, tracker.tool_cost_usd)


if __name__ == "__main__":
    unittest.main()
