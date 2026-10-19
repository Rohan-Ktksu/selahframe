import io
import json
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

    def scene_plan(self):
        plan = self.client.get(self.url + "/scenes").json()
        return {
            "image_revision": plan["image_revision"],
            "scenes": [
                {key: item[key] for key in ("id", "enabled", "duration_weight", "motion_style")}
                for item in plan["scenes"]
            ],
        }

    def upload_scene_image(self, color):
        data = io.BytesIO()
        Image.new("RGB", (80, 140), color).save(data, "PNG")
        response = self.client.post(
            self.url + "/images",
            files={"image": ("photo.png", data.getvalue(), "image/png")},
            data={"source_url": "Owned test image", "license_name": "Owned"},
        )
        self.assertEqual(response.status_code, 200)
        return response.json()

    def test_placeholder_scene_plan_and_thumbnails(self):
        plan = self.client.get(self.url + "/scenes").json()
        self.assertEqual(len(plan["scenes"]), 6)
        self.assertTrue(all(item["placeholder"] for item in plan["scenes"]))
        thumb = self.client.get(plan["scenes"][0]["thumbnail_url"])
        self.assertEqual(thumb.status_code, 200)
        self.assertEqual(Image.open(io.BytesIO(thumb.content)).size, (180, 320))
        self.assertAlmostEqual(sum(s["share"] for s in plan["scenes"]), 1)

    def test_first_photo_replaces_placeholder_plan_and_second_appends(self):
        first = self.upload_scene_image("red")
        second = self.upload_scene_image("blue")
        plan = self.client.get(self.url + "/scenes").json()
        self.assertEqual(
            [s["image_asset_id"] for s in plan["scenes"]], [first["asset_id"], second["asset_id"]]
        )
        self.assertTrue(all(not s["placeholder"] for s in plan["scenes"]))
        thumb = self.client.get(plan["scenes"][0]["thumbnail_url"])
        pixel = Image.open(io.BytesIO(thumb.content)).getpixel((90, 160))
        self.assertGreater(pixel[0], 200)
        self.assertLess(pixel[2], 30)

    def test_scene_edits_preserve_approval_and_invalidate_preview(self):
        self.seed_export()
        plan = self.scene_plan()
        plan["scenes"].reverse()
        plan["scenes"][0].update(duration_weight=3, motion_style="zoom_out")
        plan["scenes"][-1]["enabled"] = False
        response = self.client.put(self.url + "/scenes", json=plan)
        self.assertEqual(response.status_code, 200)
        project = m.load_project(self.pid)
        self.assertEqual(project["approved_version"], 1)
        self.assertEqual(project["image_revision"], 1)
        self.assertEqual(self.client.get(self.url + "/preview").status_code, 409)
        saved = response.json()["scenes"]
        self.assertEqual(saved[0]["id"], plan["scenes"][0]["id"])
        self.assertAlmostEqual(saved[0]["share"], 3 / 7)
        m.initialize()
        self.assertEqual(
            self.client.get(self.url + "/scenes").json()["scenes"][0]["id"], saved[0]["id"]
        )

    def test_scene_plan_rejects_stale_or_invalid_updates(self):
        original = self.scene_plan()
        updated = self.scene_plan()
        updated["scenes"][0]["duration_weight"] = 2
        self.assertEqual(self.client.put(self.url + "/scenes", json=updated).status_code, 200)
        self.assertEqual(self.client.put(self.url + "/scenes", json=original).status_code, 409)
        invalid = self.scene_plan()
        invalid["scenes"][0]["id"] = invalid["scenes"][1]["id"]
        self.assertEqual(self.client.put(self.url + "/scenes", json=invalid).status_code, 422)
        invalid = self.scene_plan()
        for item in invalid["scenes"]:
            item["enabled"] = False
        self.assertEqual(self.client.put(self.url + "/scenes", json=invalid).status_code, 422)
        invalid = self.scene_plan()
        invalid["scenes"][0]["duration_weight"] = 0
        self.assertEqual(self.client.put(self.url + "/scenes", json=invalid).status_code, 422)
        self.assertEqual(self.client.get(self.url + "/scenes").json()["image_revision"], 1)

    def test_scene_ids_cannot_cross_project_boundaries(self):
        other = self.client.post("/api/projects", json=self.payload).json()["id"]
        foreign = self.client.get(f"/api/projects/{other}/scenes").json()["scenes"][0]
        plan = self.scene_plan()
        plan["scenes"][0]["id"] = foreign["id"]
        self.assertEqual(self.client.put(self.url + "/scenes", json=plan).status_code, 422)
        self.assertEqual(
            self.client.get(self.url + "/scenes/" + foreign["id"] + "/thumbnail").status_code, 404
        )

    def test_noop_scene_save_keeps_existing_preview(self):
        self.seed_export()
        self.assertEqual(
            self.client.put(self.url + "/scenes", json=self.scene_plan()).status_code, 200
        )
        self.assertEqual(m.load_project(self.pid)["image_revision"], 0)
        self.assertEqual(self.client.get(self.url + "/preview").status_code, 200)

    def test_busy_project_blocks_scene_changes_and_snapshot_is_immutable(self):
        self.approve()
        plan = self.scene_plan()
        plan["scenes"].reverse()
        plan["scenes"][0]["duration_weight"] = 4
        plan["scenes"][1]["enabled"] = False
        self.client.put(self.url + "/scenes", json=plan)
        with patch.object(m, "start_worker"):
            job_id = self.client.post(self.url + "/render").json()["job_id"]
        pending = self.scene_plan()
        pending["scenes"][0]["duration_weight"] = 1
        self.assertEqual(self.client.put(self.url + "/scenes", json=pending).status_code, 409)
        with m.connection() as c:
            import json

            snapshot = json.loads(
                c.execute("SELECT snapshot_json FROM jobs WHERE id=?", (job_id,)).fetchone()[0]
            )
        self.assertEqual(len(snapshot["scenes"]), 5)
        self.assertEqual(snapshot["scenes"][0]["id"], plan["scenes"][0]["id"])
        self.assertEqual(snapshot["scenes"][0]["duration_weight"], 4)

    def test_thumbnail_rejects_path_outside_project(self):
        asset = self.upload_scene_image("red")
        with m.connection() as c:
            c.execute(
                "UPDATE assets SET local_path=? WHERE id=?",
                (str(Path(self.tmp.name) / "outside.jpg"), asset["asset_id"]),
            )
        url = self.client.get(self.url + "/scenes").json()["scenes"][0]["thumbnail_url"]
        self.assertEqual(self.client.get(url).status_code, 404)

    def test_scene_migration_preserves_images_and_is_repeatable(self):
        asset = self.upload_scene_image("green")
        with m.connection() as c:
            c.execute("DELETE FROM scenes WHERE project_id=?", (self.pid,))
        m.initialize()
        first = self.client.get(self.url + "/scenes").json()["scenes"]
        m.initialize()
        second = self.client.get(self.url + "/scenes").json()["scenes"]
        self.assertEqual(first, second)
        self.assertEqual(first[0]["image_asset_id"], asset["asset_id"])

    def import_test_music(self):
        def normalize(source, destination, budget):
            destination.write_bytes(b"normalized-music")
            return 3000

        def immediate_worker(target, args):
            target(*args)

        with (
            patch.object(media, "normalize_music", side_effect=normalize),
            patch.object(media, "executable", return_value="test-tool"),
            patch.object(m, "start_worker", side_effect=immediate_worker),
        ):
            response = self.client.post(
                self.url + "/music/tracks",
                data={
                    "source_url": "Original test composition",
                    "license_name": "Owned fixture",
                    "rights_confirmed": "true",
                },
                files={"track": ("../../test.wav", b"original-music", "audio/wav")},
            )
        self.assertEqual(response.status_code, 202, response.text)
        return self.client.get(self.url + "/music").json()

    def music_payload(self, plan, **changes):
        return {
            "music_revision": plan["music_revision"],
            "asset_id": plan["asset_id"],
            "enabled": plan["enabled"],
            "gain_db": plan["gain_db"],
            **changes,
        }

    def test_music_off_by_default_and_import_preserves_approval_original_and_preview(self):
        self.approve()
        self.assertFalse(self.client.get(self.url + "/music").json()["enabled"])
        plan = self.import_test_music()
        self.assertFalse(plan["enabled"])
        self.assertEqual(plan["tracks"][0]["name"], "test.wav")
        self.assertEqual(self.client.get(self.url).json()["approved_version"], 1)
        preview = plan["tracks"][0]["preview_url"]
        self.assertEqual(self.client.get(preview, headers={"Range": "bytes=0-3"}).status_code, 206)
        with m.connection() as c:
            row = c.execute("SELECT * FROM music_tracks").fetchone()
        self.assertEqual(Path(row["original_path"]).read_bytes(), b"original-music")
        self.assertNotIn("local_path", str(plan))

    def test_music_requires_rights_and_real_supported_file_extension(self):
        data = {"source_url": "Fixture", "license_name": "Owned"}
        response = self.client.post(
            self.url + "/music/tracks", data=data, files={"track": ("track.wav", b"x")}
        )
        self.assertEqual(response.status_code, 400)
        data["rights_confirmed"] = "true"
        response = self.client.post(
            self.url + "/music/tracks",
            data=data,
            files={"track": ("playlist.m3u", b"http://example.invalid")},
        )
        self.assertEqual(response.status_code, 400)
        with (
            patch.object(media, "executable", return_value="test-tool"),
            patch.object(m, "MAX_MUSIC_BYTES", 3),
        ):
            response = self.client.post(
                self.url + "/music/tracks", data=data, files={"track": ("track.wav", b"1234")}
            )
        self.assertEqual(response.status_code, 413)

    def test_music_settings_stale_noop_validation_and_project_ownership(self):
        plan = self.import_test_music()
        saved = self.client.put(self.url + "/music", json=self.music_payload(plan)).json()
        self.assertEqual(saved["music_revision"], plan["music_revision"])
        saved = self.client.put(
            self.url + "/music", json=self.music_payload(plan, enabled=True)
        ).json()
        self.assertEqual(saved["music_revision"], plan["music_revision"] + 1)
        self.assertEqual(
            self.client.put(self.url + "/music", json=self.music_payload(plan)).status_code, 409
        )
        for changes, status in [
            ({"gain_db": 0}, 422),
            ({"asset_id": None, "enabled": True}, 400),
            ({"asset_id": "foreign-id"}, 400),
        ]:
            self.assertEqual(
                self.client.put(
                    self.url + "/music", json=self.music_payload(saved, **changes)
                ).status_code,
                status,
            )
        other = self.client.post("/api/projects", json=self.payload).json()["id"]
        self.assertEqual(
            self.client.get(
                f"/api/projects/{other}/music/tracks/{plan['asset_id']}/preview"
            ).status_code,
            404,
        )
        self.assertEqual(
            self.client.put(
                f"/api/projects/{other}/music", json=self.music_payload(plan, music_revision=0)
            ).status_code,
            400,
        )

    def test_music_change_invalidates_export_cache_download_and_drive(self):
        original = self.seed_export()
        plan = self.import_test_music()
        self.client.put(self.url + "/music", json=self.music_payload(plan, enabled=True))
        # Even an old complete status cannot expose the stale export.
        m.update_project(self.pid, status="complete")
        self.assertEqual(self.client.get(self.url + "/download").status_code, 404)
        self.assertEqual(self.client.post(self.url + "/upload-drive").status_code, 404)
        with patch.object(m, "start_worker") as worker:
            response = self.client.post(self.url + "/render")
        self.assertEqual(response.status_code, 202)
        worker.assert_called_once()
        with m.connection() as c:
            snapshot = json.loads(
                c.execute(
                    "SELECT snapshot_json FROM jobs WHERE id=?", (response.json()["job_id"],)
                ).fetchone()[0]
            )
        self.assertEqual(snapshot["music"]["id"], plan["asset_id"])
        self.assertTrue(original.is_file())
        self.assertEqual(
            self.client.put(self.url + "/music", json=self.music_payload(plan)).status_code, 409
        )

    def test_music_import_locks_edits_and_other_jobs_then_recovers_after_restart(self):
        self.approve()
        with (
            patch.object(media, "executable", return_value="test-tool"),
            patch.object(m, "start_worker"),
        ):
            response = self.client.post(
                self.url + "/music/tracks",
                data={"source_url": "Fixture", "license_name": "Owned", "rights_confirmed": "true"},
                files={"track": ("track.wav", b"staged-audio")},
            )
        self.assertEqual(response.status_code, 202)
        self.assertEqual(self.client.get(self.url).json()["status"], "importing_music")
        self.assertEqual(self.client.post(self.url + "/render").status_code, 409)
        self.assertEqual(
            self.client.put(
                self.url + "/script", json={"script": "Blocked during audio import"}
            ).status_code,
            409,
        )
        self.assertEqual(
            self.client.post(self.url + "/approve", json={"script_version": 1}).status_code, 409
        )
        self.assertEqual(
            self.client.put(self.url + "/scenes", json=self.scene_plan()).status_code, 409
        )
        self.assertEqual(
            self.client.put(self.url + "/music", json={"music_revision": 0}).status_code, 409
        )
        m.initialize()
        self.assertEqual(self.client.get(self.url).json()["status"], "approved")
        self.assertEqual(
            self.client.get("/api/v1/jobs/" + response.json()["job_id"]).json()["status"], "failed"
        )

    def test_failed_music_decode_restores_previous_export_and_settings(self):
        video = self.seed_export()

        def immediate_worker(target, args):
            target(*args)

        with (
            patch.object(media, "executable", return_value="test-tool"),
            patch.object(m, "start_worker", side_effect=immediate_worker),
            patch.object(media, "normalize_music", side_effect=media.MediaError("Invalid audio")),
        ):
            response = self.client.post(
                self.url + "/music/tracks",
                data={"source_url": "Fixture", "license_name": "Owned", "rights_confirmed": "true"},
                files={"track": ("not-audio.wav", b"invalid")},
            )
        self.assertEqual(response.status_code, 202)
        self.assertEqual(self.client.get(self.url).json()["status"], "complete")
        self.assertEqual(self.client.get(self.url + "/download").status_code, 200)
        self.assertFalse(self.client.get(self.url + "/music").json()["tracks"])
        self.assertTrue(video.is_file())

    def test_music_track_limit_and_failed_worker_release(self):
        for _ in range(3):
            self.import_test_music()
        with patch.object(media, "executable", return_value="test-tool"):
            response = self.client.post(
                self.url + "/music/tracks",
                data={"source_url": "Fixture", "license_name": "Owned", "rights_confirmed": "true"},
                files={"track": ("track.wav", b"audio")},
            )
        self.assertEqual(response.status_code, 409)
        self.assertEqual(len(self.client.get(self.url + "/music").json()["tracks"]), 3)

    def test_music_missing_or_changed_file_never_silently_exports_without_it(self):
        plan = self.import_test_music()
        self.approve()
        self.client.put(self.url + "/music", json=self.music_payload(plan, enabled=True))
        with m.connection() as c:
            row = c.execute(
                "SELECT local_path FROM assets WHERE id=?", (plan["asset_id"],)
            ).fetchone()
        Path(row[0]).write_bytes(b"changed-after-import")
        with patch.object(m, "start_worker"):
            response = self.client.post(self.url + "/render")
        m.render_worker(self.pid, response.json()["job_id"])
        job = self.client.get("/api/v1/jobs/" + response.json()["job_id"]).json()
        self.assertEqual(job["status"], "failed")
        self.assertIn("changed on disk", job["error"])

    def test_music_worker_start_failure_releases_lock_and_retains_old_export(self):
        video = self.seed_export()
        with (
            patch.object(media, "executable", return_value="test-tool"),
            patch.object(m, "start_worker", side_effect=RuntimeError("thread unavailable")),
        ):
            response = self.client.post(
                self.url + "/music/tracks",
                data={"source_url": "Fixture", "license_name": "Owned", "rights_confirmed": "true"},
                files={"track": ("track.wav", b"staged")},
            )
        self.assertEqual(response.status_code, 503)
        self.assertEqual(self.client.get(self.url).json()["status"], "complete")
        self.assertTrue(video.is_file())
        with m.connection() as c:
            self.assertIsNone(c.execute("SELECT id FROM jobs WHERE status='running'").fetchone())

    def test_music_and_render_cannot_both_claim_global_job(self):
        from concurrent.futures import ThreadPoolExecutor

        self.approve()

        def upload():
            return self.client.post(
                self.url + "/music/tracks",
                data={"source_url": "Fixture", "license_name": "Owned", "rights_confirmed": "true"},
                files={"track": ("track.wav", b"staged")},
            ).status_code

        with (
            patch.object(media, "executable", return_value="test-tool"),
            patch.object(m, "start_worker"),
            ThreadPoolExecutor(max_workers=2) as pool,
        ):
            imported = pool.submit(upload)
            rendered = pool.submit(lambda: self.client.post(self.url + "/render").status_code)
            self.assertEqual(sorted([imported.result(), rendered.result()]), [202, 409])
        with m.connection() as c:
            self.assertEqual(
                c.execute("SELECT COUNT(*) FROM jobs WHERE status='running'").fetchone()[0], 1
            )

    def test_music_defaults_and_voice_relative_range(self):
        plan = self.client.get(self.url + "/music").json()
        self.assertEqual(plan["gain_db"], -24)
        for gain in (-11, -41):
            self.assertEqual(
                self.client.put(
                    self.url + "/music", json={"music_revision": 0, "gain_db": gain}
                ).status_code,
                422,
            )

    def test_quiet_music_migration_preserves_approval_and_is_idempotent(self):
        self.approve()
        with m.connection() as c:
            c.execute(
                "UPDATE projects SET music_gain_db=-18, music_enabled=1, status='complete', drive_status='verified-size' WHERE id=?",
                (self.pid,),
            )
            c.execute("PRAGMA user_version=4")
        m.initialize()
        first = self.client.get(self.url).json()
        self.assertEqual(first["music_gain_db"], -24)
        self.assertEqual(first["music_revision"], 1)
        self.assertEqual(first["status"], "approved")
        self.assertEqual(first["approved_version"], 1)
        self.assertEqual(first["drive_status"], "")
        m.initialize()
        self.assertEqual(self.client.get(self.url).json()["music_revision"], 1)

    def image_request(self, **changes):
        project = self.client.get(self.url).json()
        payload = {
            "image_revision": project["image_revision"],
            "script_version": project["script_version"],
            "consent": True,
            "count": 1,
        }
        payload.update(changes)
        return self.client.post(self.url + "/cinematic", json=payload)

    def test_images_require_consent_current_version_and_approved_autorender(self):
        self.assertEqual(self.image_request(consent=False).status_code, 400)
        self.assertEqual(self.image_request(image_revision=99).status_code, 409)
        self.assertEqual(self.image_request(render_after=True).status_code, 409)
        self.assertEqual(self.image_request(source="narration").status_code, 400)

    def test_image_generation_claims_global_lock_and_cancellation_restores_project(self):
        self.approve()
        with patch.object(m, "start_worker"):
            result = self.image_request()
            self.assertEqual(result.status_code, 202)
            self.assertEqual(self.client.get(self.url).json()["status"], "generating_images")
            self.assertEqual(self.client.post(self.url + "/render").status_code, 409)
            self.assertEqual(self.image_request().status_code, 409)
            self.assertEqual(
                self.client.put(
                    self.url + "/script", json={"script": "Cannot edit during generation"}
                ).status_code,
                409,
            )
        self.assertEqual(self.client.post(self.url + "/cinematic/cancel").status_code, 200)
        self.assertEqual(self.client.get(self.url).json()["status"], "approved")
        self.assertEqual(
            self.client.get("/api/v1/jobs/" + result.json()["job_id"]).json()["status"], "cancelled"
        )

    def test_image_success_saves_real_assets_provenance_and_renders_only_approved_script(self):
        self.approve()
        with patch.object(m, "start_worker") as worker:
            result = self.image_request(replace_plan=True, render_after=True)
        data = io.BytesIO()
        Image.new("RGB", (32, 48), "green").save(data, "JPEG")
        with (
            patch.object(
                m.cinematic,
                "request_image",
                return_value=(
                    data.getvalue(),
                    data.getvalue(),
                    {"model": "stable_diffusion", "seed": "7", "generation_id": "fixture"},
                ),
            ),
            patch.object(m, "render") as render,
        ):
            target, args = worker.call_args.args
            target(*args)
        render.assert_called_once()
        project = self.client.get(self.url).json()
        self.assertEqual(project["approved_version"], 1)
        self.assertEqual(project["image_revision"], 1)
        plan = self.client.get(self.url + "/scenes").json()
        self.assertEqual(len(plan["scenes"]), 1)
        self.assertFalse(plan["scenes"][0]["placeholder"])
        self.assertTrue(plan["scenes"][0]["generated"])
        self.assertEqual(self.client.get(plan["scenes"][0]["thumbnail_url"]).status_code, 200)
        receipt = list((m.OUTPUT / self.pid / "images" / "generated").glob("*/provenance.json"))[0]
        self.assertEqual(json.loads(receipt.read_text())["records"][0]["seed"], "7")
        self.assertEqual(
            self.client.get("/api/v1/jobs/" + result.json()["job_id"]).json()["status"], "complete"
        )

    def test_cancelled_image_worker_cannot_apply_assets_late(self):
        with patch.object(m, "start_worker") as worker:
            self.image_request()
        self.client.post(self.url + "/cinematic/cancel")
        with patch.object(m.cinematic, "request_image", side_effect=m.cinematic.Cancelled()):
            target, args = worker.call_args.args
            target(*args)
        self.assertEqual(self.client.get(self.url).json()["image_revision"], 0)

    def test_image_failure_and_start_failure_keep_previous_plan(self):
        with patch.object(m, "start_worker", side_effect=RuntimeError()):
            self.assertEqual(self.image_request().status_code, 503)
        self.assertEqual(self.client.get(self.url).json()["status"], "draft")
        with patch.object(m, "start_worker") as worker:
            self.image_request()
        with patch.object(
            m.cinematic, "request_image", side_effect=m.cinematic.ImageError("Queue timed out")
        ):
            target, args = worker.call_args.args
            target(*args)
        self.assertEqual(len(self.client.get(self.url + "/scenes").json()["scenes"]), 6)
        self.assertEqual(self.client.get(self.url).json()["image_revision"], 0)

    def test_restart_recovers_image_job_without_approving_narration(self):
        with patch.object(m, "start_worker"):
            self.image_request()
        m.initialize()
        project = self.client.get(self.url).json()
        self.assertEqual(project["status"], "draft")
        self.assertIsNone(project["approved_version"])
        self.assertEqual(project["job"]["status"], "failed")

    def test_partial_image_failure_retains_original_plan_and_downloaded_file(self):
        with patch.object(m, "start_worker") as worker:
            self.image_request(count=2, replace_plan=True)
        data = io.BytesIO()
        Image.new("RGB", (32, 48), "green").save(data, "JPEG")
        fixture = (
            data.getvalue(),
            data.getvalue(),
            {"model": "stable_diffusion", "seed": "7", "generation_id": "fixture"},
        )
        with patch.object(
            m.cinematic,
            "request_image",
            side_effect=[fixture, m.cinematic.ImageError("Queue timeout")],
        ):
            target, args = worker.call_args.args
            target(*args)
        self.assertEqual(len(self.client.get(self.url + "/scenes").json()["scenes"]), 6)
        self.assertEqual(self.client.get(self.url).json()["image_revision"], 0)
        self.assertTrue(list((m.OUTPUT / self.pid / "images" / "generated").glob("*/scene-01.jpg")))
        checkpoint = list((m.OUTPUT / self.pid / "images" / "generated").glob("*/provenance.json"))[
            0
        ]
        self.assertEqual(len(json.loads(checkpoint.read_text())["records"]), 1)


if __name__ == "__main__":
    unittest.main()
