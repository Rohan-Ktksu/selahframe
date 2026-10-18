import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from PIL import Image

from app import main as m
from app import media


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
        self.payload = dict(
            title="Test",
            reference="Test 1:1",
            scripture="Supplied test text",
            translation="Test",
            scripture_source="Test fixture",
            source_license="Test only",
            context_text="Adjacent test context",
            placeholders=True,
        )
        self.pid = self.client.post("/api/projects", json=self.payload).json()["id"]
        self.url = f"/api/projects/{self.pid}"

    def tearDown(self):
        self.client.close()
        self.db.stop()
        self.out.stop()
        self.tmp.cleanup()

    def approve(self):
        p = self.client.put(
            self.url + "/script", json={"script": "Reviewed narration for testing."}
        ).json()
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
        self.assertEqual(
            self.client.post(self.url + "/approve", json={"script_version": 1}).status_code,
            409,
        )
        self.assertEqual(self.client.post(self.url + "/render").status_code, 409)

    def test_duplicate_render_and_global_limit(self):
        self.approve()
        with patch.object(m, "start_worker") as thread:
            self.assertEqual(self.client.post(self.url + "/render").status_code, 202)
            self.client.post(self.url + "/render")
            thread.assert_called_once()
            self.assertEqual(
                self.client.put(
                    self.url + "/script", json={"script": "Cannot change during render"}
                ).status_code,
                409,
            )
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
        self.assertEqual(
            self.client.post(
                self.url + "/images",
                data={"source_url": "test fixture", "license_name": "owned test image"},
                files={"image": ("bad.png", b"not image", "image/png")},
            ).status_code,
            400,
        )
        with patch.object(m, "MAX_UPLOAD_BYTES", 10):
            self.assertEqual(
                self.client.post(
                    self.url + "/images",
                    data={
                        "source_url": "test fixture",
                        "license_name": "owned test image",
                    },
                    files={"image": ("big.png", b"x" * 11)},
                ).status_code,
                413,
            )
        data = io.BytesIO()
        Image.new("RGB", (20, 20)).save(data, "PNG")
        response = self.client.post(
            self.url + "/images",
            data={"source_url": "test fixture", "license_name": "owned test image"},
            files={"image": ("../../pic.png", data.getvalue(), "image/png")},
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue((m.OUTPUT / self.pid / "images" / response.json()["filename"]).is_file())

    def seed_export(self):
        self.approve()
        m.update_project(self.pid, status="complete")
        video = m.OUTPUT / self.pid / "final.mp4"
        video.write_bytes(b"mock-video")
        with m.connection() as c:
            c.execute(
                "INSERT INTO jobs (id, project_id, stage, status, snapshot_json) VALUES ('render-test', ?, 'complete', 'complete', '{}')",
                (self.pid,),
            )
            c.execute(
                "INSERT INTO exports (id, project_id, job_id, script_version, image_revision, quality, file_path, width, height, duration_ms, checksum) VALUES ('export-test', ?, 'render-test', 1, 0, '720p', ?, 720, 1280, 1000, 'test')",
                (self.pid, str(video)),
            )
            c.execute(
                "UPDATE exports SET pipeline_signature=? WHERE id='export-test'",
                (media.pipeline_signature(),),
            )
        return video

    def test_drive_requires_verification_and_keeps_files(self):
        video = self.seed_export()
        with patch.object(m, "start_worker"):
            response = self.client.post(self.url + "/upload-drive")
            self.assertEqual(response.status_code, 202)
            job_id = response.json()["job_id"]
        with patch.object(m, "run", side_effect=[None, RuntimeError("failed")]):
            m.drive_worker(self.pid, job_id, m.current_export(self.pid))
        self.assertTrue(video.exists())
        self.assertEqual(m.load_project(self.pid)["drive_status"], "failed")
        with patch.object(m, "run") as run:
            m.drive_worker(self.pid, job_id, m.current_export(self.pid))
            self.assertEqual(m.load_project(self.pid)["drive_status"], "verified-size")
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
        self.assertEqual(
            self.client.post(
                "/api/projects",
                json=self.payload,
                headers={"Origin": "https://example.com"},
            ).status_code,
            403,
        )

    def test_missing_render_dependencies_are_actionable(self):
        self.approve()
        with patch.object(m, "start_worker"):
            job_id = self.client.post(self.url + "/render").json()["job_id"]
        with patch.object(media, "readiness", return_value={"ffmpeg": False}):
            m.render_worker(self.pid, job_id)
        p = m.load_project(self.pid)
        self.assertEqual(p["status"], "failed")
        self.assertIn("ffmpeg", p["error"])
        self.assertEqual(self.client.get("/api/v1/jobs/" + job_id).json()["status"], "failed")

    def test_script_history_preserves_approved_version(self):
        self.approve()
        self.client.put(
            self.url + "/script", json={"script": "An edited narration after approval."}
        )
        versions = self.client.get(self.url + "/scripts").json()
        self.assertEqual([v["version"] for v in versions], [2, 1])
        self.assertIsNotNone(versions[1]["approved_at"])
        self.assertIsNone(versions[0]["approved_at"])

    def test_job_progress_survives_database_reopen_and_restart_fails_active(self):
        self.approve()
        with patch.object(m, "start_worker"):
            a = self.client.post(self.url + "/render").json()
            b = self.client.post(self.url + "/render").json()
        self.assertEqual(a["job_id"], b["job_id"])
        m.progress_job(a["job_id"], "voice", 10)
        self.assertEqual(self.client.get("/api/v1/jobs/" + a["job_id"]).json()["progress"], 10)
        m.initialize()
        job = self.client.get("/api/v1/jobs/" + a["job_id"]).json()
        self.assertEqual(job["status"], "failed")
        self.assertIn("stopped", job["error"])

    def test_upload_requires_provenance_and_invalidates_previous_export(self):
        self.seed_export()
        data = io.BytesIO()
        Image.new("RGB", (20, 20)).save(data, "PNG")
        file = {"image": ("photo.png", data.getvalue(), "image/png")}
        self.assertEqual(self.client.post(self.url + "/images", files=file).status_code, 422)
        self.assertEqual(
            self.client.post(
                self.url + "/images",
                files=file,
                data={"source_url": "Own photo", "license_name": "Owned"},
            ).status_code,
            200,
        )
        self.assertEqual(self.client.get(self.url + "/preview").status_code, 409)

    def test_export_reuse_does_not_start_another_worker(self):
        self.seed_export()
        with patch.object(m, "start_worker") as worker:
            response = self.client.post(self.url + "/render")
        self.assertEqual(response.json()["status"], "complete")
        worker.assert_not_called()

    def test_changed_pipeline_does_not_reuse_an_older_export(self):
        self.seed_export()
        with (
            patch.object(media, "pipeline_signature", return_value="updated-renderer"),
            patch.object(m, "start_worker") as worker,
        ):
            response = self.client.post(self.url + "/render")
        self.assertEqual(response.json()["status"], "running")
        worker.assert_called_once()

    def test_versioned_routes_available(self):
        self.assertEqual(self.client.get("/api/v1/projects/" + self.pid).status_code, 200)
        self.assertEqual(
            self.client.get("/api/v1/projects/" + self.pid + "/scripts").status_code,
            200,
        )

    def test_parallel_render_requests_claim_one_job(self):
        from concurrent.futures import ThreadPoolExecutor

        self.approve()
        with patch.object(m, "start_worker") as worker:
            with ThreadPoolExecutor(max_workers=6) as pool:
                responses = list(pool.map(lambda _: m.render(self.pid), range(12)))
        self.assertEqual(len({r["job_id"] for r in responses}), 1)
        worker.assert_called_once()

    def test_drive_job_blocks_edits_and_render(self):
        self.seed_export()
        with patch.object(m, "start_worker"):
            self.client.post(self.url + "/upload-drive")
        self.assertEqual(
            self.client.put(
                self.url + "/script", json={"script": "Changed during Drive upload"}
            ).status_code,
            409,
        )
        self.assertEqual(self.client.post(self.url + "/render").status_code, 409)

    def test_bad_ollama_response_has_manual_fallback(self):
        for raw in (None, [], {"unexpected": True}):
            with patch.object(m.requests, "post") as request:
                request.return_value.json.return_value = {"response": raw}
                response = self.client.post(self.url + "/generate-script")
            self.assertEqual(response.status_code, 503)
            self.assertIn("manually", response.json()["detail"])
            self.assertEqual(m.load_project(self.pid)["scripture"], self.payload["scripture"])

    def test_slow_draft_cannot_overwrite_manual_edits(self):
        def draft_request(*args, **kwargs):
            m.save_script(self.pid, "Manual text written while the model is busy.")
            from unittest.mock import Mock

            response = Mock()
            response.json.return_value = {
                "response": "A late model response must not replace edits."
            }
            return response

        with patch.object(m.requests, "post", side_effect=draft_request):
            response = self.client.post(self.url + "/generate-script")
        self.assertEqual(response.status_code, 409)
        self.assertTrue(m.load_project(self.pid)["script"].startswith("Manual text"))


if __name__ == "__main__":
    unittest.main()
