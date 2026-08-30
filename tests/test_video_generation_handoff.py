import asyncio
import copy
import tempfile
import unittest
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.codex_video_runner import (
    _apply_caption_packaging,
    _generation_handoff,
    _plan_has_caption_packaging,
    _remotion_handoff_from_plan,
    _review_summary,
    _wants_caption_packaging,
    _wants_no_music,
    _wants_voiceover,
)
from univa.mcp_tools import video_gen


def _sample_plan():
    return {
        "target_duration_seconds": 5,
        "aspect_ratio": "9:16",
        "research_summary": {
            "visual_reference_anchors": ["steel-blue background", "sharp pasta texture"],
            "avoid_due_to_research": ["warm soft light", "watermark"],
        },
        "preliminary_video_info": {
            "objective": "Show the pasta texture directly",
            "hard_constraints": ["5 seconds", "9:16", "no music"],
            "style_direction": "hard, cold, high-contrast food photography",
        },
        "initial_storyboard": [
            {"shot_id": "shot_01", "rough_beat": "fork lifts pasta", "tentative_duration_seconds": 5}
        ],
        "style_anchors": {
            "visual_style": "cold commercial food photography",
            "lighting": "hard cool side backlight",
            "color_palette": "steel blue, charcoal, cool gray",
            "camera_language": "macro locked push-in",
        },
        "shots": [
            {
                "id": "shot_01",
                "duration_seconds": 5,
                "generation_unit_id": "unit_01",
                "scene_id": "scene_01",
                "narrative_role": "hero food reveal",
                "scene_blueprint": "pasta on a black plate",
                "camera_motion": "stable macro push-in",
                "background": "steel-blue geometric set",
                "start_state": "pasta rests on plate",
                "end_state": "fork holds pasta in a hero frame",
                "continuity_anchor": "same plate, sauce, light, and camera axis",
                "duplicate_guard": "single generation unit",
                "visual_logic": {
                    "link_from_previous": "opening",
                    "composition_change": "plate to lifted noodles",
                    "link_to_next": "final shot",
                },
                "prompt_components": {
                    "subject": "tomato basil spaghetti",
                    "subject_motion": "fork lifts noodles while parmesan falls",
                    "scene": "black plate on a cool-gray table",
                    "spatial": "pasta foreground, fork midground, steel-blue background",
                    "camera": "100mm macro, shallow depth of field",
                    "atmosphere": "cold and direct",
                    "stylization": "high-contrast commercial photography",
                    "negative_constraints": "no people, text, logo, watermark, or music",
                },
                "expanded_generation_prompt": (
                    "A detailed five-second macro shot of tomato basil spaghetti on a black ceramic plate. "
                    "A fork lifts elastic noodles while parmesan falls and steam rises. The camera makes a "
                    "stable controlled push-in with shallow depth of field. Use hard cool side backlight, "
                    "steel-blue and charcoal surroundings, crisp sauce highlights, deep shadows, and no "
                    "people, text, logos, watermark, soft warm light, narration, or music."
                ),
                "generation_tool": "text2video_gen",
                "negative_constraints": "no people, text, logo, watermark, or music",
            }
        ],
        "transitions": [],
        "execution_plan": [
            {"step": 1, "tool": "text2video_gen", "shot_id": "shot_01", "duration_seconds": 5}
        ],
        "quality_checks": ["style and continuity are consistent"],
    }


