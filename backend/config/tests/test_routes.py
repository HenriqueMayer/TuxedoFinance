import tempfile
from pathlib import Path

from django.test import TestCase, override_settings


class HealthTests(TestCase):
    def test_health_is_public(self):
        response = self.client.get("/api/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ok")


class ClientRouteTests(TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.client_dir = Path(directory.name)
        (self.client_dir / "index.html").write_text("<!doctype html><title>client</title>")

    def test_client_route_returns_the_entry_document_uncached(self):
        with override_settings(CLIENT_DIR=self.client_dir):
            response = self.client.get("/transactions/42")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"<title>client</title>", response.content)
        self.assertIn("no-cache", response["Cache-Control"])

    def test_unknown_api_path_is_not_a_client_route(self):
        with override_settings(CLIENT_DIR=self.client_dir):
            response = self.client.get("/api/does-not-exist")
        self.assertEqual(response.status_code, 404)
        self.assertNotIn(b"<title>client</title>", response.content)

    def test_missing_file_is_a_404_and_not_the_entry_document(self):
        with override_settings(CLIENT_DIR=self.client_dir):
            response = self.client.get("/assets/index-old-build.js")
        self.assertEqual(response.status_code, 404)
        self.assertNotIn(b"<title>client</title>", response.content)

    def test_missing_build_is_a_404(self):
        with override_settings(CLIENT_DIR=self.client_dir / "absent"):
            self.assertEqual(self.client.get("/").status_code, 404)

    def test_client_route_refuses_post(self):
        with override_settings(CLIENT_DIR=self.client_dir):
            self.assertEqual(self.client.post("/transactions").status_code, 405)
