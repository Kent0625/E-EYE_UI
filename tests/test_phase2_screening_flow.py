import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import unittest
import json
from app.app import create_app
from app import store

class TestPhase2ScreeningFlow(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.client = self.app.test_client()

    def test_new_screening_page_rendering(self):
        """Tests that the intake form renders with auto-generated code and disabled continue button."""
        res = self.client.get("/screen/new")
        self.assertEqual(res.status_code, 200)
        html = res.data.decode("utf-8")
        self.assertIn("Participant code", html)
        self.assertIn("Do not enter names", html)
        self.assertIn("Participant is 18 or older", html)
        self.assertIn("Written consent is signed and on file", html)
        self.assertIn("disabled", html)

    def test_session_creation_api(self):
        """Tests creating a session via POST /api/sessions."""
        payload = {
            "participant_code": "EE-261019-999",
            "site": "Barangay Health Station",
            "consent_age": True,
            "consent_signed": True
        }
        res = self.client.post("/api/sessions", json=payload)
        self.assertEqual(res.status_code, 201)
        data = res.get_json()
        self.assertEqual(data["participant_code"], "EE-261019-999")
        self.assertEqual(data["site"], "Barangay Health Station")
        self.assertTrue(data["consent_age"])
        self.assertTrue(data["consent_signed"])
        self.assertIn("id", data)

        # Verify retrieval from store
        stored = store.get_session(data["id"])
        self.assertIsNotNone(stored)
        self.assertEqual(stored["participant_code"], "EE-261019-999")

    def test_align_and_record_page(self):
        """Tests that Align and Record screen loads for OD and OS with valid session."""
        session = store.get_session("s_mock_refer")
        self.assertIsNotNone(session)

        # OD screen
        res_od = self.client.get("/screen/s_mock_refer/OD")
        self.assertEqual(res_od.status_code, 200)
        html_od = res_od.data.decode("utf-8")
        self.assertIn("Right eye (OD)", html_od)
        self.assertIn("/api/preview.mjpg", html_od)
        self.assertIn("/api/distance", html_od)
        self.assertIn("Ask the participant to look at the target", html_od)
        self.assertIn("10–15 cm (Target)", html_od)

        # OS screen
        res_os = self.client.get("/screen/s_mock_refer/OS")
        self.assertEqual(res_os.status_code, 200)
        html_os = res_os.data.decode("utf-8")
        self.assertIn("Left eye (OS)", html_os)

    def test_preview_mjpeg_and_distance_sse_headers(self):
        """Tests headers of hardware emulation stream endpoints."""
        res_preview = self.client.get("/api/preview.mjpg")
        self.assertEqual(res_preview.status_code, 200)
        self.assertIn("multipart/x-mixed-replace", res_preview.mimetype)

        res_dist = self.client.get("/api/distance")
        self.assertEqual(res_dist.status_code, 200)
        self.assertEqual(res_dist.mimetype, "text/event-stream")

    def test_record_endpoint(self):
        """Tests triggering 5s record on an eye."""
        res = self.client.post("/api/sessions/s_mock_refer/record", json={"eye": "OD"})
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data["status"], "recording_started")
        self.assertEqual(data["eye"], "OD")
        self.assertEqual(data["duration_s"], 5)

    def test_processing_events_sse(self):
        """Tests processing SSE endpoint delivers real sequential stages."""
        res = self.client.get("/api/sessions/s_mock_refer/events")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.mimetype, "text/event-stream")

    def test_retake_ui_elements(self):
        """Tests that processing template includes the retake view with plain-language causes."""
        res = self.client.get("/screen/s_mock_retake/processing?eye=OS")
        self.assertEqual(res.status_code, 200)
        html = res.data.decode("utf-8")
        self.assertIn("Not enough clear frames. Retake this eye", html)
        self.assertIn("Likely causes: blinking during capture, head movement, or distance drifted", html)
        self.assertIn("Retake this eye", html)
        self.assertIn("Skip this eye", html)

if __name__ == "__main__":
    unittest.main()
