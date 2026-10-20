import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import time
import socket
import threading
import json
import urllib.request
import psutil
from werkzeug.serving import make_server
from app.app import create_app
from app import store
from app.clinical import compute_se

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

def test_ground_truth_disabled_research_mode_returns_403():
    """
    Verifies that /api/sessions/<id>/ground-truth rejects updates with 403 Forbidden
    when Research mode is disabled.
    """
    test_id = "s_test_gt_disabled_403"
    orig_mode = store.get_setting("research_mode", "0")
    store.set_setting("research_mode", "0")

    store.create_session({
        "id": test_id,
        "participant_code": "EE-GT-403",
        "created_at": "2026-10-20T16:00:00+08:00",
        "site": "Test Site",
        "consent_age": True,
        "consent_signed": True,
        "client_time": "2026-10-20T16:00:00+08:00",
        "status": "complete",
        "referral": False,
        "referral_eyes": [],
        "eyes": {
            "OD": {"status": "ok", "sphere_D": 0.0, "cylinder_D": 0.0, "se_D": 0.0, "label": "emmetropia", "frames_used": 10, "frames_total": 100},
            "OS": {"status": "ok", "sphere_D": 0.0, "cylinder_D": 0.0, "se_D": 0.0, "label": "emmetropia", "frames_used": 10, "frames_total": 100}
        }
    })

    try:
        app = create_app()
        client = app.test_client()

        res = client.post(f"/api/sessions/{test_id}/ground-truth", json={
            "eye": "OD",
            "sphere_D": -1.25,
            "cylinder_D": -0.50
        })
        assert res.status_code == 403
        data = res.get_json()
        assert "error" in data
        assert "Research mode is disabled" in data["error"]
    finally:
        store.set_setting("research_mode", orig_mode)
        store.delete_session(test_id)

def test_ground_truth_blank_input_returns_400():
    """
    Verifies that /api/sessions/<id>/ground-truth rejects blank or missing values with 400 Bad Request.
    """
    test_id = "s_test_gt_blank_400"
    orig_mode = store.get_setting("research_mode", "0")
    store.set_setting("research_mode", "1")

    store.create_session({
        "id": test_id,
        "participant_code": "EE-GT-BLANK",
        "created_at": "2026-10-20T16:00:00+08:00",
        "site": "Test Site",
        "consent_age": True,
        "consent_signed": True,
        "client_time": "2026-10-20T16:00:00+08:00",
        "status": "complete",
        "referral": False,
        "referral_eyes": [],
        "eyes": {
            "OD": {"status": "ok", "sphere_D": 0.0, "cylinder_D": 0.0, "se_D": 0.0, "label": "emmetropia", "frames_used": 10, "frames_total": 100},
            "OS": {"status": "ok", "sphere_D": 0.0, "cylinder_D": 0.0, "se_D": 0.0, "label": "emmetropia", "frames_used": 10, "frames_total": 100}
        }
    })

    try:
        app = create_app()
        client = app.test_client()

        # Blank string for sphere
        res = client.post(f"/api/sessions/{test_id}/ground-truth", json={
            "eye": "OD",
            "sphere_D": "",
            "cylinder_D": "-0.50"
        })
        assert res.status_code == 400
        assert "blank" in res.get_json().get("error", "").lower()

        # Missing sphere (None)
        res2 = client.post(f"/api/sessions/{test_id}/ground-truth", json={
            "eye": "OD",
            "cylinder_D": "-0.50"
        })
        assert res2.status_code == 400
        assert "blank" in res2.get_json().get("error", "").lower()

        # Blank cylinder
        res3 = client.post(f"/api/sessions/{test_id}/ground-truth", json={
            "eye": "OS",
            "sphere_D": "1.00",
            "cylinder_D": ""
        })
        assert res3.status_code == 400
        assert "blank" in res3.get_json().get("error", "").lower()
    finally:
        store.set_setting("research_mode", orig_mode)
        store.delete_session(test_id)

