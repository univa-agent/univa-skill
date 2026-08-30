import os
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

from univa.utils import image_upload
from univa.utils import volcengine_api as ark


class ArkVideoReferenceUploadTests(unittest.TestCase):
    def test_http_url_passes_through(self):
        with ark._ark_reference_video_url("https://cdn.example.test/input.mp4") as url:
            self.assertEqual(url, "https://cdn.example.test/input.mp4")

    def test_local_upload_service_returns_reference_video_url(self):
        with tempfile.TemporaryDirectory() as tmp:
            video = Path(tmp) / "input.mp4"
            video.write_bytes(b"fake video")
            with patch.object(image_upload, "upload_file", return_value="https://cdn.example.test/input.mp4") as mocked:
                with ark._ark_reference_video_url(str(video)) as url:
                    self.assertEqual(url, "https://cdn.example.test/input.mp4")
                mocked.assert_called_once_with(str(video), config_section="video_upload")

    def test_video_edit_payload_uses_reference_video_role_not_base64(self):
        captured = {}

        def fake_submit(base_url, api_key, payload):
            captured["payload"] = payload
            return "task-test", None

        with patch.object(ark, "_submit_generation", side_effect=fake_submit), \
             patch.object(ark, "_poll_generation", return_value={"content": {"video_url": "https://cdn.example.test/out.mp4"}}), \
             patch.object(ark, "_download_video", return_value=True):
            result = ark.video_edit_generate("key", "make warm", "https://cdn.example.test/input.mp4", save_path="/tmp/out.mp4")

        self.assertTrue(result["success"], result)
        video_item = captured["payload"]["content"][1]
        self.assertEqual(video_item["type"], "video_url")
        self.assertEqual(video_item["role"], "reference_video")
        self.assertEqual(video_item["video_url"]["url"], "https://cdn.example.test/input.mp4")
        self.assertNotIn("base64", video_item["video_url"]["url"])

    def test_cloudflare_tunnel_provider_keeps_transport_during_submit_and_poll(self):
        events = []
        captured = {}

        @contextmanager
        def fake_tunnel(video_path, upload_config):
            events.append("enter")
            yield "https://demo.trycloudflare.com/input.mp4"
            events.append("exit")

        def fake_submit(base_url, api_key, payload):
            events.append("submit")
            captured["payload"] = payload
            return "task-test", None

        def fake_poll(base_url, api_key, task_id):
            events.append("poll")
            return {"content": {"video_url": "https://cdn.example.test/out.mp4"}}

        with tempfile.TemporaryDirectory() as tmp:
            video = Path(tmp) / "input.mp4"
            video.write_bytes(b"fake video")
            with patch.dict(os.environ, {"VIDEO_UPLOAD_PROVIDER": "cloudflare_tunnel"}), \
                 patch.object(ark, "_cloudflare_tunnel_reference_video_url", side_effect=fake_tunnel), \
                 patch.object(ark, "_submit_generation", side_effect=fake_submit), \
                 patch.object(ark, "_poll_generation", side_effect=fake_poll), \
                 patch.object(ark, "_download_video", return_value=True):
                result = ark.video_edit_generate("key", "make warm", str(video), save_path="/tmp/out.mp4")

        self.assertTrue(result["success"], result)
        self.assertEqual(events, ["enter", "submit", "poll", "exit"])
        self.assertEqual(captured["payload"]["content"][1]["role"], "reference_video")


if __name__ == "__main__":
    unittest.main()