class GenerationContractTests(unittest.TestCase):
    def test_reviewed_prompt_is_complete_and_equals_handoff_prompt(self):
        plan = video_gen._normalize_video_plan_durations(_sample_plan(), requested_total_duration=5)
        verification = video_gen._verify_generation_contracts(plan)
        self.assertTrue(verification["ready_for_generation"], verification)

        shot = plan["shots"][0]
        prompt = shot["expanded_generation_prompt"]
        self.assertIn(video_gen.GENERATION_CONTRACT_HEADER, prompt)
        self.assertIn("steel-blue background", prompt)
        self.assertIn("hard cool side backlight", prompt)
        self.assertIn("initial_storyboard", prompt)
        self.assertIn("duration_seconds", prompt)
        self.assertIn('"aspect_ratio":"9:16"', prompt)

        handoff = _generation_handoff(plan)
        review = _review_summary(plan)
        self.assertEqual(prompt, handoff["requests"][0]["prompt"])
        self.assertEqual(prompt, review[0]["expanded_generation_prompt"])
        self.assertEqual(prompt, review[0]["provider_request_preview"]["prompt"])
        self.assertEqual(5, handoff["requests"][0]["duration_seconds"])
        self.assertEqual("9:16", handoff["requests"][0]["aspect_ratio"])

    def test_plan_mutation_after_review_is_blocked(self):
        plan = video_gen._normalize_video_plan_durations(_sample_plan(), requested_total_duration=5)
        plan["style_anchors"]["lighting"] = "unauthorized warm soft light"
        verification = video_gen._verify_generation_contracts(plan)
        self.assertFalse(verification["ready_for_generation"])
        self.assertTrue(any("changed" in issue["problem"] for issue in verification["issues"]))

    def test_text2video_passes_exact_prompt_duration_and_aspect_ratio(self):
        captured = {}

        def fake_ark(api_key, prompt, **kwargs):
            captured.update({"prompt": prompt, **kwargs})
            return {"success": True, "output_path": "/tmp/fake-video.mp4"}

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.object(video_gen, "ark_text_to_video", side_effect=fake_ark), patch.object(
                video_gen, "_univa_path", side_effect=lambda value: str(Path(tmpdir) / value)
            ):
                result = asyncio.run(
                    video_gen.text2video_gen(
                        prompt="EXACT REVIEWED PROMPT",
                        duration_seconds=5,
                        aspect_ratio="9:16",
                        auto_audio=False,
                    )
                )

        self.assertEqual("EXACT REVIEWED PROMPT", captured["prompt"])
        self.assertEqual(5, captured["duration"])
        self.assertEqual("9:16", captured["aspect_ratio"])
        self.assertEqual("EXACT REVIEWED PROMPT", result["generation_request"]["prompt"])

    def test_auto_audio_preserves_native_video_api_audio(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            video_path = Path(tmpdir) / "native.mp4"
            video_path.write_bytes(b"video")
            with patch.object(video_gen, "has_audio_stream", return_value=True), patch.object(
                video_gen, "plan_audio_tool"
            ) as plan_audio:
                output_path, meta = video_gen._attach_auto_audio(str(video_path), "cinematic car promo", auto_audio=True)

        self.assertEqual(str(video_path), output_path)
        self.assertEqual("video_api_native", meta["audio_source"])
        plan_audio.assert_not_called()

    def test_auto_audio_uses_ffmpeg_fallback_after_audio_api_failure(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            video_path = Path(tmpdir) / "silent.mp4"
            video_path.write_bytes(b"video")

            def fake_run(cmd, **kwargs):
                Path(cmd[-1]).write_bytes(b"video-with-audio")
                return SimpleNamespace(returncode=0, stderr="", stdout="")

            with patch.object(video_gen, "has_audio_stream", side_effect=[False, True]), patch.object(
                video_gen, "plan_audio_tool", return_value=SimpleNamespace(success=False, message="audio api unavailable")
            ), patch.object(video_gen.shutil, "which", return_value="/usr/bin/ffmpeg"), patch.object(
                video_gen.subprocess, "run", side_effect=fake_run
            ):
                output_path, meta = video_gen._attach_auto_audio(
                    str(video_path),
                    "red pickup truck racing through desert dust",
                    auto_audio=True,
                    include_bgm=True,
                    include_sfx=True,
                    target_duration_seconds=4,
                )

        self.assertTrue(output_path.endswith("_ffmpeg_audio.mp4"))
        self.assertEqual("ffmpeg_synthetic_fallback", meta["audio_source"])
        self.assertIn("audio api unavailable", meta["audio_errors"])

    def test_negative_audio_intent_is_not_misread(self):
        self.assertFalse(_wants_voiceover("无旁白或音乐，仅保留环境声"))
        self.assertTrue(_wants_no_music("无旁白或音乐，仅保留环境声"))

    def test_remotion_handoff_keeps_approved_plan_and_cli_overrides(self):
        plan = {
            "remotion_handoff": {
                "enabled": True,
                "reason": "captions and CTA need stable typography",
                "title": "Approved title",
                "brand": {"name": "Approved brand"},
            }
        }
        args = SimpleNamespace(
            remotion_compose=False,
            no_remotion=False,
            remotion_title="CLI title",
            remotion_subtitle=None,
            remotion_brand="CLI brand",
            remotion_browser_executable="/usr/bin/chromium",
            remotion_binaries_directory=None,
            no_remotion_ffmpeg_fallback=False,
        )

        handoff = _remotion_handoff_from_plan(plan, args)

        self.assertTrue(handoff["enabled"])
        self.assertEqual("captions and CTA need stable typography", handoff["reason"])
        self.assertEqual("CLI title", handoff["title"])
        self.assertEqual("CLI brand", handoff["brand"]["name"])
        self.assertEqual("/usr/bin/chromium", handoff["browser_executable_path"])

        args.no_remotion = True
        self.assertFalse(_remotion_handoff_from_plan(plan, args)["enabled"])

    def test_remotion_handoff_is_enabled_when_caption_plan_exists(self):
        plan = {
            "caption_plan": [
                {"text": "Title", "start_seconds": 0.2, "end_seconds": 1.2},
                {"text": "Body", "start_seconds": 1.2, "end_seconds": 3.2},
                {"text": "CTA", "start_seconds": 3.2, "end_seconds": 5.0},
            ]
        }
        args = SimpleNamespace(
            remotion_compose=False,
            no_remotion=False,
            remotion_title=None,
            remotion_subtitle=None,
            remotion_brand=None,
            remotion_browser_executable=None,
            remotion_binaries_directory=None,
            no_remotion_ffmpeg_fallback=False,
        )

        self.assertTrue(_plan_has_caption_packaging(plan))
        self.assertTrue(_remotion_handoff_from_plan(plan, args)["enabled"])

    def test_caption_packaging_is_injected_for_subtitle_requests(self):
        plan = {
            "target_duration_seconds": 5,
            "shots": [
                {
                    "id": "shot_01",
                    "duration_seconds": 5,
                    "scene_blueprint": "sleek electric sedan in the city",
                    "creative_generation_prompt": "A continuous 5-second cinematic shot of a sleek pure electric intelligent sedan cruising through a modern city at dusk.",
                    "expanded_generation_prompt": "A continuous 5-second cinematic shot of a sleek pure electric intelligent sedan cruising through a modern city at dusk.",
                }
            ],
        }
        args = SimpleNamespace(prompt="生成一个5s的商品广告宣传电车，动态感，配宣传字幕。", duration=5)

        result = _apply_caption_packaging(plan, args, approved_plan=False)

        self.assertTrue(_wants_caption_packaging(args.prompt))
        self.assertTrue(_plan_has_caption_packaging(result))
        self.assertEqual(3, len(result["caption_plan"]))
        self.assertTrue(result["remotion_handoff"]["enabled"])
        self.assertEqual("电感出发", result["caption_plan"][0]["text"])
        self.assertEqual("即刻预约体验", result["caption_plan"][-1]["text"])

    def test_caption_packaging_is_required_for_approved_subtitle_plans(self):
        plan = {"target_duration_seconds": 5, "shots": []}
        args = SimpleNamespace(prompt="生成一个5s的商品广告宣传电车，动态感，配宣传字幕。", duration=5)

        with self.assertRaises(RuntimeError):
            _apply_caption_packaging(plan, args, approved_plan=True)


if __name__ == "__main__":
    unittest.main()