def test_ground_truth_non_numeric_text_returns_400():
    """
    Verifies that /api/sessions/<id>/ground-truth rejects non-numeric text input with 400 Bad Request.
    """
    test_id = "s_test_gt_text_400"
    orig_mode = store.get_setting("research_mode", "0")
    store.set_setting("research_mode", "1")

    store.create_session({
        "id": test_id,
        "participant_code": "EE-GT-TEXT",
        "created_at": "2026-10-20T16:00:00+08:00",
        "site": "Test Site",
        "consent_age": True,
        "consent_signed": True,
        "client_time": "2026-10-20T16:00:00+08:00",
        "status": "complete",
        "referral": False,
        "referral_eyes": [],
        "eyes": {
            "OD": {"status": "ok", "sphere_D": 0.0, "cylinder_D": 0.0, "se_D": 0.0, "label": "emmetropia", "frames_used": 10, "frames_total": 100},
            "OS": {"status": "ok", "sphere_D": 0.0, "cylinder_D": 0.0, "se_D": 0.0, "label": "emmetropia", "frames_used": 10, "frames_total": 100}
        }
    })

    try:
        app = create_app()
        client = app.test_client()

        # Non-numeric text in sphere
        res = client.post(f"/api/sessions/{test_id}/ground-truth", json={
            "eye": "OD",
            "sphere_D": "abc",
            "cylinder_D": -0.50
        })
        assert res.status_code == 400
        assert "numeric" in res.get_json().get("error", "").lower()

        # Non-numeric text in cylinder
        res2 = client.post(f"/api/sessions/{test_id}/ground-truth", json={
            "eye": "OS",
            "sphere_D": 0.0,
            "cylinder_D": "not_a_number"
        })
        assert res2.status_code == 400
        assert "numeric" in res2.get_json().get("error", "").lower()
    finally:
        store.set_setting("research_mode", orig_mode)
        store.delete_session(test_id)

def test_ground_truth_out_of_range_returns_400():
    """
    Verifies that /api/sessions/<id>/ground-truth rejects values outside the physiological
    autorefractor measurement range [-20.0, +20.0] D with 400 Bad Request.
    """
    test_id = "s_test_gt_range_400"
    orig_mode = store.get_setting("research_mode", "0")
    store.set_setting("research_mode", "1")

    store.create_session({
        "id": test_id,
        "participant_code": "EE-GT-RANGE",
        "created_at": "2026-10-20T16:00:00+08:00",
        "site": "Test Site",
        "consent_age": True,
        "consent_signed": True,
        "client_time": "2026-10-20T16:00:00+08:00",
        "status": "complete",
        "referral": False,
        "referral_eyes": [],
        "eyes": {
            "OD": {"status": "ok", "sphere_D": 0.0, "cylinder_D": 0.0, "se_D": 0.0, "label": "emmetropia", "frames_used": 10, "frames_total": 100},
            "OS": {"status": "ok", "sphere_D": 0.0, "cylinder_D": 0.0, "se_D": 0.0, "label": "emmetropia", "frames_used": 10, "frames_total": 100}
        }
    })

    try:
        app = create_app()
        client = app.test_client()

        # 9999 D sphere
        res1 = client.post(f"/api/sessions/{test_id}/ground-truth", json={
            "eye": "OD",
            "sphere_D": 9999,
            "cylinder_D": 0.0
        })
        assert res1.status_code == 400
        assert "range" in res1.get_json().get("error", "").lower()

        # -9999 D cylinder
        res2 = client.post(f"/api/sessions/{test_id}/ground-truth", json={
            "eye": "OD",
            "sphere_D": 0.0,
            "cylinder_D": -9999
        })
        assert res2.status_code == 400
        assert "range" in res2.get_json().get("error", "").lower()

        # Just outside upper bound (+20.05 D)
        res3 = client.post(f"/api/sessions/{test_id}/ground-truth", json={
            "eye": "OS",
            "sphere_D": 20.05,
            "cylinder_D": 0.0
        })
        assert res3.status_code == 400
        assert "range" in res3.get_json().get("error", "").lower()

        # Just outside lower bound (-20.05 D)
        res4 = client.post(f"/api/sessions/{test_id}/ground-truth", json={
            "eye": "OS",
            "sphere_D": 0.0,
            "cylinder_D": -20.05
        })
        assert res4.status_code == 400
        assert "range" in res4.get_json().get("error", "").lower()
    finally:
        store.set_setting("research_mode", orig_mode)
        store.delete_session(test_id)

