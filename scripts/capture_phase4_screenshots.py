import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import time
import socket
import threading
from playwright.sync_api import sync_playwright
from werkzeug.serving import make_server
from app.app import create_app
from app import store
from app.mock.fixtures import seed_fixtures_if_empty

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
    docs_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "docs", "phase4"))
    os.makedirs(docs_dir, exist_ok=True)

    # 1. Ensure mock sessions are seeded
    seed_fixtures_if_empty(store)

    app = create_app()
    port = find_free_port()
    server = ServerThread(app, port)
    server.start()
    base_url = f"http://127.0.0.1:{port}"
    time.sleep(0.5)

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)

            for vp in VIEWPORTS:
                w = vp["width"]
                h = vp["height"]
                name = vp["name"]
                print(f"Capturing Phase 4 screenshots for {name} ({w}x{h})...")

                page = browser.new_page(viewport={"width": w, "height": h})

                # A. History Populated
                page.goto(f"{base_url}/history", wait_until="domcontentloaded")
                page.wait_for_selector(".history-item-card")
                time.sleep(0.3)
                page.screenshot(path=os.path.join(docs_dir, f"history_populated_{w}px.png"))

                # B. History Delete Confirmation Modal
                first_delete_btn = page.locator(".history-delete-btn").first
                first_delete_btn.click()
                page.locator("#delete-modal").wait_for(state="visible")
                time.sleep(0.2)
                page.screenshot(path=os.path.join(docs_dir, f"history_delete_confirm_{w}px.png"))
                page.click("#btn-cancel-delete")
                page.locator("#delete-modal").wait_for(state="hidden")
                time.sleep(0.2)

                # C. History No Match Search
                page.fill("#history-search", "EE-NONEXISTENT-999")
                page.wait_for_selector("#history-no-match-card")
                time.sleep(0.2)
                page.screenshot(path=os.path.join(docs_dir, f"history_no_match_{w}px.png"))
                page.click("#btn-clear-search")
                page.wait_for_selector(".history-item-card")
                time.sleep(0.2)

                # D. Settings
                page.goto(f"{base_url}/settings", wait_until="domcontentloaded")
                page.wait_for_selector(".settings-container")
                time.sleep(0.3)
                page.screenshot(path=os.path.join(docs_dir, f"settings_{w}px.png"))

                page.close()

            # E. History Empty (requires clearing sessions temporarily)
            print("Capturing History Empty screenshots across viewports...")
            # Backup existing sessions
            all_sessions = store.list_sessions()
            store.delete_all_sessions()

            for vp in VIEWPORTS:
                w = vp["width"]
                h = vp["height"]
                page = browser.new_page(viewport={"width": w, "height": h})
                page.goto(f"{base_url}/history", wait_until="domcontentloaded")
                page.wait_for_selector("#history-empty-card")
                time.sleep(0.2)
                page.screenshot(path=os.path.join(docs_dir, f"history_empty_{w}px.png"))
                page.close()

            # Restore sessions
            for s in all_sessions:
                store.create_session(s)
            seed_fixtures_if_empty(store)

            browser.close()
            print("All Phase 4 screenshots successfully captured in docs/phase4/!")

    finally:
        server.shutdown()

if __name__ == "__main__":
    capture_all()
