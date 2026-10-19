import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import time
import socket
import threading
from playwright.sync_api import sync_playwright
from werkzeug.serving import make_server
from app.app import create_app

def find_free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]

class ServerThread(threading.Thread):
    def __init__(self, app, port):
        super().__init__()
        self.server = make_server('127.0.0.1', port, app, threaded=True)
        self.daemon = True

    def run(self):
        self.server.serve_forever()

    def shutdown(self):
        self.server.shutdown()

def test_distance_stability_gate_behavior():
    """
    Test 1: Record is disabled when too far, too close, or just inside the band;
    it enables only after 1.0 s continuously in band;
    it disables again if distance drifts out.
    """
    app = create_app()
    port = find_free_port()
    server = ServerThread(app, port)
    server.start()
    base_url = f"http://127.0.0.1:{port}"
    time.sleep(0.5)

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 390, "height": 844})
            page.goto(f"{base_url}/screen/s_mock_refer/OD")
            page.wait_for_selector("#btn-record")

            # Pause background SSE so test can drive precise scripted sequence
            page.evaluate("if (window.evtSource) window.evtSource.close()")

            # 1. Too far (18.0 cm) -> Record is disabled
            page.evaluate("renderDistance({ cm: 18.0, valid: true })")
            assert page.is_disabled("#btn-record")
            assert "closer" in page.text_content("#distance-badge").lower()

            # 2. Too close (8.5 cm) -> Record is disabled
            page.evaluate("renderDistance({ cm: 8.5, valid: true })")
            assert page.is_disabled("#btn-record")
            assert "back" in page.text_content("#distance-badge").lower()

            # 3. No reading (0.0 cm / invalid) -> Record is disabled
            page.evaluate("renderDistance({ cm: 0.0, valid: false })")
            assert page.is_disabled("#btn-record")
            badge_text = page.text_content("#distance-badge").lower()
            assert "no reading" in badge_text or "no distance reading" in badge_text

            # 4. Just inside band (12.5 cm, t=0) -> Record is STILL disabled
            page.evaluate("renderDistance({ cm: 12.5, valid: true })")
            assert page.is_disabled("#btn-record")
            assert "holding" in page.text_content("#stability-text").lower()

            # 5. After 1.1s continuously in band -> Record ENABLES
            time.sleep(1.1)
            page.evaluate("renderDistance({ cm: 12.6, valid: true })")
            assert page.is_enabled("#btn-record")
            assert "ready" in page.text_content("#record-disabled-reason").lower()

            # 6. Distance drifts out (drifts to 16.5 cm) -> Record immediately DISABLES again
            page.evaluate("renderDistance({ cm: 16.5, valid: true })")
            assert page.is_disabled("#btn-record")
            assert "closer" in page.text_content("#distance-badge").lower()

            # 7. Back in range, wait 1.1s -> re-enables
            page.evaluate("renderDistance({ cm: 13.0, valid: true })")
            assert page.is_disabled("#btn-record")
            time.sleep(1.1)
            page.evaluate("renderDistance({ cm: 13.0, valid: true })")
            assert page.is_enabled("#btn-record")

            browser.close()
    finally:
        server.shutdown()

def test_recording_countdown_and_flow():
    """
    Test 2: The 5 to 0 countdown runs and disables other controls;
    the flow goes OD -> processing -> OS -> processing -> result.
    """
    app = create_app()
    port = find_free_port()
    server = ServerThread(app, port)
    server.start()
    base_url = f"http://127.0.0.1:{port}"
    time.sleep(0.5)

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 390, "height": 844})

            # Create new session from intake
            page.goto(f"{base_url}/screen/new")
            page.check("#chk-age")
            page.check("#chk-consent")
            assert page.is_enabled("#btn-continue")
            page.click("#btn-continue")

            # Navigated to OD Align & Record
            page.wait_for_url("**/screen/*/OD")
            assert "OD" in page.url
            assert "Right eye (OD)" in page.content()

            # Pause background stream to stabilize
            page.evaluate("if (window.evtSource) window.evtSource.close()")
            page.evaluate("renderDistance({ cm: 12.5, valid: true })")
            time.sleep(1.1)
            page.evaluate("renderDistance({ cm: 12.5, valid: true })")
            assert page.is_enabled("#btn-record")

            # Click Record
            page.click("#btn-record")

            # Overlay is visible with countdown and Hold still
            page.wait_for_selector("#recording-overlay", state="visible")
            assert "Hold still" in page.text_content("#recording-overlay")
            assert page.is_disabled("#btn-record")

            # Await completion to processing page
            page.wait_for_url("**/screen/*/processing?eye=OD", timeout=8000)
            assert "Processing" in page.content()

            # Processing advances to OS Align & Record
            page.wait_for_url("**/screen/*/OS", timeout=8000)
            assert "OS" in page.url
            assert "Left eye (OS)" in page.content()

            # Stabilize OS and Record
            page.evaluate("if (window.evtSource) window.evtSource.close()")
            page.evaluate("renderDistance({ cm: 12.5, valid: true })")
            time.sleep(1.1)
            page.evaluate("renderDistance({ cm: 12.5, valid: true })")
            assert page.is_enabled("#btn-record")
            page.click("#btn-record")

            # Second processing advances to Result
            page.wait_for_url("**/screen/*/processing?eye=OS", timeout=8000)
            page.wait_for_url("**/screen/*/result", timeout=8000)
            assert "result" in page.url

            browser.close()
    finally:
        server.shutdown()