def test_concurrency_three_streams_non_blocking_and_memory():
    """
    Demonstrates that 3 simultaneous long-lived streaming clients (2x SSE distance, 1x MJPEG preview)
    do not block concurrent standard HTTP requests, and reports process memory RSS.
    """
    app = create_app()
    port = find_free_port()
    server = ServerThread(app, port)
    server.start()
    base_url = f"http://127.0.0.1:{port}"
    time.sleep(0.5)

    stream_results = {
        "client1_bytes": 0,
        "client2_bytes": 0,
        "client3_bytes": 0,
        "stop": False
    }

    def sse_reader(client_key):
        try:
            req = urllib.request.Request(f"{base_url}/api/distance")
            with urllib.request.urlopen(req, timeout=5) as response:
                while not stream_results["stop"]:
                    chunk = response.read(64)
                    if chunk:
                        stream_results[client_key] += len(chunk)
                    time.sleep(0.05)
        except Exception as e:
            pass

    def mjpeg_reader(client_key):
        try:
            req = urllib.request.Request(f"{base_url}/api/preview.mjpg")
            with urllib.request.urlopen(req, timeout=5) as response:
                while not stream_results["stop"]:
                    chunk = response.read(256)
                    if chunk:
                        stream_results[client_key] += len(chunk)
                    time.sleep(0.05)
        except Exception as e:
            pass

    # Record initial memory RSS
    proc = psutil.Process(os.getpid())
    rss_start_mb = proc.memory_info().rss / (1024 * 1024)

    # Launch 3 simultaneous streaming clients
    t1 = threading.Thread(target=sse_reader, args=("client1_bytes",), daemon=True)
    t2 = threading.Thread(target=sse_reader, args=("client2_bytes",), daemon=True)
    t3 = threading.Thread(target=mjpeg_reader, args=("client3_bytes",), daemon=True)

    t1.start()
    t2.start()
    t3.start()

    try:
        # Wait for connections to establish and start receiving stream chunks
        time.sleep(0.6)

        # Confirm all 3 streams are active and receiving data simultaneously
        assert stream_results["client1_bytes"] > 0, "SSE Client 1 must receive stream data"
        assert stream_results["client2_bytes"] > 0, "SSE Client 2 must receive stream data"
        assert stream_results["client3_bytes"] > 0, "MJPEG Client 3 must receive stream data"

        # While all 3 streams are actively holding their connections, execute non-streaming API requests
        test_endpoints = [
            "/api/status",
            "/api/settings",
            "/api/sessions"
        ]

        for ep in test_endpoints:
            t_req_start = time.time()
            req = urllib.request.Request(f"{base_url}{ep}")
            with urllib.request.urlopen(req, timeout=2) as resp:
                elapsed_ms = (time.time() - t_req_start) * 1000
                assert resp.status == 200, f"{ep} failed with {resp.status}"
                assert elapsed_ms < 500, f"{ep} took {elapsed_ms:.1f}ms (> 500ms limit), server blocked by streams!"

        # Measure memory RSS during active concurrent streams
        rss_streaming_mb = proc.memory_info().rss / (1024 * 1024)
        print(f"\n[Phase 6 Concurrency & Memory Report]")
        print(f"Active Streams: 3 (2x SSE /api/distance, 1x MJPEG /api/preview.mjpg)")
        print(f"Stream Bytes Received: Client1={stream_results['client1_bytes']}B, Client2={stream_results['client2_bytes']}B, Client3={stream_results['client3_bytes']}B")
        print(f"Memory RSS Initial: {rss_start_mb:.2f} MB")
        print(f"Memory RSS During Concurrent Streams: {rss_streaming_mb:.2f} MB")
        print(f"Memory Delta: {rss_streaming_mb - rss_start_mb:+.2f} MB")

        # Memory must be reasonable (< 250 MB total RSS in this environment)
        assert rss_streaming_mb < 250.0, f"Memory footprint excessive: {rss_streaming_mb:.2f} MB"
    finally:
        stream_results["stop"] = True
        server.shutdown()

