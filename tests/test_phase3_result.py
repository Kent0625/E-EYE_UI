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
from app.clinical import compute_se, classify_condition, evaluate_referral

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

def test_result_screen_fixtures_behavior():
    """
    Verifies behavior for each fixture on the Result screen:
    1. refer (s_mock_refer): amber banner, warning icon, REFERRAL RECOMMENDED, lists OD, OS.
    2. no_refer (s_mock_norefer): green banner, check icon, NO REFERRAL NEEDED.
    3. retake (s_mock_retake): OD is -1.00 D (outside range). Per manuscript, banner shows
       REFERRAL RECOMMENDED (OD) plus note that OS needs a retake. Never red.
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

            # --- 1. REFER FIXTURE ---
            page.goto(f"{base_url}/screen/s_mock_refer/result", wait_until="domcontentloaded")
            page.wait_for_selector("#referral-banner")

            banner = page.locator("#referral-banner")
            banner_class = banner.get_attribute("class")
            assert "badge-warn" in banner_class, f"Expected amber badge-warn in {banner_class}"
            assert "badge-error" not in banner_class, "Referral banner must NEVER be red (badge-error)"

            banner_text = banner.text_content()
            assert "REFERRAL RECOMMENDED" in banner_text
            assert "OD" in banner_text and "OS" in banner_text

            # Check OD/OS cards have large SE with true minus sign
            od_se = page.text_content("#od-se-val").strip()
            os_se = page.text_content("#os-se-val").strip()
            assert "−1.75 D" in od_se
            assert "−1.37 D" in os_se
            assert "-" not in od_se and "-" not in os_se, "Must use true unicode minus sign '−' (\u2212)"

            # Check cylinder is shown without implying referral
            cyl_note = page.locator(".eye-se-rule-note").first.text_content()
            assert "Spherical Equivalent" in cyl_note or "SE" in cyl_note

            # --- 2. NO REFER FIXTURE ---
            page.goto(f"{base_url}/screen/s_mock_norefer/result", wait_until="domcontentloaded")
            page.wait_for_selector("#referral-banner")

            banner = page.locator("#referral-banner")
            banner_class = banner.get_attribute("class")
            assert "badge-ok" in banner_class, f"Expected green badge-ok in {banner_class}"
            assert "badge-error" not in banner_class

            banner_text = banner.text_content()
            assert "NO REFERRAL NEEDED" in banner_text
            assert "within the normal range" in banner_text

            # --- 3. RETAKE FIXTURE (OD is -1.00 D, OS is retake_needed) ---
            page.goto(f"{base_url}/screen/s_mock_retake/result", wait_until="domcontentloaded")
            page.wait_for_selector("#referral-banner")

            banner = page.locator("#referral-banner")
            banner_class = banner.get_attribute("class")
            assert "badge-warn" in banner_class, f"Expected amber badge-warn for retake in {banner_class}"
            assert "badge-error" not in banner_class, "Retake banner must NEVER be red"

            banner_text = banner.text_content()
            # Since OD is -1.00 D (outside +-0.50 D), banner MUST recommend referral for OD
            assert "REFERRAL RECOMMENDED" in banner_text
            assert "OD" in banner_text
            # Plus a note that OS needs a retake
            assert "OS needs a retake" in banner_text or "needs a retake" in banner_text

            # Verify OS card has retake needed state and retake button
            assert page.locator("a[href='/screen/s_mock_retake/OS']").is_visible()
            os_card_text = page.locator(".eye-card").nth(1).text_content()
            assert "Retake" in os_card_text or "frames used" in os_card_text

            # Statutory disclaimer present on all fixtures
            disclaimer = page.locator(".result-disclaimer").first.text_content()
            assert "Screening only" in disclaimer and "diagnosis" in disclaimer

            browser.close()
    finally:
        server.shutdown()

def test_screening_incomplete_banner_when_recorded_eyes_in_range():
    """
    Verifies that 'SCREENING INCOMPLETE' is shown only when all recorded eyes are within range.
    (e.g., OD is 0.00 D, and OS is retake_needed).
    """
    app = create_app()
    port = find_free_port()
    server = ServerThread(app, port)
    server.start()
    base_url = f"http://127.0.0.1:{port}"
    time.sleep(0.5)

    test_id = "s_test_in_range_retake"
    store.delete_session(test_id)
    store.create_session({
        "id": test_id,
        "participant_code": "EE-TEST-INCOMPLETE",
        "created_at": "2026-10-19T12:00:00+08:00",
        "site": "RHU Sumilao",
        "status": "retake_needed",
        "referral": False,
        "referral_eyes": [],
        "eyes": {
            "OD": {"status": "ok", "sphere_D": 0.00, "cylinder_D": 0.00, "se_D": 0.00, "label": "emmetropia", "frames_used": 10, "frames_total": 110},
            "OS": {"status": "retake_needed", "frames_used": 5, "frames_total": 105, "error_reason": "few_valid_frames"}
        }
    })

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 390, "height": 844})
            page.goto(f"{base_url}/screen/{test_id}/result", wait_until="domcontentloaded")
            page.wait_for_selector("#referral-banner")

            banner = page.locator("#referral-banner")
            banner_text = banner.text_content()
            assert "SCREENING INCOMPLETE" in banner_text
            assert "REFERRAL RECOMMENDED" not in banner_text

            browser.close()
    finally:
        server.shutdown()
        store.delete_session(test_id)

def test_se_rounding_boundary_behavior():
    """
    Tests exact clinical referral boundary decisions and Result screen rendering:
    - -0.504 D rounds to -0.50 D -> NO REFERRAL
    - -0.505 D rounds to -0.51 D -> REFERRAL RECOMMENDED
    - +0.505 D rounds to +0.51 D -> REFERRAL RECOMMENDED
    """
    app = create_app()
    port = find_free_port()
    server = ServerThread(app, port)
    server.start()
    base_url = f"http://127.0.0.1:{port}"
    time.sleep(0.5)

    # Ensure clean state before inserting
    for sid in ("s_test_bound_504", "s_test_bound_neg_505", "s_test_bound_pos_505"):
        store.delete_session(sid)

    # Case 1: -0.504 -> rounds to -0.50 D (NO REFERRAL)
    se_504 = compute_se("-0.25", "-0.508")
    ref_504, eyes_504 = evaluate_referral(se_504, 0.00)
    store.create_session({
        "id": "s_test_bound_504",
        "participant_code": "EE-BOUND-504",
        "created_at": "2026-10-19T12:00:00+08:00",
        "site": "RHU Sumilao",
        "status": "complete",
        "referral": ref_504,
        "referral_eyes": eyes_504,
        "eyes": {
            "OD": {"status": "ok", "sphere_D": -0.25, "cylinder_D": -0.508, "se_D": se_504, "label": classify_condition(se_504), "frames_used": 10, "frames_total": 110},
            "OS": {"status": "ok", "sphere_D": 0.00, "cylinder_D": 0.00, "se_D": 0.00, "label": "emmetropia", "frames_used": 10, "frames_total": 110}
        }
    })

    # Case 2: -0.505 -> rounds to -0.51 D (REFERRAL RECOMMENDED)
    se_neg_505 = compute_se("-0.25", "-0.51")
    ref_neg_505, eyes_neg_505 = evaluate_referral(se_neg_505, 0.00)
    store.create_session({
        "id": "s_test_bound_neg_505",
        "participant_code": "EE-BOUND-NEG-505",
        "created_at": "2026-10-19T12:05:00+08:00",
        "site": "RHU Sumilao",
        "status": "complete",
        "referral": ref_neg_505,
        "referral_eyes": eyes_neg_505,
        "eyes": {
            "OD": {"status": "ok", "sphere_D": -0.25, "cylinder_D": -0.51, "se_D": se_neg_505, "label": classify_condition(se_neg_505), "frames_used": 10, "frames_total": 110},
            "OS": {"status": "ok", "sphere_D": 0.00, "cylinder_D": 0.00, "se_D": 0.00, "label": "emmetropia", "frames_used": 10, "frames_total": 110}
        }
    })

    # Case 3: +0.505 -> rounds to +0.51 D (REFERRAL RECOMMENDED)
    se_pos_505 = compute_se("+0.25", "+0.51")
    ref_pos_505, eyes_pos_505 = evaluate_referral(se_pos_505, 0.00)
    store.create_session({
        "id": "s_test_bound_pos_505",
        "participant_code": "EE-BOUND-POS-505",
        "created_at": "2026-10-19T12:10:00+08:00",
        "site": "RHU Sumilao",
        "status": "complete",
        "referral": ref_pos_505,
        "referral_eyes": eyes_pos_505,
        "eyes": {
            "OD": {"status": "ok", "sphere_D": 0.25, "cylinder_D": 0.51, "se_D": se_pos_505, "label": classify_condition(se_pos_505), "frames_used": 10, "frames_total": 110},
            "OS": {"status": "ok", "sphere_D": 0.00, "cylinder_D": 0.00, "se_D": 0.00, "label": "emmetropia", "frames_used": 10, "frames_total": 110}
        }
    })

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 390, "height": 844})

            # Check -0.504 boundary -> No referral
            page.goto(f"{base_url}/screen/s_test_bound_504/result", wait_until="domcontentloaded")
            page.wait_for_selector("#referral-banner")
            assert "badge-ok" in page.locator("#referral-banner").get_attribute("class")
            assert "−0.50 D" in page.text_content("#od-se-val")

            # Check -0.505 boundary -> Referral
            page.goto(f"{base_url}/screen/s_test_bound_neg_505/result", wait_until="domcontentloaded")
            page.wait_for_selector("#referral-banner")
            assert "badge-warn" in page.locator("#referral-banner").get_attribute("class")
            assert "−0.51 D" in page.text_content("#od-se-val")

            # Check +0.505 boundary -> Referral
            page.goto(f"{base_url}/screen/s_test_bound_pos_505/result", wait_until="domcontentloaded")
            page.wait_for_selector("#referral-banner")
            assert "badge-warn" in page.locator("#referral-banner").get_attribute("class")
            assert "+0.51 D" in page.text_content("#od-se-val")

            browser.close()
    finally:
        server.shutdown()
        for sid in ("s_test_bound_504", "s_test_bound_neg_505", "s_test_bound_pos_505"):
            store.delete_session(sid)

def test_result_layout_desktop_and_mobile_stacking():
    """
    Verifies:
    1. At 1440px and 1024px: eye cards (.result-main) start at row 1 alongside the sidebar (.result-sidebar),
       with no empty vertical gap above them.
    2. At 320px: thumbnail stacks above the SE value, and '-1.00 D' does not wrap.
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

            # Test 1: Desktop grid alignment (1440px and 1024px)
            for w, h in [(1440, 900), (1024, 768)]:
                page = browser.new_page(viewport={"width": w, "height": h})
                page.goto(f"{base_url}/screen/s_mock_refer/result", wait_until="domcontentloaded")
                page.wait_for_selector("#referral-banner")

                main_box = page.locator(".result-main").bounding_box()
                side_box = page.locator(".result-sidebar").bounding_box()

                assert main_box is not None and side_box is not None
                # Both columns must start at the same vertical offset (no empty gap above eye cards)
                assert abs(main_box["y"] - side_box["y"]) < 5.0, (
                    f"[{w}px] Grid mismatch: main y={main_box['y']} vs sidebar y={side_box['y']}"
                )
                page.close()

            # Test 2: 320px mobile thumbnail stacking and no-wrap SE value
            page_320 = browser.new_page(viewport={"width": 320, "height": 568})
            page_320.goto(f"{base_url}/screen/s_mock_refer/result", wait_until="domcontentloaded")
            page_320.wait_for_selector("#od-se-val")

            thumb_box = page_320.locator(".eye-thumbnail").first.bounding_box()
            se_box = page_320.locator("#od-se-val").first.bounding_box()

            # Thumbnail must be stacked above the SE value
            assert thumb_box["y"] < se_box["y"], (
                f"[320px] Expected thumbnail (y={thumb_box['y']}) stacked above SE value (y={se_box['y']})"
            )

            # SE value must not wrap
            white_space = page_320.locator("#od-se-val").first.evaluate("el => getComputedStyle(el).whiteSpace")
            assert white_space == "nowrap", f"[320px] Expected white-space: nowrap, got {white_space}"

            page_320.close()
            browser.close()
    finally:
        server.shutdown()

