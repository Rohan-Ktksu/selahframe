import base64
import os
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from app import main, security

PASSWORD = "test-only-password-with-32-characters"


class OnlineSecurityTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(
            os.environ,
            {
                "SELAHFRAME_PUBLIC_URL": "https://studio.example.com",
                "SELAHFRAME_PASSWORD": PASSWORD,
                "SELAHFRAME_USER": "owner",
            },
            clear=False,
        )
        self.env.start()
        self.client = TestClient(main.app)

    def tearDown(self):
        self.client.close()
        self.env.stop()

    def auth(self, password=PASSWORD):
        return {
            "Authorization": "Basic " + base64.b64encode(("owner:" + password).encode()).decode()
        }

    def test_online_pages_assets_and_api_require_credentials(self):
        for path in ["/", "/static/studio.js", "/api/projects", "/api/health"]:
            self.assertEqual(self.client.get(path).status_code, 401)
        self.assertEqual(self.client.get("/", headers=self.auth("incorrect")).status_code, 401)
        response = self.client.get("/", headers=self.auth())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["cache-control"], "private, no-store")
        self.assertEqual(self.client.get("/healthz").json(), {"ok": True})

    def test_cross_origin_request_is_rejected_even_with_password(self):
        headers = {**self.auth(), "Origin": "https://unrelated.test"}
        self.assertEqual(
            self.client.post("/api/projects", headers=headers, json={}).status_code, 403
        )
        headers["Origin"] = "https://studio.example.com"
        self.assertEqual(
            self.client.post("/api/projects", headers=headers, json={}).status_code, 422
        )

    def test_startup_configuration_fails_closed(self):
        security.validate()
        with patch.dict(os.environ, {"SELAHFRAME_PASSWORD": "weak"}):
            with self.assertRaisesRegex(RuntimeError, "24 characters"):
                security.validate()
        with patch.dict(os.environ, {"SELAHFRAME_PUBLIC_URL": "http://insecure.test"}):
            with self.assertRaisesRegex(RuntimeError, "HTTPS"):
                security.validate()
        with patch.dict(
            os.environ,
            {"SELAHFRAME_PUBLIC_URL": "", "RENDER_EXTERNAL_URL": "", "SELAHFRAME_ONLINE": "1"},
        ):
            with self.assertRaises(RuntimeError):
                security.validate()

    def test_render_url_is_supported_without_hardcoding_assigned_hostname(self):
        with patch.dict(
            os.environ,
            {
                "SELAHFRAME_PUBLIC_URL": "",
                "RENDER_EXTERNAL_URL": "https://demo.onrender.com",
                "SELAHFRAME_ONLINE": "1",
            },
        ):
            self.assertEqual(security.public_origin(), "https://demo.onrender.com")
            security.validate()

    def test_malformed_auth_never_authenticates(self):
        for value in [
            "",
            "Bearer secret",
            "Basic ?????",
            "Basic " + base64.b64encode(b"no-colon").decode(),
        ]:
            self.assertFalse(security.authorized(value))