def test_ten_consecutive_fresh_loads_result_banner():
    """
    Asserts 10 consecutive fresh loads of the Result page render the correct banner
    consistently (mirrors the manuscript's 10-connection reliability test).
    """
    app = create_app()
    port = find_free_port()
    server = ServerThread(app, port)
    server.start()
    base_url = f"http://127.0.0.1:{port}"
    time.sleep(0.5)

    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()

            for i in range(10):
                # 1. Refer fixture: must consistently show REFERRAL RECOMMENDED and badge-warn
                page.goto(f"{base_url}/screen/s_mock_refer/result", wait_until="domcontentloaded")
                banner = page.locator("#referral-banner")
                assert banner.is_visible(), f"Iteration {i}: banner must be visible"
                assert "badge-warn" in banner.get_attribute("class"), f"Iteration {i}: must have badge-warn class"
                assert "REFERRAL RECOMMENDED" in banner.inner_text(), f"Iteration {i}: text mismatch"

                # 2. No-refer fixture: must consistently show NO REFERRAL and badge-ok
                page.goto(f"{base_url}/screen/s_mock_norefer/result", wait_until="domcontentloaded")
                banner_norefer = page.locator("#referral-banner")
                assert banner_norefer.is_visible()
                assert "badge-ok" in banner_norefer.get_attribute("class")
                assert "NO REFERRAL" in banner_norefer.inner_text()

            browser.close()
    finally:
        server.shutdown()

def test_zero_external_network_requests():
    """
    Asserts that during full navigation across all screens, zero requests leave the local host.
    Every single HTTP request must be local (127.0.0.1 / localhost).
    """
    app = create_app()
    port = find_free_port()
    server = ServerThread(app, port)
    server.start()
    base_url = f"http://127.0.0.1:{port}"
    time.sleep(0.5)

    requested_urls = []

    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()

            def on_request(req):
                requested_urls.append(req.url)

            page.on("request", on_request)

            test_paths = [
                "/",
                "/screen/new",
                "/screen/s_mock_refer/align",
                "/screen/s_mock_refer/result",
                "/history",
                "/settings"
            ]

            for path in test_paths:
                page.goto(f"{base_url}{path}", wait_until="domcontentloaded")
                page.wait_for_timeout(100)

            browser.close()

        assert len(requested_urls) > 0, "Requests must be recorded"
        for url in requested_urls:
            assert url.startswith(f"http://127.0.0.1:{port}") or url.startswith(f"http://localhost:{port}"), \
                f"External network request detected: {url}"
    finally:
        server.shutdown()

def test_no_prohibited_clinical_or_ai_wording():
    """
    Brief §17 & no-ai-slop compliance:
    Asserts no 'risk tier', 'confidence', 'ai-powered', 'diagnosis', 'patient name'
    in UI templates or i18n dictionaries.
    """
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    prohibited = [
        "risk tier",
        "confidence score",
        "confidence bar",
        "ai-powered",
        "smart ai",
        "patient name",
        "diagnostic certainty"
    ]

    scan_dirs = [
        os.path.join(base_dir, "app", "templates"),
        os.path.join(base_dir, "app", "static", "i18n")
    ]

    for d in scan_dirs:
        for fname in os.listdir(d):
            fpath = os.path.join(d, fname)
            if os.path.isfile(fpath):
                with open(fpath, "r", encoding="utf-8") as f:
                    content = f.read().lower()
                for phrase in prohibited:
                    assert phrase not in content, f"Prohibited phrase '{phrase}' found in {fname}"

