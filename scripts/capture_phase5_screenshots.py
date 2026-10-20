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
    docs_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "docs", "phase5"))
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

            # -----------------------------------------------------------------
            # A. Settings with Research Mode toggle
            # -----------------------------------------------------------------
            store.set_setting("research_mode", "1")
            for vp in VIEWPORTS:
                w = vp["width"]
                h = vp["height"]
                print(f"Capturing Settings (Research Mode on) at {w}x{h}...")
                page = browser.new_page(viewport={"width": w, "height": h})
                page.goto(f"{base_url}/settings", wait_until="domcontentloaded")
                page.wait_for_selector("#toggle-research-mode")
                time.sleep(0.3)
                page.screenshot(path=os.path.join(docs_dir, f"settings_research_mode_{w}px.png"))
                page.close()

            # -----------------------------------------------------------------
            # B. Result Screen with Research Mode enabled (Ground Truth Section)
            # -----------------------------------------------------------------
            # Seed sample ground truth for s_mock_refer
            refer_session = store.get_session("s_mock_refer")
            if refer_session:
                eyes = refer_session.get("eyes", {})
                if "OD" in eyes:
                    eyes["OD"]["ground_truth"] = {"sphere_D": -1.25, "cylinder_D": -0.50, "se_D": -1.50}
                if "OS" in eyes:
                    eyes["OS"]["ground_truth"] = {"sphere_D": 0.00, "cylinder_D": 0.00, "se_D": 0.00}
                store.update_session("s_mock_refer", eyes=eyes)

            for vp in VIEWPORTS:
                w = vp["width"]
                h = vp["height"]
                print(f"Capturing Result (Research Mode on with Ground Truth) at {w}x{h}...")
                page = browser.new_page(viewport={"width": w, "height": h})
                page.goto(f"{base_url}/screen/s_mock_refer/result", wait_until="domcontentloaded")
                page.wait_for_selector("#ground-truth-section")
                time.sleep(0.3)
                page.screenshot(path=os.path.join(docs_dir, f"result_research_mode_{w}px.png"))
                page.close()

            # -----------------------------------------------------------------
            # C. Result Screen with Research Mode disabled (Standard view)
            # -----------------------------------------------------------------
            store.set_setting("research_mode", "0")
            for vp in VIEWPORTS:
                w = vp["width"]
                h = vp["height"]
                print(f"Capturing Result (Standard, Research Mode off) at {w}x{h}...")
                page = browser.new_page(viewport={"width": w, "height": h})
                page.goto(f"{base_url}/screen/s_mock_refer/result", wait_until="domcontentloaded")
                page.wait_for_selector("#referral-banner")
                time.sleep(0.3)
                page.screenshot(path=os.path.join(docs_dir, f"result_standard_{w}px.png"))
                page.close()

            # -----------------------------------------------------------------
            # D. Home Screen (Cleaned with server storage & zero inline styles)
            # -----------------------------------------------------------------
            for vp in VIEWPORTS:
                w = vp["width"]
                h = vp["height"]
                print(f"Capturing Home Screen at {w}x{h}...")
                page = browser.new_page(viewport={"width": w, "height": h})
                page.goto(f"{base_url}/", wait_until="domcontentloaded")
                page.wait_for_selector("#status-grid")
                time.sleep(0.3)
                page.screenshot(path=os.path.join(docs_dir, f"home_cleaned_{w}px.png"))
                page.close()

            browser.close()
            print("All Phase 5 screenshots successfully captured under docs/phase5/!")

    finally:
        server.shutdown()

if __name__ == "__main__":
    capture_all()
