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
