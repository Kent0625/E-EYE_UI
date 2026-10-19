import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import time
import socket
import threading
import pytest
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

WIDTHS = [320, 390, 768, 1024, 1440]

SCREENS = [
    ("/", "home"),
    ("/screen/new", "new_screening"),
    ("/screen/s_mock_refer/OD", "align_record"),
    ("/screen/s_mock_refer/processing?eye=OD", "processing"),
    ("/screen/s_mock_retake/processing?eye=OS", "retake"),
    ("/history", "history"),
    ("/settings", "settings")
]

def test_no_horizontal_overflow_scroll():
    """
    Calls window.scrollTo(1000, 0) and asserts scrollX == 0
    on every screen at all 5 widths (320, 390, 768, 1024, 1440).
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
            for path, name in SCREENS:
                for w in WIDTHS:
                    h = 568 if w == 320 else 844
                    page = browser.new_page(viewport={"width": w, "height": h})
                    page.goto(f"{base_url}{path}")
                    page.wait_for_load_state("domcontentloaded")
                    time.sleep(0.15)

                    # Trigger scroll to 1000px horizontally
                    page.evaluate("window.scrollTo(1000, 0)")
                    scroll_x = page.evaluate("window.scrollX")

                    assert scroll_x == 0, (
                        f"Horizontal scroll detected on {name} ({path}) at width {w}px: "
                        f"window.scrollX = {scroll_x}"
                    )

                    # Also verify document scrollWidth does not exceed viewport width
                    scroll_w = page.evaluate("document.documentElement.scrollWidth")
                    inner_w = page.evaluate("window.innerWidth")
                    assert scroll_w <= inner_w, (
                        f"scrollWidth ({scroll_w}) > innerWidth ({inner_w}) on {name} at {w}px"
                    )
                    page.close()
            browser.close()
    finally:
        server.shutdown()

def test_phone_320x568_align_and_record_no_scroll_visibility():
    """
    At 320x568 on Align & Record:
    Preview, large distance number/state, and Record button must ALL be visible
    with no scrolling (window.scrollY == 0).
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
            page = browser.new_page(viewport={"width": 320, "height": 568})
            page.goto(f"{base_url}/screen/s_mock_refer/OD")
            page.wait_for_selector("#btn-record")
            time.sleep(0.2)

            # Check scroll position is strictly 0
            scroll_y = page.evaluate("window.scrollY")
            assert scroll_y == 0, f"Expected initial window.scrollY == 0, got {scroll_y}"

            viewport_height = 568

            # 1. Preview element is visible within viewport
            preview_box = page.locator("#preview-wrapper").bounding_box()
            assert preview_box is not None, "Preview wrapper not rendered"
            assert preview_box["y"] >= 0 and (preview_box["y"] + preview_box["height"]) <= viewport_height, (
                f"Preview wrapper is out of viewport: y={preview_box['y']}, h={preview_box['height']}"
            )

            # 2. Distance number and state badge are visible within viewport
            dist_val_box = page.locator("#distance-val").bounding_box()
            assert dist_val_box is not None, "Distance val element not rendered"
            assert dist_val_box["y"] >= 0 and (dist_val_box["y"] + dist_val_box["height"]) <= viewport_height, (
                f"Distance value out of viewport: y={dist_val_box['y']}, h={dist_val_box['height']}"
            )

            dist_badge_box = page.locator("#distance-badge").bounding_box()
            assert dist_badge_box is not None, "Distance badge element not rendered"
            assert dist_badge_box["y"] >= 0 and (dist_badge_box["y"] + dist_badge_box["height"]) <= viewport_height, (
                f"Distance badge out of viewport: y={dist_badge_box['y']}, h={dist_badge_box['height']}"
            )

            # 3. Record button in sticky action bar is visible within viewport
            btn_box = page.locator("#btn-record").bounding_box()
            assert btn_box is not None, "Record button not rendered"
            assert btn_box["y"] >= 0 and (btn_box["y"] + btn_box["height"]) <= viewport_height, (
                f"Record button out of viewport: y={btn_box['y']}, h={btn_box['height']}"
            )

            # Touch target of button >= 48x48
            assert btn_box["height"] >= 48, f"Button height {btn_box['height']} < 48px"
            assert btn_box["width"] >= 48, f"Button width {btn_box['width']} < 48px"

            browser.close()
    finally:
        server.shutdown()

if __name__ == "__main__":
    test_no_horizontal_overflow_scroll()
    test_phone_320x568_align_and_record_no_scroll_visibility()
    print("All overflow and 320x568 visibility tests PASSED.")
