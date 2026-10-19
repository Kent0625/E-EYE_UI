import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import time
import socket
import threading
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright
from werkzeug.serving import make_server
from app.app import create_app

VIEWPORTS = [
    {"name": "320px_compact_mobile", "width": 320, "height": 568},
    {"name": "390px_standard_phone", "width": 390, "height": 844},
    {"name": "768px_tablet_portrait", "width": 768, "height": 1024},
    {"name": "1024px_laptop_tablet_land", "width": 1024, "height": 768},
    {"name": "1440px_desktop_workstation", "width": 1440, "height": 900}
]

def find_free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]

class ServerThread(threading.Thread):
    def __init__(self, app, port):
        super().__init__()
        self.server = make_server('127.0.0.1', port, app, threaded=True)
        self.port = port

    def run(self):
        self.server.serve_forever()

    def shutdown(self):
        self.server.shutdown()

def run_visual_and_network_verification():
    app = create_app()
    port = find_free_port()
    server = ServerThread(app, port)
    server.start()
    base_url = f"http://127.0.0.1:{port}"
    print(f"Test server running at {base_url}")
    
    # Wait for server readiness
    time.sleep(1.0)
    
    screenshot_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "artifacts", "screenshots"))
    os.makedirs(screenshot_dir, exist_ok=True)
    
    all_requests = []
    external_requests = []
    
    allowed_hosts = {"127.0.0.1", "localhost", "192.168.4.1"}
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        
        for vp in VIEWPORTS:
            vp_name = vp["name"]
            width = vp["width"]
            height = vp["height"]
            vp_dir = os.path.join(screenshot_dir, f"{width}px")
            os.makedirs(vp_dir, exist_ok=True)
            
            context = browser.new_context(viewport={"width": width, "height": height})
            page = context.new_page()
            
            # Monitor network requests
            def handle_request(req):
                all_requests.append(req.url)
                parsed = urlparse(req.url)
                if parsed.hostname not in allowed_hosts and parsed.scheme in ("http", "https"):
                    external_requests.append(req.url)
            
            page.on("request", handle_request)
            
            # 1. Test Home Screen
            page.goto(f"{base_url}/", wait_until="networkidle")
            page.wait_for_timeout(400)
            
            # Verify no horizontal scroll
            has_hscroll = page.evaluate("() => document.documentElement.scrollWidth > window.innerWidth")
            if has_hscroll:
                print(f"[ERROR] Horizontal scroll detected at {width}px on Home page!")
            else:
                print(f"[PASS] Zero horizontal scroll at {width}px on Home page.")
                
            home_shot = os.path.join(vp_dir, "01_home.png")
            page.screenshot(path=home_shot, full_page=True)
            print(f"Saved: {home_shot}")

            # 2. Test Settings Screen
            page.goto(f"{base_url}/settings", wait_until="networkidle")
            page.wait_for_timeout(300)
            settings_shot = os.path.join(vp_dir, "02_settings.png")
            page.screenshot(path=settings_shot, full_page=True)
            print(f"Saved: {settings_shot}")
            
            context.close()
            
        browser.close()
        
    server.shutdown()
    
    print("\n--- Network Isolation Audit ---")
    print(f"Total internal requests: {len(all_requests)}")
    print(f"External requests detected: {len(external_requests)}")
    
    # Write network log
    net_log_path = os.path.join(screenshot_dir, "network_log.txt")
    with open(net_log_path, "w", encoding="utf-8") as f:
        f.write(f"=== E-Eye Offline Network Audit ===\n")
        f.write(f"Timestamp: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"Allowed Hosts: {allowed_hosts}\n")
        f.write(f"Total Requests Logged: {len(all_requests)}\n")
        f.write(f"External Violations: {len(external_requests)}\n\n")
        f.write("--- Request Log ---\n")
        for u in sorted(set(all_requests)):
            f.write(f"{u}\n")
            
    if external_requests:
        print("[FAIL] Outbound external network requests detected!")
        for er in external_requests:
            print(f"  VIOLATION: {er}")
        sys.exit(1)
    else:
        print("[PASS] STRICT 100% OFFLINE COMPLIANCE CONFIRMED (0 external requests)")

if __name__ == "__main__":
    run_visual_and_network_verification()
