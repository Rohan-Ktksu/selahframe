import base64
import io
import unittest
from unittest.mock import patch

from PIL import Image
from app import cinematic as g

RID = "11111111-1111-4111-8111-111111111111"


def image_bytes():
    b = io.BytesIO()
    Image.new("RGB", (32, 48), "green").save(b, "PNG")
    return b.getvalue()


class CinematicTests(unittest.TestCase):
    def test_success_uses_free_endpoint_and_inline_image_and_keeps_receipt(self):
        raw = image_bytes()
        with patch.object(
            g,
            "api",
            side_effect=[
                {"id": RID},
                {"done": True},
                {
                    "generations": [
                        {
                            "img": base64.b64encode(raw).decode(),
                            "model": "stable_diffusion",
                            "seed": "7",
                            "id": "g1",
                        }
                    ]
                },
            ],
        ) as call:
            original, jpg, receipt = g.request_image(
                "Public fixture", lambda *_: None, lambda: False, lambda _: None
            )
        self.assertEqual(original, raw)
        self.assertEqual(receipt["seed"], "7")
        self.assertEqual(Image.open(io.BytesIO(jpg)).format, "JPEG")
        payload = call.call_args_list[0].args[2]
        self.assertFalse(payload["r2"])
        self.assertTrue(payload["censor_nsfw"])
        self.assertEqual(payload["models"], ["stable_diffusion"])

    def test_remote_media_urls_and_censored_outputs_are_rejected(self):
        for generation in [{"img": "https://evil.test/private"}, {"img": "x", "censored": True}]:
            with patch.object(
                g,
                "api",
                side_effect=[{"id": RID}, {"done": True}, {"generations": [generation]}, {}],
            ) as call:
                with self.assertRaises(g.ImageError):
                    g.request_image("test", lambda *_: None, lambda: False, lambda _: None)
            self.assertEqual(call.call_args.args[:2], ("DELETE", "/generate/status/" + RID))

    def test_timeout_cancels_remote_job_without_resubmitting(self):
        with (
            patch.object(g, "api", side_effect=[{"id": RID}, {}]) as call,
            patch.object(g.time, "monotonic", side_effect=[0, 601]),
        ):
            with self.assertRaisesRegex(g.ImageError, "10 minutes"):
                g.request_image("test", lambda *_: None, lambda: False, lambda _: None)
        self.assertEqual(call.call_count, 2)
        self.assertEqual(call.call_args.args[0], "DELETE")

    def test_cancel_after_admission_cancels_remote_job(self):
        with patch.object(g, "api", side_effect=[{"id": RID}, {}]) as call:
            with self.assertRaises(g.Cancelled):
                g.request_image(
                    "test",
                    lambda *_: None,
                    unittest.mock.Mock(side_effect=[False, True]),
                    lambda _: None,
                )
        self.assertEqual(call.call_args.args[0], "DELETE")

    def test_network_errors_do_not_expose_keys_or_provider_text(self):
        with patch.object(
            g.requests, "request", side_effect=g.requests.ConnectionError("SECRET credential")
        ):
            with self.assertRaises(g.ImageError) as raised:
                g.api("GET", "/test")
        self.assertNotIn("SECRET", str(raised.exception))

    def test_prompts_keep_context_but_do_not_invent_scripture(self):
        text = "A quiet river through green pastures."
        result = g.prompts(text, 3, "morning light")
        self.assertEqual(len(result), 3)
        self.assertTrue(all(text in p and "morning light" in p for p in result))
        self.assertEqual(len(set(result)), 3)

    def test_no_eligible_workers_fails_and_cancels_instead_of_waiting(self):
        with patch.object(g, "api", side_effect=[{"id": RID}, {"is_possible": False}, {}]) as call:
            with self.assertRaisesRegex(g.ImageError, "No eligible"):
                g.request_image("test", lambda *_: None, lambda: False, lambda _: None)
        self.assertEqual(call.call_args.args[0], "DELETE")

    def test_response_bytes_are_capped_before_json_decode(self):
        from unittest.mock import MagicMock

        response = MagicMock()
        response.status_code = 200
        response.iter_content.return_value = [b"x" * 5]
        with patch.object(g.requests, "request") as request, patch.object(g, "MAX_RESPONSE", 4):
            request.return_value.__enter__.return_value = response
            with self.assertRaisesRegex(g.ImageError, "size limit"):
                g.api("GET", "/test")
