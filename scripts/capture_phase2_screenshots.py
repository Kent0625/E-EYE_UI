import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import time
import socket
import threading
import shutil
from playwright.sync_api import sync_playwright
from werkzeug.serving import make_server
from app.app import create_app

VIEWPORTS = [
    {"name": "320px", "width": 320, "height": 568},
    {"name": "390px", "width": 390, "height": 844},
    {"name": "768px", "width": 768, "height": 1024},
    {"name": "1024px", "width": 1024, "height": 768},
    {"name": "1440px", "width": 1440, "height": 900}
]

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

def capture_all():
    app = create_app()
    port = find_free_port()
    server = ServerThread(app, port)
    server.start()
    base_url = f"http://127.0.0.1:{port}"
    time.sleep(0.5)

    local_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "screenshots", "phase2"))
    brain_dir = os.environ.get("AGY_BRAIN_DIR")
    os.makedirs(local_dir, exist_ok=True)
    if brain_dir:
        os.makedirs(brain_dir, exist_ok=True)

    states = [
        # (state_key, path, action_func)
        ("new_empty", "/screen/new", lambda p: None),
        ("new_ticked", "/screen/new", lambda p: (p.check("#chk-age"), p.check("#chk-consent"))),
        ("align_too_close", "/screen/s_mock_refer/OD", lambda p: (
            p.evaluate("if(window.evtSource) window.evtSource.close()"),
            p.evaluate("renderDistance({ cm: 8.5, valid: true })")
        )),
        ("align_distance_ok", "/screen/s_mock_refer/OD", lambda p: (
            p.evaluate("if(window.evtSource) window.evtSource.close()"),
            p.evaluate("renderDistance({ cm: 12.5, valid: true })"),
            time.sleep(1.1),
            p.evaluate("renderDistance({ cm: 12.5, valid: true })")
        )),
        ("align_too_far", "/screen/s_mock_refer/OD", lambda p: (
            p.evaluate("if(window.evtSource) window.evtSource.close()"),
            p.evaluate("renderDistance({ cm: 18.0, valid: true })")
        )),
        ("align_no_reading", "/screen/s_mock_refer/OD", lambda p: (
            p.evaluate("if(window.evtSource) window.evtSource.close()"),
            p.evaluate("renderDistance({ cm: 0.0, valid: false })")
        )),
        ("align_record_disabled", "/screen/s_mock_refer/OD", lambda p: (
            p.evaluate("if(window.evtSource) window.evtSource.close()"),
            p.evaluate("renderDistance({ cm: 12.5, valid: true })")
        )),
        ("align_countdown_running", "/screen/s_mock_refer/OD", lambda p: (
            p.evaluate("if(window.evtSource) window.evtSource.close()"),
            p.evaluate("renderDistance({ cm: 12.5, valid: true })"),
            time.sleep(1.1),
            p.evaluate("renderDistance({ cm: 12.5, valid: true })"),
            p.click("#btn-record"),
            p.wait_for_selector("#recording-overlay", state="visible")
        )),
        ("align_preview_unavailable", "/screen/s_mock_refer/OD", lambda p: (
            p.evaluate("if(window.evtSource) window.evtSource.close()"),
            p.evaluate("document.getElementById('stream-fallback').style.display = 'flex'")
        )),
        ("processing", "/screen/s_mock_refer/processing?eye=OD", lambda p: time.sleep(0.5)),
        ("retake", "/screen/s_mock_retake/processing?eye=OS", lambda p: p.wait_for_selector("#retake-view", state="visible", timeout=6000))
    ]

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)

            # Capture 55 viewport screenshots across the 11 states
            for state_key, path, action in states:
                for vp in VIEWPORTS:
                    w = vp["width"]
                    h = vp["height"]
                    ctx = browser.new_context(viewport={"width": w, "height": h})
                    page = ctx.new_page()

                    page.goto(f"{base_url}{path}", wait_until="networkidle")
                    time.sleep(0.3)
                    action(page)
                    time.sleep(0.2)

                    filename = f"{state_key}_{w}px.png"
                    # Viewport-sized screenshot (full_page=False)
                    page.screenshot(path=local_path, full_page=False)
                    if brain_dir:
                        brain_path = os.path.join(brain_dir, filename)
                        shutil.copy2(local_path, brain_path)
                    ctx.close()

            # Capture special 320px home screen scrolled to bottom
            ctx_320 = browser.new_context(viewport={"width": 320, "height": 568})
            page_320 = ctx_320.new_page()
            page_320.goto(f"{base_url}/", wait_until="networkidle")
            time.sleep(0.3)
            page_320.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            time.sleep(0.3)
            scrolled_name = "home_scrolled_320px.png"
            p1 = os.path.join(local_dir, scrolled_name)
            page_320.screenshot(path=p1, full_page=False)
            if brain_dir:
                p2 = os.path.join(brain_dir, scrolled_name)
                shutil.copy2(p1, p2)
            ctx_320.close()

            browser.close()
    finally:
        server.shutdown()

    print(f"\nAll 56 Phase 2 screenshots successfully captured and stored in:\n  {local_dir}\n  {brain_dir}")

if __name__ == "__main__":
    capture_all()
