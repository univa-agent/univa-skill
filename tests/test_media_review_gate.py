import unittest
from types import SimpleNamespace

from univa.utils.pipeline_orchestrator import PipelineOrchestrator
from univa.utils.skill_loader import SkillLoader


class _FakePlanAgent:
    def __init__(self):
        self.agent = SimpleNamespace(model=SimpleNamespace(id="test-model"))
        self.budget_tracker = None
        self.calls = 0

    async def generate_plan(self, session_id, request):
        self.calls += 1
        return {
            "execution_plan": {"steps": []},
            "research_brief": {"status": "test"},
            "source_analysis": {"status": "not_needed"},
            "media_plan": {"approval_required": True},
            "edit_proposal": {},
            "media_plan_validation": {"status": "pass"},
            "media_plan_review": {"status": "awaiting_human"},
            "media_result": {"success": True},
            "media_quality_report": {"status": "pass"},
            "delivery_report": {"status": "test"},
        }


class _FakeActAgent:
    def __init__(self):
        self.budget_tracker = None
        self.calls = 0

    async def execute_plan(self, request, plan):
        self.calls += 1
        return {}


class _FakeSystem:
    def __init__(self):
        self.plan_agent = _FakePlanAgent()
        self.act_agent = _FakeActAgent()


class MediaReviewGateTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.loader = SkillLoader(project_root=".")

    def test_media_pipeline_and_skill_routes_are_registered(self):
        pipeline = self.loader.load_pipeline("media-atomic")
        self.assertIsNotNone(pipeline)
        self.assertEqual(
            ["analyze", "proposal", "confirm", "execute", "validate", "deliver"],
            [stage["name"] for stage in pipeline["stages"]],
        )
        self.assertTrue(pipeline["stages"][2]["human_approval_default"])

        cases = {
            "generate a product image": [
                "meta/media-review-gate",
                "meta/generate-pipeline",
                "core/wavespeed-image-gen",
            ],
            "generate background music": [
                "meta/media-review-gate",
                "meta/generate-pipeline",
                "core/audio-gen",
            ],
            "edit this image into watercolor style": [
                "meta/media-review-gate",
                "meta/edit-pipeline",
                "core/wavespeed-image-gen",
            ],
        }
        for prompt, required_skills in cases.items():
            loaded = self.loader._fallback_skill_match(prompt)
            for skill in required_skills:
                self.assertIn(skill, loaded, (prompt, loaded))

    def test_theme_skill_matching_for_generation_enhancement(self):
        self.assertEqual(
            ["themes/tech-product-review"],
            self.loader.find_theme_skills_for_task("生成一个科技产品评测开箱视频，突出参数和性能"),
        )

        self.assertEqual(
            ["themes/chinese-ink-guochao", "themes/product-advertising"],
            self.loader.find_theme_skills_for_task("做一个国潮水墨商品广告视频"),
        )

        self.assertEqual(
            [],
            self.loader.find_theme_skills_for_task("请分析这个视频的镜头结构"),
        )

        loaded = self.loader._fallback_skill_match("生成一个国潮水墨商品广告视频")
        self.assertLess(
            loaded.index("themes/chinese-ink-guochao"),
            loaded.index("meta/media-review-gate"),
        )
        self.assertLess(
            loaded.index("themes/product-advertising"),
            loaded.index("meta/media-review-gate"),
        )

    def test_theme_generation_context_influences_layer2_prompt_context(self):
        context = self.loader.build_theme_generation_context(
            "生成一个国潮水墨商品广告视频，突出新品卖点"
        )
        self.assertIn("Theme Generation Enhancement Context", context)
        self.assertIn("themes/chinese-ink-guochao", context)
        self.assertIn("themes/product-advertising", context)
        self.assertIn("留白", context)
        self.assertIn("行动号召", context)
        self.assertIn("theme_consistency_target: >= 0.8", context)

        layer2 = self.loader.load_layer2_skills(
            "生成一个国潮水墨商品广告视频，突出新品卖点"
        )
        self.assertIn("Theme Generation Enhancement Context", layer2)
        self.assertIn("## Generation Detail Expansion", layer2)
        self.assertIn("Final Prompt Influence", layer2)

    def test_all_theme_skills_have_generation_expansion_contract(self):
        theme_skills = self.loader.list_skills("themes")
        self.assertEqual(20, len(theme_skills))
        for skill_path in theme_skills:
            content = self.loader.load_skill(skill_path)
            self.assertIn("## Generation Detail Expansion", content, skill_path)
            self.assertIn("### Prompt Expansion Checklist", content, skill_path)
            self.assertIn("### Final Prompt Influence", content, skill_path)

    async def test_revision_replans_and_remains_paused_without_media_execution(self):
        orchestrator = PipelineOrchestrator(self.loader)
        system = _FakeSystem()

        state = await orchestrator.start(
            "media-atomic",
            "generate a test image",
            system,
            session_id="media-review-test",
        )
        self.assertEqual("awaiting_human", state.status)
        self.assertEqual("confirm", state.interaction_stage)

        act_calls_before_revision = system.act_agent.calls
        state = await orchestrator.resume(
            "make the palette warmer",
            system,
            "media-review-test",
        )

        self.assertEqual("awaiting_human", state.status)
        self.assertEqual("confirm", state.interaction_stage)
        self.assertFalse(state.artifacts["revision_request"]["confirmed"])
        self.assertEqual(act_calls_before_revision, system.act_agent.calls)


if __name__ == "__main__":
    unittest.main()
