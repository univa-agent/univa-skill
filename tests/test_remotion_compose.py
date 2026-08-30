import asyncio
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from univa.mcp_tools import video_gen


class RemotionComposeTests(unittest.TestCase):
    def test_normalizes_caption_segments_and_word_timings(self):
        captions = video_gen._normalize_remotion_captions(
            [
                {"text": "Opening line", "start_seconds": 1, "end_seconds": 2.5},
                {"words": [{"word": "UniVA", "startMs": 2600, "endMs": 3100}]},
                {"text": "bad", "start_seconds": "nope"},
            ]
        )

        self.assertEqual(
            captions,
            [
                {"text": "Opening line", "startSeconds": 1.0, "endSeconds": 2.5},
                {"text": "UniVA", "startSeconds": 2.6, "endSeconds": 3.1},
            ],
        )

    def test_normalizes_overlays_to_supported_shape(self):
        overlays = video_gen._normalize_remotion_overlays(
            [
                {
                    "type": "unknown",
                    "title": "Launch message",
                    "in_seconds": 2,
                    "out_seconds": 1,
                    "position": "unsupported",
                    "stat": "3x",
                }
            ]
        )

        self.assertEqual(overlays[0]["type"], "lower_third")
        self.assertEqual(overlays[0]["position"], "lower_left")
        self.assertEqual(overlays[0]["text"], "Launch message")
        self.assertEqual(overlays[0]["startSeconds"], 2.0)
        self.assertEqual(overlays[0]["endSeconds"], 5.0)
        self.assertEqual(overlays[0]["value"], "3x")

    def test_remotion_render_passes_timeout_and_writes_props(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir) / "packages" / "remotion-compose"
            (root / "node_modules").mkdir(parents=True)
            (root / "package.json").write_text("{}", encoding="utf-8")
            input_video = Path(tmpdir) / "input.mp4"
            input_video.write_bytes(b"video")
            output_video = Path(tmpdir) / "out.mp4"
            browser = Path(tmpdir) / "chrome"
            browser.write_text("#!/bin/sh\n", encoding="utf-8")
            browser.chmod(0o755)
            binaries_dir = Path(tmpdir) / "compositor"
            binaries_dir.mkdir()
            (binaries_dir / "remotion").write_text("#!/bin/sh\n", encoding="utf-8")
            captured = {}

            def fake_run(cmd, **kwargs):
                if cmd[:2] == ["ffprobe", "-v"] and "format=duration" in cmd:
                    return subprocess.CompletedProcess(cmd, 0, stdout="4.2\n", stderr="")
                if cmd[:2] == ["ffprobe", "-v"] and "stream=width,height" in cmd:
                    return subprocess.CompletedProcess(cmd, 0, stdout="1280x720\n", stderr="")
                captured["cmd"] = cmd
                captured["kwargs"] = kwargs
                output_video.write_bytes(b"rendered")
                return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

            with patch.object(video_gen, "UNIVA_ROOT", Path(tmpdir)), patch.object(
                video_gen, "_remotion_binary", return_value="npx"
            ), patch.object(video_gen.subprocess, "run", side_effect=fake_run):
                result = video_gen._remotion_render(
                    str(input_video),
                    str(output_video),
                    title="Title",
                    captions=[{"text": "Hi", "start_seconds": 0, "end_seconds": 1}],
                    browser_executable_path=str(browser),
                    remotion_binaries_directory=str(binaries_dir),
                    remotion_timeout_ms=120000,
                )

            self.assertTrue(result.success, result)
            self.assertIn(f"--browser-executable={browser}", captured["cmd"])
            self.assertIn(f"--binaries-directory={binaries_dir.resolve()}", captured["cmd"])
            self.assertIn("--timeout=120000", captured["cmd"])
            self.assertIn(str(binaries_dir.resolve()), captured["kwargs"]["env"].get("LD_LIBRARY_PATH", ""))
            self.assertIn("--duration=126", captured["cmd"])
            props_arg = next(item for item in captured["cmd"] if item.startswith("--props="))
            props_path = root / props_arg.removeprefix("--props=")
            self.assertTrue(props_path.exists())
            self.assertEqual(str(output_video.resolve()), result.output_path)

    def test_discovers_installed_chrome_when_not_requested(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            browser = Path(tmpdir) / "google-chrome"
            browser.write_text("#!/bin/sh\n", encoding="utf-8")
            browser.chmod(0o755)

            def fake_which(name):
                return str(browser) if name == "google-chrome" else None

            with patch.object(video_gen.shutil, "which", side_effect=fake_which):
                self.assertEqual(str(browser), video_gen._remotion_browser_executable())

    def test_prefers_musl_compositor_on_old_glibc_hosts(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir) / "packages" / "remotion-compose"
            (root / "node_modules").mkdir(parents=True)
            (root / "package.json").write_text("{}", encoding="utf-8")
            gnu = Path(tmpdir) / "node_modules" / ".bun" / "node_modules" / "@remotion" / "compositor-linux-x64-gnu"
            musl = Path(tmpdir) / "node_modules" / ".bun" / "node_modules" / "@remotion" / "compositor-linux-x64-musl"
            gnu.mkdir(parents=True)
            musl.mkdir(parents=True)
            (gnu / "remotion").write_text("#!/bin/sh\n", encoding="utf-8")
            (musl / "remotion").write_text("#!/bin/sh\n", encoding="utf-8")

            with patch.object(video_gen, "UNIVA_ROOT", Path(tmpdir)), patch.object(
                video_gen, "_host_libc_version_tuple", return_value=("glibc", (2, 31))
            ):
                self.assertEqual(str(musl.resolve()), video_gen._remotion_binaries_directory(root))

    def test_remotion_failure_hint_mentions_musl_zlib_symbols(self):
        hint = video_gen._remotion_failure_hint("zlibCompileFlags symbol not found deflateInit_ symbol not found")
        self.assertIn("zlib symbols", hint)
        self.assertIn("FFmpeg subtitle fallback", hint)

    def test_remotion_failure_falls_back_to_ffmpeg_ass_subtitles(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir) / "packages" / "remotion-compose"
            (root / "node_modules").mkdir(parents=True)
            (root / "package.json").write_text("{}", encoding="utf-8")
            input_video = Path(tmpdir) / "input.mp4"
            input_video.write_bytes(b"video")
            output_video = Path(tmpdir) / "out.mp4"
            run_commands = []

            def fake_run(cmd, **kwargs):
                run_commands.append(cmd)
                if cmd[:2] == ["ffprobe", "-v"] and "format=duration" in cmd:
                    return subprocess.CompletedProcess(cmd, 0, stdout="5.0\n", stderr="")
                if cmd[:2] == ["ffprobe", "-v"] and "stream=width,height" in cmd:
                    return subprocess.CompletedProcess(cmd, 0, stdout="1280x720\n", stderr="")
                if "render" in cmd:
                    return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="GLIBC_2.35 not found")
                if cmd[:2] == ["ffmpeg", "-y"]:
                    output_video.write_bytes(b"fallback")
                    return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
                return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="unexpected")

            with patch.object(video_gen, "UNIVA_ROOT", Path(tmpdir)), patch.object(
                video_gen, "_remotion_binary", return_value="npx"
            ), patch.object(video_gen.subprocess, "run", side_effect=fake_run):
                result = video_gen._remotion_render(
                    str(input_video),
                    str(output_video),
                    captions=[{"text": "必杀！", "start_seconds": 1.0, "end_seconds": 2.0}],
                    fallback_to_ffmpeg_subtitles=True,
                )

            self.assertTrue(result.success, result)
            self.assertEqual("ffmpeg_ass_subtitle_fallback", result.content["method"])
            self.assertTrue(result.content["remotion_attempted"])
            self.assertIn("GLIBC_2.35", result.content["remotion_error"])
            self.assertTrue(output_video.exists())
            self.assertTrue(any(cmd[:2] == ["ffmpeg", "-y"] for cmd in run_commands))

    def test_merge_uses_remotion_output_when_requested(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            merged = Path(tmpdir) / "merged.mp4"
            merged.write_bytes(b"merged")
            remotion = Path(tmpdir) / "merged_remotion.mp4"
            remotion.write_bytes(b"remotion")

            captured_remotion_kwargs = {}

            def fake_remotion(*args, **kwargs):
                captured_remotion_kwargs.update(kwargs)
                return video_gen.ToolResponse(
                    success=True,
                    output_path=str(remotion),
                    content={"method": "remotion"},
                )

            with patch.object(video_gen, "_univa_path", side_effect=lambda value: str(Path(tmpdir) / value)), patch.object(
                video_gen, "_merge_generated_videos", return_value=str(merged)
            ), patch.object(video_gen, "_attach_auto_audio", return_value=(str(merged), None)), patch.object(
                video_gen, "_remotion_render", side_effect=fake_remotion
            ):
                result = asyncio.run(
                    video_gen.merge2videos(
                        ["a.mp4", "b.mp4"],
                        auto_audio=False,
                        remotion_compose=True,
                        remotion_title="Launch",
                        remotion_binaries_directory="/tmp/remotion-bin",
                        remotion_fallback_to_ffmpeg_subtitles=True,
                    )
                )

            self.assertTrue(result.success)
            self.assertEqual(str(remotion), result.output_path)
            self.assertTrue(result.content["remotion_compose"]["success"])
            self.assertEqual("/tmp/remotion-bin", captured_remotion_kwargs["remotion_binaries_directory"])
            self.assertTrue(captured_remotion_kwargs["fallback_to_ffmpeg_subtitles"])


if __name__ == "__main__":
    unittest.main()
