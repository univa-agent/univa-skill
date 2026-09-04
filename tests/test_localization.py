import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from univa.utils.localization import (
    bilingual_cues,
    normalize_cues,
    parse_captions,
    transcribe_media,
    translate_cues,
    write_srt,
    write_vtt,
)
from univa.utils.skill_loader import SkillLoader


class LocalizationTests(unittest.TestCase):
    def setUp(self):
        self.cues = [
            {"id": "1", "start_seconds": 0, "end_seconds": 1.2, "text": "Hello"},
            {"id": "2", "start_seconds": 1.2, "end_seconds": 2.5, "text": "World"},
        ]

    def test_srt_and_vtt_round_trip(self):
        self.assertEqual(self.cues, parse_captions(write_srt(self.cues)))
        self.assertEqual(self.cues, parse_captions(write_vtt(self.cues)))

    def test_overlap_repair_and_bilingual_layout(self):
        overlapping = [
            {"id": "1", "start_seconds": 0, "end_seconds": 2, "text": "A"},
            {"id": "2", "start_seconds": 1, "end_seconds": 3, "text": "B"},
        ]
        repaired = normalize_cues(overlapping)
        self.assertLessEqual(repaired[0]["end_seconds"], repaired[1]["start_seconds"])
        bilingual = bilingual_cues(self.cues, [
            {"id": "1", "start_seconds": 0, "end_seconds": 1.2, "text": "你好"},
            {"id": "2", "start_seconds": 1.2, "end_seconds": 2.5, "text": "世界"},
        ])
        self.assertEqual("Hello\n你好", bilingual[0]["text"])

    def test_translation_preserves_ids_count_and_timing(self):
        def translator(cues, target, source):
            return [{"id": cue["id"], "text": f"ZH:{cue['text']}"} for cue in cues]

        result = translate_cues(self.cues, "zh-CN", translator, "en")
        self.assertTrue(result["success"])
        self.assertEqual(["1", "2"], [cue["id"] for cue in result["captions"]])
        self.assertEqual(1.2, result["captions"][0]["end_seconds"])

        invalid = translate_cues(self.cues, "zh-CN", lambda cues, target, source: [], "en")
        self.assertFalse(invalid["success"])

    def test_missing_asr_backend_is_explicit(self):
        with tempfile.NamedTemporaryFile(suffix=".wav") as source:
            with patch("univa.utils.localization.importlib.util.find_spec", return_value=None):
                result = transcribe_media(source.name)
        self.assertFalse(result["success"])
        self.assertEqual("backend_unavailable", result["error_code"])

    def test_localization_pipeline_and_skill_are_discoverable(self):
        loader = SkillLoader(project_root=".")
        pipeline = loader.load_pipeline("localization")
        self.assertEqual(
            ["preflight", "transcribe", "translate", "confirm", "voiceover", "render", "locale_qa", "deliver"],
            [stage["name"] for stage in pipeline["stages"]],
        )
        self.assertTrue(pipeline["stages"][3]["human_approval_default"])
        matched = loader._fallback_skill_match("为这个视频制作双语字幕并配音")
        self.assertIn("core/localization", matched)


if __name__ == "__main__":
    unittest.main()
