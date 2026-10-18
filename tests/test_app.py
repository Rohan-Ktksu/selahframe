import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from PIL import Image
from app import main as m


class AppTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.db = patch.object(m, "DB", root / "test.sqlite3")
        self.out = patch.object(m, "OUTPUT", root / "output")
        self.db.start()
        self.out.start()
        m.OUTPUT.mkdir()
        m.initialize()
        self.client = TestClient(m.app)
        self.payload = dict(title="Test", reference="Test 1:1", scripture="Supplied test text",
                            translation="Test", scripture_source="Test fixture", source_license="Test only",
                            context_text="Adjacent test context", placeholders=True)
        self.pid = self.client.post("/api/projects", json=self.payload).json()["id"]
        self.url = f"/api/projects/{self.pid}"

    def tearDown(self):
        self.client.close()
        self.db.stop()
        self.out.stop()
        self.tmp.cleanup()

    def approve(self):
        p = self.client.put(self.url + "/script", json={"script": "Reviewed narration for testing."}).json()
        return self.client.post(self.url + "/approve", json={"script_version": p["script_version"]})

    def test_home_health_and_persistence(self):
        self.assertEqual(self.client.get("/").status_code, 200)
        self.assertIn("components", self.client.get("/api/health").json())
        m.initialize()
        self.assertEqual(self.client.get(self.url).json()["scripture"], self.payload["scripture"])

    def test_provenance_required(self):
        del self.payload["translation"]
        self.assertEqual(self.client.post("/api/projects", json=self.payload).status_code, 422)

    def test_failed_status_cannot_bypass_approval(self):
        m.update_project(self.pid, status="failed")
        self.assertEqual(self.client.post(self.url + "/render").status_code, 409)

    def test_edit_revokes_approval_and_stale_approval_rejected(self):
        self.assertEqual(self.approve().status_code, 200)
        self.client.put(self.url + "/script", json={"script": "A revised narration for testing."})
        self.assertIsNone(self.client.get(self.url).json()["approved_version"])
        self.assertEqual(self.client.post(self.url + "/approve", json={"script_version": 1}).status_code, 409)
        self.assertEqual(self.client.post(self.url + "/render").status_code, 409)

    def test_duplicate_render_and_global_limit(self):
        self.approve()
        with patch.object(m.threading, "Thread") as thread:
            self.assertEqual(self.client.post(self.url + "/render").status_code, 200)
            self.client.post(self.url + "/render")
            thread.assert_called_once()
            self.assertEqual(self.client.put(self.url + "/script", json={"script": "Cannot change during render"}).status_code, 409)
            other = self.client.post("/api/projects", json=self.payload).json()["id"]
            m.update_project(other, script="Reviewed script", script_version=1, approved_version=1)
            self.assertEqual(self.client.post(f"/api/projects/{other}/render").status_code, 409)

    def test_restart_recovers_interrupted_job(self):
        self.approve()
        m.update_project(self.pid, status="rendering")
        m.initialize()
        p = self.client.get(self.url).json()
        self.assertEqual(p["status"], "failed")
        self.assertEqual(p["approved_version"], 1)

    def test_invalid_oversized_and_valid_image(self):
        self.assertEqual(self.client.post(self.url + "/images", files={"image": ("bad.png", b"not image", "image/png")}).status_code, 400)
        with patch.object(m, "MAX_UPLOAD_BYTES", 10):
            self.assertEqual(self.client.post(self.url + "/images", files={"image": ("big.png", b"x" * 11)}).status_code, 413)
        data = io.BytesIO()
        Image.new("RGB", (20, 20)).save(data, "PNG")
        response = self.client.post(self.url + "/images", files={"image": ("../../pic.png", data.getvalue(), "image/png")})
        self.assertEqual(response.status_code, 200)
        self.assertTrue((m.OUTPUT / self.pid / "images" / response.json()["filename"]).is_file())

    def test_drive_requires_verification_and_keeps_files(self):
        m.update_project(self.pid, status="complete")
        video = m.OUTPUT / self.pid / "final.mp4"
        video.write_bytes(b"mock-video")
        with patch.object(m, "run", side_effect=[None, RuntimeError("failed")]):
            self.assertEqual(self.client.post(self.url + "/upload-drive").status_code, 503)
        self.assertTrue(video.exists())
        self.assertEqual(m.load_project(self.pid)["drive_status"], "failed")
        with patch.object(m, "run") as run:
            self.assertEqual(self.client.post(self.url + "/upload-drive").json()["status"], "verified-size")
            self.assertIn(f"bibledrive:Bible-AI-Studio/Projects/{self.pid}", run.call_args.args[0])
            self.assertEqual(run.call_args.args[0][1], "check")

    def test_subprocess_uses_stdin(self):
        with patch.object(m.subprocess, "run") as run:
            run.return_value.returncode = 0
            m.run(["python", "-m", "piper"], input_text="Narration")
            self.assertEqual(run.call_args.kwargs["input"], "Narration")

    def test_unapproved_download_blocked(self):
        (m.OUTPUT / self.pid / "final.mp4").write_bytes(b"stale")
        self.assertEqual(self.client.get(self.url + "/download").status_code, 409)

    def test_external_origin_cannot_modify_project(self):
        self.assertEqual(self.client.post("/api/projects", json=self.payload, headers={"Origin": "https://example.com"}).status_code, 403)

    def test_missing_render_dependencies_are_actionable(self):
        self.approve()
        with patch.object(m.shutil, "which", return_value=None):
            m.render_worker(self.pid)
        p = m.load_project(self.pid)
        self.assertEqual(p["status"], "failed")
        self.assertIn("ffmpeg", p["error"])


if __name__ == "__main__":
    unittest.main()
