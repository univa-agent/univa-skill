import unittest
from pathlib import Path

from univa.utils.skill_loader import SkillLoader


class ExternalAgentGuidanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = Path(__file__).resolve().parents[1]
        cls.loader = SkillLoader(project_root=str(cls.root))

    def test_faster_whisper_is_declared_for_full_and_portable_runtime(self):
        for filename in ("requirements.txt", "requirements.runtime.txt"):
            lines = {
                line.strip()
                for line in (self.root / filename).read_text(encoding="utf-8").splitlines()
            }
            self.assertIn("faster-whisper==1.2.1", lines, filename)

    def test_asr_sidecar_request_routes_to_localization_not_video_generation(self):
        matched = self.loader._fallback_skill_match(
            "对这个视频做ASR转写并生成SRT字幕"
        )
        self.assertIn("core/localization", matched)
        self.assertIn("pipelines/localization/executive-producer", matched)
        self.assertNotIn("core/wavespeed-video-gen", matched)

    def test_new_video_with_localized_captions_keeps_both_capabilities(self):
        matched = self.loader._fallback_skill_match(
            "生成一个带双语字幕的产品宣传视频"
        )
        self.assertIn("core/localization", matched)
        self.assertIn("core/wavespeed-video-gen", matched)

    def test_timecoded_search_routes_to_media_index(self):
        matched = self.loader._fallback_skill_match(
            "检索这个长视频中出现火车的时间段"
        )
        self.assertIn("core/media-index", matched)
        self.assertIn("meta/understand-pipeline", matched)
        self.assertNotIn("core/wavespeed-video-gen", matched)

    def test_checkpoint_and_provenance_prompts_route_to_protocols(self):
        checkpoint = self.loader._fallback_skill_match(
            "恢复上次暂停的任务并继续执行"
        )
        provenance = self.loader._fallback_skill_match(
            "查看产物版本、执行回执、成本记录和来源记录"
        )
        self.assertIn("meta/checkpoint-protocol", checkpoint)
        self.assertIn("meta/artifact-provenance", checkpoint)
        self.assertIn("meta/artifact-provenance", provenance)

    def test_layer2_exposes_localization_tool_contract(self):
        context = self.loader.load_layer2_skills(
            "对这个视频做ASR转写并生成SRT字幕"
        )
        self.assertIn("### core/localization", context)
        self.assertIn("## Tool Contracts", context)
        self.assertIn("transcribe_media", context)
        self.assertIn("## External Agent Execution", context)

    def test_layer2_exposes_media_index_sequence_and_provenance_rules(self):
        index_context = self.loader.load_layer2_skills(
            "检索这个长视频中出现火车的时间段"
        )
        provenance_context = self.loader.load_layer2_skills(
            "查看产物版本、执行回执、成本记录和来源记录"
        )
        self.assertIn("### core/media-index", index_context)
        self.assertIn("update_video_index_segments", index_context)
        self.assertIn("semantic_search", index_context)
        self.assertIn("### meta/artifact-provenance", provenance_context)
        self.assertIn("Execution receipts are append-only", provenance_context)

    def test_external_agent_guides_reference_specialized_skills(self):
        paths = [
            "AGENTS.md",
            "CLAUDE.md",
            "skills/agent-integrations/codex-univa-video-ops/SKILL.md",
            "skills/agent-integrations/claude-code-univa-video-ops/SKILL.md",
            "skills/agent-integrations/univa-external-agent-bridge/SKILL.md",
        ]
        for relative_path in paths:
            content = (self.root / relative_path).read_text(encoding="utf-8")
            self.assertIn("localization", content.lower(), relative_path)
            self.assertIn("media-index", content, relative_path)
            self.assertIn("artifact-provenance", content, relative_path)


if __name__ == "__main__":
    unittest.main()
