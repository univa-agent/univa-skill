import subprocess
import tempfile
import unittest
from pathlib import Path

from univa.utils.media_index import MediaIndex


class MediaIndexTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        root = Path(self.temp_dir.name) / "index"
        self.index = MediaIndex(str(root), str(root / "index.db"))
        self.video = Path(self.temp_dir.name) / "sample.mp4"
        subprocess.run([
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "lavfi",
            "-i", "color=c=red:s=160x90:r=10", "-t", "2", "-pix_fmt", "yuv420p",
            "-y", str(self.video),
        ], check=True)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_index_creates_timecoded_segments_and_reuses_unchanged_media(self):
        result = self.index.index_video(str(self.video), segment_duration_seconds=1)
        self.assertTrue(result["success"])
        self.assertEqual(2, len(result["segments"]))
        self.assertEqual(0.0, result["segments"][0]["start_seconds"])
        self.assertTrue(Path(result["segments"][0]["thumbnail_path"]).is_file())
        reused = self.index.index_video(str(self.video), segment_duration_seconds=1)
        self.assertTrue(reused["reused"])
        self.assertEqual(result["index_id"], reused["index_id"])

    def test_search_and_time_range_lookup_return_exact_ranges(self):
        indexed = self.index.index_video(str(self.video), segment_duration_seconds=1)
        enriched = self.index.enrich_segments(str(self.video), [
            {
                "start_seconds": 0,
                "end_seconds": 2,
                "caption": "red train",
                "keywords": ["train", "red"],
            }
        ])
        self.assertEqual(2, enriched["segments_updated"])
        matches = self.index.search("train", str(self.video), top_k=3)
        self.assertTrue(matches["success"])
        self.assertEqual(2, len(matches["segments"]))
        self.assertFalse(matches["semantic_search"])
        moment = self.index.get_moment(str(self.video), 0.5, 1.5)
        self.assertEqual(2, len(moment["segments"]))

    def test_enrichment_requires_an_existing_index_and_valid_annotations(self):
        other = Path(self.temp_dir.name) / "other.mp4"
        other.write_bytes(self.video.read_bytes())
        with self.assertRaisesRegex(ValueError, "not indexed"):
            self.index.enrich_segments(str(other), [{
                "start_seconds": 0,
                "end_seconds": 1,
                "caption": "test",
            }])
        self.index.index_video(str(self.video), segment_duration_seconds=1)
        with self.assertRaisesRegex(ValueError, "invalid time range"):
            self.index.enrich_segments(str(self.video), [{
                "start_seconds": 1,
                "end_seconds": 0,
                "caption": "test",
            }])

    def test_invalid_media_has_explicit_failure(self):
        with self.assertRaises(FileNotFoundError):
            self.index.index_video(str(Path(self.temp_dir.name) / "missing.mp4"))


if __name__ == "__main__":
    unittest.main()