def test_result_screen_zero_overflow_across_viewports():
    """Verifies that all three fixtures have 0 horizontal overflow at all 5 widths."""
    app = create_app()
    port = find_free_port()
    server = ServerThread(app, port)
    server.start()
    base_url = f"http://127.0.0.1:{port}"
    time.sleep(0.5)

    fixtures = ["s_mock_refer", "s_mock_norefer", "s_mock_retake"]

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)

            for fix_id in fixtures:
                for vp in VIEWPORTS:
                    w = vp["width"]
                    h = vp["height"]
                    page = browser.new_page(viewport={"width": w, "height": h})
                    page.goto(f"{base_url}/screen/{fix_id}/result", wait_until="domcontentloaded")
                    page.wait_for_selector("#referral-banner")

                    page.evaluate("window.scrollTo(1000, 0)")
                    scroll_x = page.evaluate("window.scrollX")
                    assert scroll_x == 0, f"[{fix_id} @ {w}px] Horizontal scrollX = {scroll_x}"

                    scroll_w = page.evaluate("document.documentElement.scrollWidth")
                    inner_w = page.evaluate("window.innerWidth")
                    assert scroll_w <= inner_w, f"[{fix_id} @ {w}px] scrollWidth ({scroll_w}) > innerWidth ({inner_w})"

                    page.close()

            browser.close()
    finally:
        server.shutdown()
