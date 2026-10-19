import os
import sys
import time
import socket
import threading
from playwright.sync_api import sync_playwright
from werkzeug.serving import make_server

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from app.app import create_app

VIEWPORTS = [
    {"name": "320px", "width": 320, "height": 568},
    {"name": "390px", "width": 390, "height": 844},
    {"name": "768px", "width": 768, "height": 1024},
    {"name": "1024px", "width": 1024, "height": 768},
    {"name": "1440px", "width": 1440, "height": 900}
]

FIXTURES = [
    {"key": "refer", "id": "s_mock_refer"},
    {"key": "norefer", "id": "s_mock_norefer"},
    {"key": "retake", "id": "s_mock_retake"}
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

def capture():
    os.makedirs("docs/phase3", exist_ok=True)
    app = create_app()
    port = find_free_port()
    server = ServerThread(app, port)
    server.start()
    base_url = f"http://127.0.0.1:{port}"
    time.sleep(0.5)

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)

            for fix in FIXTURES:
                for vp in VIEWPORTS:
                    page = browser.new_page(viewport={"width": vp["width"], "height": vp["height"]})
                    url = f"{base_url}/screen/{fix['id']}/result"
                    page.goto(url, wait_until="domcontentloaded")
                    page.wait_for_selector("#referral-banner")
                    # allow fonts/icons to settle
                    page.wait_for_timeout(300)

                    out_path = f"docs/phase3/{fix['key']}_{vp['name']}.png"
                    # Viewport-sized screenshot (full_page=False) to reflect true device display
                    page.screenshot(path=out_path, full_page=False)
                    print(f"Captured {out_path} ({vp['width']}x{vp['height']})")

                    # If 320px mobile, also capture scrolled-to-bottom to prove nothing is hidden under nav bar
                    if vp["width"] == 320:
                        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                        page.wait_for_timeout(200)
                        scrolled_path = f"docs/phase3/{fix['key']}_320px_scrolled.png"
                        page.screenshot(path=scrolled_path, full_page=False)
                        print(f"Captured {scrolled_path} ({vp['width']}x{vp['height']} scrolled)")

                        if fix['key'] == 'retake':
                            # Scroll directly to the OS card showing the retake button
                            page.locator(".eye-card").nth(1).scroll_into_view_if_needed()
                            page.wait_for_timeout(200)
                            os_card_path = "docs/phase3/retake_320px_os_card.png"
                            page.screenshot(path=os_card_path, full_page=False)
                            print(f"Captured {os_card_path} (OS retake card visible)")

                    page.close()

            # Capture header toggle detail at 320px
            page = browser.new_page(viewport={"width": 320, "height": 568})
            page.goto(f"{base_url}/screen/s_mock_refer/result", wait_until="domcontentloaded")
            page.wait_for_selector(".app-header")
            page.wait_for_timeout(300)
            header_el = page.locator(".app-header")
            header_el.screenshot(path="docs/phase3/header_toggle_320px.png")
            print("Captured docs/phase3/header_toggle_320px.png")
            page.close()

            browser.close()
    finally:
        server.shutdown()

if __name__ == "__main__":
    capture()