def test_retake_fixture_ui():
    """
    Test 3: The retake fixture triggers the retake alert and displays Retake and Skip this eye buttons.
    """
    app = create_app()
    port = find_free_port()
    server = ServerThread(app, port)
    server.start()
    base_url = f"http://127.0.0.1:{port}"
    time.sleep(0.5)

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 390, "height": 844})

            # Navigate to processing with s_mock_retake for OS
            page.goto(f"{base_url}/screen/s_mock_retake/processing?eye=OS")
            
            # Wait for SSE to conclude and display retake view
            page.wait_for_selector("#retake-view", state="visible", timeout=6000)
            assert "Not enough clear frames" in page.text_content("#retake-view")
            assert "blinking" in page.text_content("#retake-view").lower()
            assert page.is_visible("#btn-retake")
            assert page.is_visible("#btn-skip-eye")

            # Click Skip this eye -> Navigates to Result
            page.click("#btn-skip-eye")
            page.wait_for_url("**/screen/s_mock_retake/result")
            assert "result" in page.url

            browser.close()
    finally:
        server.shutdown()

def test_recording_distance_drift_path():
    """
    Test 4: Distance changed during recording path.
    Backend stream emits 'distance_drift' and completes with success=False.
    UI dismisses countdown overlay, shows 'Distance changed during recording. Retake.' alert,
    and resets for realignment.
    """
    app = create_app()
    port = find_free_port()
    server = ServerThread(app, port)
    server.start()
    base_url = f"http://127.0.0.1:{port}"
    time.sleep(0.5)

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 390, "height": 844})
            page.goto(f"{base_url}/screen/s_mock_refer/OD?simulate=drift&fast=1")
            page.wait_for_selector("#btn-record")

            page.evaluate("if (window.evtSource) window.evtSource.close()")
            page.evaluate("renderDistance({ cm: 12.5, valid: true })")
            time.sleep(1.1)
            page.evaluate("renderDistance({ cm: 12.5, valid: true })")
            assert page.is_enabled("#btn-record")

            page.click("#btn-record")
            page.wait_for_selector("#recording-overlay", state="visible")

            page.wait_for_selector("#recording-alert", state="visible", timeout=6000)
            assert page.is_hidden("#recording-overlay")
            alert_text = page.text_content("#recording-alert")
            assert "distance changed" in alert_text.lower()
            assert "retake" in alert_text.lower()

            browser.close()
    finally:
        server.shutdown()

def test_recording_backend_failure_path():
    """
    Test 5: Backend failure during recording.
    Backend stream emits recording_complete with success=False and reason=capture_error.
    UI dismisses countdown overlay and displays capture error alert.
    """
    app = create_app()
    port = find_free_port()
    server = ServerThread(app, port)
    server.start()
    base_url = f"http://127.0.0.1:{port}"
    time.sleep(0.5)

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 390, "height": 844})
            page.goto(f"{base_url}/screen/s_mock_refer/OD?simulate=error&fast=1")
            page.wait_for_selector("#btn-record")

            page.evaluate("if (window.evtSource) window.evtSource.close()")
            page.evaluate("renderDistance({ cm: 12.5, valid: true })")
            time.sleep(1.1)
            page.evaluate("renderDistance({ cm: 12.5, valid: true })")
            assert page.is_enabled("#btn-record")

            page.click("#btn-record")
            page.wait_for_selector("#recording-overlay", state="visible")

            page.wait_for_selector("#recording-alert", state="visible", timeout=6000)
            assert page.is_hidden("#recording-overlay")
            alert_text = page.text_content("#recording-alert")
            assert "failed" in alert_text.lower() or "error" in alert_text.lower()

            browser.close()
    finally:
        server.shutdown()

if __name__ == "__main__":
    test_distance_stability_gate_behavior()
    test_recording_countdown_and_flow()
    test_retake_fixture_ui()
    test_recording_distance_drift_path()
    test_recording_backend_failure_path()
    print("All Phase 2 behavior tests PASSED.")