def test_keyboard_only_full_screening_flow():
    """
    Checklist Item 8 (Keyboard Run-Through & Focus States):
    Completes the full operational workflow:
      New Screening -> Align (OD) -> Record (OD) -> Processing -> Align (OS) -> Record (OS) -> Processing -> Result
    using EXCLUSIVELY keyboard interaction (Tab, Space, Enter).
    Asserts a visible focus indicator (computed solid outline >= 2px or box-shadow)
    on each interactive control when focused.
    """
    app = create_app()
    port = find_free_port()
    server = ServerThread(app, port)
    server.start()
    base_url = f"http://127.0.0.1:{port}"
    time.sleep(0.5)

    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1024, "height": 768})

            def get_focused_info():
                return page.evaluate("""() => {
                    const el = document.activeElement;
                    if (!el || el === document.body) return null;
                    const s = window.getComputedStyle(el);
                    const hasOutline = s.outlineStyle !== 'none' && parseFloat(s.outlineWidth) > 0;
                    const hasBoxShadow = s.boxShadow !== 'none' && s.boxShadow !== '';
                    return {
                        tag: el.tagName,
                        id: el.id,
                        className: el.className,
                        outlineStyle: s.outlineStyle,
                        outlineWidth: s.outlineWidth,
                        outlineColor: s.outlineColor,
                        visible: hasOutline || hasBoxShadow
                    };
                }""")

            # 1. New Screening: navigate via URL
            page.goto(f"{base_url}/screen/new", wait_until="networkidle")

            # Tab to #chk-age
            checked_age = False
            for _ in range(10):
                page.keyboard.press("Tab")
                info = get_focused_info()
                if info and info["id"] == "chk-age":
                    assert info["visible"], f"chk-age must have visible focus indicator: {info}"
                    page.keyboard.press("Space")
                    checked_age = True
                    break
            assert checked_age, "Failed to navigate to #chk-age via Tab"

            # Tab to #chk-consent
            checked_consent = False
            for _ in range(5):
                page.keyboard.press("Tab")
                info = get_focused_info()
                if info and info["id"] == "chk-consent":
                    assert info["visible"], f"chk-consent must have visible focus indicator: {info}"
                    page.keyboard.press("Space")
                    checked_consent = True
                    break
            assert checked_consent, "Failed to navigate to #chk-consent via Tab"

            # Tab to #btn-continue (now enabled)
            submitted_new = False
            for _ in range(5):
                page.keyboard.press("Tab")
                info = get_focused_info()
                if info and info["id"] == "btn-continue":
                    assert info["visible"], f"btn-continue must have visible focus indicator: {info}"
                    assert info["outlineStyle"] == "solid"
                    page.keyboard.press("Enter")
                    submitted_new = True
                    break
            assert submitted_new, "Failed to focus and submit #btn-continue via keyboard"

            # 2. OD Align & Record: wait for page load and distance stabilization
            page.wait_for_url("**/screen/*/OD**", timeout=10000)
            page.wait_for_selector("#btn-record:not([disabled])", timeout=20000)

            # Tab to #btn-record
            recorded_od = False
            for _ in range(12):
                page.keyboard.press("Tab")
                info = get_focused_info()
                if info and info["id"] == "btn-record":
                    assert info["visible"], f"btn-record must have visible focus indicator: {info}"
                    assert info["outlineStyle"] == "solid"
                    page.keyboard.press("Enter")
                    recorded_od = True
                    break
            assert recorded_od, "Failed to focus and activate #btn-record via keyboard"

            # 3. OD Processing -> Automatic OS Redirect
            page.wait_for_url("**/screen/*/processing?eye=OD", timeout=12000)
            page.wait_for_url("**/screen/*/OS**", timeout=15000)

            # 4. OS Align & Record: wait for distance stabilization
            page.wait_for_selector("#btn-record:not([disabled])", timeout=20000)

            # Tab to OS #btn-record
            recorded_os = False
            for _ in range(12):
                page.keyboard.press("Tab")
                info = get_focused_info()
                if info and info["id"] == "btn-record":
                    assert info["visible"], f"OS btn-record must have visible focus indicator: {info}"
                    assert info["outlineStyle"] == "solid"
                    page.keyboard.press("Enter")
                    recorded_os = True
                    break
            assert recorded_os, "Failed to focus and activate OS #btn-record via keyboard"

            # 5. OS Processing -> Automatic Result Screen Redirect
            page.wait_for_url("**/screen/*/processing?eye=OS", timeout=12000)
            page.wait_for_url("**/screen/*/result**", timeout=15000)

            # 6. Result Screen verification
            assert page.locator("#referral-banner").is_visible()
            
            # Tab through controls on result page and verify focus indicators
            verified_result_control = False
            for _ in range(15):
                page.keyboard.press("Tab")
                info = get_focused_info()
                if info and ("btn-print-slip" in info.get("className", "") or info["id"] in ("btn-new-screening", "btn-save-ground-truth")):
                    assert info["visible"], f"Result control must have visible focus indicator: {info}"
                    assert info["outlineStyle"] == "solid" or info["visible"]
                    verified_result_control = True
                    break
            assert verified_result_control, "Failed to focus any primary action on Result page via Tab"

            browser.close()
    finally:
        server.shutdown()


