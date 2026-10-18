import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app import media


class MediaTests(unittest.TestCase):
    def test_captions_cover_duration_in_two_short_lines(self):
        text = "We review the exact words and preserve the approved narration in a vertical video with approximate captions."
        cues = media.captions(text, 14.57)
        self.assertEqual(cues[0][0], 0)
        self.assertEqual(cues[-1][1], 14570)
        self.assertEqual(" ".join(body.replace("\n", " ") for _, _, body in cues), text)
        for index, (start, end, body) in enumerate(cues):
            self.assertLess(start, end)
            self.assertLessEqual(len(body.splitlines()), 2)
            self.assertTrue(all(len(line) <= 32 for line in body.splitlines()))
            if index:
                self.assertEqual(cues[index - 1][1], start)

    def test_ass_uses_explicit_portrait_canvas_and_neutralizes_style_injection(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "captions.ass"
            media.write_ass(path, r"Plain {\\b1} words should remain readable.", 4, 1080, 1920)
            text = path.read_text(encoding="utf-8")
            self.assertIn("PlayResX: 1080", text)
            self.assertIn("PlayResY: 1920", text)
            self.assertNotIn(r"{\\b1}", text)

    def test_disk_cap_is_enforced_before_media_work(self):
        with tempfile.TemporaryDirectory() as tmp:
            scratch = Path(tmp) / "scratch"
            scratch.mkdir()
            with patch.dict("os.environ", {"MAX_RENDER_DISK_GB": "0"}):
                with self.assertRaisesRegex(media.MediaError, "budget"):
                    media.disk_guard(scratch, reserve=1)

    def test_tool_errors_do_not_expose_narration_or_paths(self):
        with patch.object(media.subprocess, "run") as run:
            run.return_value.returncode = 1
            run.return_value.stderr = "SECRET narration at private path"
            with self.assertRaises(media.MediaError) as raised:
                media.run(["ffmpeg"])
            self.assertNotIn("SECRET", str(raised.exception))

    def test_oversized_word_fails_with_clear_caption_error(self):
        with self.assertRaisesRegex(media.MediaError, "32 characters"):
            media.captions("x" * 33, 2)

    def test_weighted_scene_frames_cover_all_audio_without_zero_length_scenes(self):
        for frames, weights in [(1500, [1, 2, 1]), (6, [0.25, 10, 1]), (101, [1] * 24)]:
            counts = media.allocate_scene_frames(frames, weights)
            self.assertEqual(sum(counts), frames)
            self.assertTrue(all(count >= 1 for count in counts))
        counts = media.allocate_scene_frames(1500, [1, 2, 1])
        self.assertLessEqual(abs(counts[1] - 2 * counts[0]), 2)

    def test_invalid_timing_or_too_many_scenes_reports_actionable_error(self):
        for frames, weights in [(2, [1, 1, 1]), (50, [0, 1]), (50, [float("nan")]), (50, [])]:
            with self.assertRaises(media.MediaError):
                media.allocate_scene_frames(frames, weights)

    def test_unknown_motion_is_rejected(self):
        with self.assertRaisesRegex(media.MediaError, "motion"):
            media.scene_filter(720, 1280, 25, "unsafe-filter")
