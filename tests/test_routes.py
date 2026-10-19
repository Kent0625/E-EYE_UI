import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import unittest
from app.app import create_app

class TestRoutes(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.client = self.app.test_client()

    def test_navigation_tabs_no_404(self):
        # All primary nav tabs must return 200 (no 404s)
        pages = [
            ("/", "Home"),
            ("/screen/new", "Screen (New)"),
            ("/screen/s_mock_refer/OD", "Screen (Align OD)"),
            ("/screen/s_mock_refer/OS", "Screen (Align OS)"),
            ("/screen/s_mock_refer/processing", "Screen (Processing)"),
            ("/screen/s_mock_refer/result", "Screen (Result)"),
            ("/history", "History"),
            ("/settings", "Settings")
        ]
        for path, label in pages:
            res = self.client.get(path)
            self.assertEqual(res.status_code, 200, f"Expected 200 for {label} ({path}), got {res.status_code}")
            self.assertIn(b"E-Eye", res.data)

    def test_media_send_from_directory_security(self):
        # Valid media file returns 200
        res = self.client.get("/media/OD_sample.jpg")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.mimetype, "image/jpeg")

        # Path traversal attempts must be refused by send_from_directory (404 or 400)
        bad_paths = [
            "/media/../app.py",
            "/media/..%2fapp.py",
            "/media/..\\app.py",
            "/media/%2e%2e/app.py",
            "/media/../../eeye.db"
        ]
        for bp in bad_paths:
            res = self.client.get(bp)
            self.assertIn(res.status_code, (404, 400), f"Path traversal '{bp}' was not refused! Got {res.status_code}")

    def test_api_status(self):
        res = self.client.get("/api/status")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data["camera"], "ok")
        self.assertEqual(data["model"], "loaded")
        self.assertTrue(data["mock_mode"])

    def test_api_sessions(self):
        res = self.client.get("/api/sessions")
        self.assertEqual(res.status_code, 200)
        sessions = res.get_json()
        self.assertIsInstance(sessions, list)
        self.assertGreaterEqual(len(sessions), 1)

    def test_unknown_session_friendly_page(self):
        # Unknown session IDs must return a friendly 'session not found' page
        unknown_urls = [
            "/screen/unknown-session-999/OD",
            "/screen/unknown-session-999/processing",
            "/screen/unknown-session-999/result"
        ]
        for url in unknown_urls:
            res = self.client.get(url)
            self.assertEqual(res.status_code, 404, f"Expected 404 for unknown session {url}, got {res.status_code}")
            html = res.data.decode("utf-8")
            self.assertIn("Screening session not found", html)
            self.assertIn("unknown-session-999", html)
            self.assertIn("/screen/new", html)
            self.assertIn("Return to Home", html)

        # Nav tabs must still never 404
        for nav_url in ["/", "/screen/new", "/history", "/settings"]:
            nav_res = self.client.get(nav_url)
            self.assertEqual(nav_res.status_code, 200, f"Nav tab {nav_url} returned {nav_res.status_code}")

if __name__ == "__main__":
    unittest.main()
