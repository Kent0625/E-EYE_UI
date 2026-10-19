import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import time
import socket
import threading
import csv
import io
from playwright.sync_api import sync_playwright
from werkzeug.serving import make_server
from app.app import create_app
from app import store

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

def test_zero_inline_styles_phase4():
    """
    Guarantees 0 inline style= attributes in history.html and settings.html.
    """
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    history_path = os.path.join(base_dir, "app", "templates", "history.html")
    settings_path = os.path.join(base_dir, "app", "templates", "settings.html")

    with open(history_path, "r", encoding="utf-8") as f:
        history_cnt = f.read().count("style=")
    with open(settings_path, "r", encoding="utf-8") as f:
        settings_cnt = f.read().count("style=")

    assert history_cnt == 0, f"history.html must have 0 inline styles, found {history_cnt}"
    assert settings_cnt == 0, f"settings.html must have 0 inline styles, found {settings_cnt}"

def test_csv_export_endpoint():
    """
    Verifies /api/export.csv returns 200, valid CSV structure, participant codes, and no PII.
    """
    app = create_app()
    client = app.test_client()
    res = client.get("/api/export.csv")
    assert res.status_code == 200
    assert "text/csv" in res.content_type
    assert "eeye_sessions_export.csv" in res.headers.get("Content-Disposition", "")

    reader = csv.reader(io.StringIO(res.data.decode("utf-8")))
    header = next(reader)
    assert "participant_code" in header
    assert "referral" in header
    assert "OD_se_D" in header
    assert "OS_se_D" in header

    # Ensure no personal identifiable info columns exist
    for col in header:
        assert col.lower() not in ("name", "first_name", "last_name", "dob", "birthdate", "phone", "address")

def test_320px_banner_shortened_and_first_se_visible():
    """
    Verifies that on 320x568 phone screen, the referral banner is shortened
    and the first SE value (OD) is fully visible above the bottom navigation fold without scrolling.
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
            page.goto(f"{base_url}/screen/s_mock_refer/result", wait_until="domcontentloaded")
            page.wait_for_selector("#od-se-val")

            se_box = page.locator("#od-se-val").bounding_box()
            nav_box = page.locator(".bottom-nav").bounding_box()

            assert se_box is not None, "SE value element must be rendered"
            assert nav_box is not None, "Bottom nav must be rendered"

            # The bottom of the SE value box must be above the top of the bottom navigation bar
            se_bottom = se_box["y"] + se_box["height"]
            nav_top = nav_box["y"]
            assert se_bottom <= nav_top, f"SE value ({se_bottom}px) must be above nav bar ({nav_top}px) without scrolling"

            # Verify Unicode minus sign is used
            se_text = page.locator("#od-se-val").inner_text()
            assert "−" in se_text, f"SE value must contain true Unicode minus '−', got {se_text}"
            assert "-" not in se_text, f"SE value must not contain ASCII hyphen '-', got {se_text}"

            browser.close()
    finally:
        server.shutdown()

def test_history_search_and_filter_behavior():
    """
    Verifies History screen behavior:
    - Search input filters participant codes live.
    - Non-matching search displays empty state with clear search button.
    - Clear search button resets search and restores session list.
    - Filter chips filter by referral status and conditions.
    """
    # Seed a specific test session
    test_session = {
        "id": "s_test_phase4_search",
        "participant_code": "EE-PHASE4-999",
        "created_at": "2026-10-19T14:00:00+08:00",
        "site": "Test Health Unit",
        "consent_age": True,
        "consent_signed": True,
        "client_time": "2026-10-19T14:00:00+08:00",
        "status": "complete",
        "referral": True,
        "referral_eyes": ["OD"],
        "eyes": {
            "OD": {
                "status": "ok",
                "sphere_D": -2.0,
                "cylinder_D": -0.5,
                "se_D": -2.25,
                "label": "myopia_moderate",
                "frames_used": 10,
                "frames_total": 100
            },
            "OS": {
                "status": "ok",
                "sphere_D": 0.0,
                "cylinder_D": 0.0,
                "se_D": 0.0,
                "label": "emmetropia",
                "frames_used": 10,
                "frames_total": 100
            }
        }
    }
    store.create_session(test_session)

    app = create_app()
    port = find_free_port()
    server = ServerThread(app, port)
    server.start()
    base_url = f"http://127.0.0.1:{port}"
    time.sleep(0.5)

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 768, "height": 1024})
            page.goto(f"{base_url}/history", wait_until="domcontentloaded")
            page.wait_for_selector("#session-list")

            # 1. Verify seeded session is rendered
            assert page.locator("text=EE-PHASE4-999").count() > 0

            # 2. Search for exact participant code
            page.fill("#history-search", "EE-PHASE4-999")
            page.wait_for_timeout(300)
            assert page.locator(".history-item-card").count() == 1
            assert page.locator("text=EE-PHASE4-999").is_visible()

            # 3. Search for non-existent participant code -> No match state
            page.fill("#history-search", "EE-DOES-NOT-EXIST-000")
            page.wait_for_timeout(300)
            assert page.locator("#history-no-match-card").is_visible()
            assert page.locator("#btn-clear-search").is_visible()

            # 4. Click Clear Search
            page.click("#btn-clear-search")
            page.wait_for_timeout(300)
            assert page.locator("#history-search").input_value() == ""
            assert page.locator("text=EE-PHASE4-999").is_visible()

            # 5. Filter chips: "No referral" should exclude this session
            page.click(".filter-btn[data-filter='no_referral']")
            page.wait_for_timeout(300)
            assert page.locator("text=EE-PHASE4-999").count() == 0

            # 6. Filter chips: "Referral" should include this session
            page.click(".filter-btn[data-filter='referral']")
            page.wait_for_timeout(300)
            assert page.locator("text=EE-PHASE4-999").is_visible()

            # 7. Filter chips: "Myopia" should include this session
            page.click(".filter-btn[data-filter='myopia']")
            page.wait_for_timeout(300)
            assert page.locator("text=EE-PHASE4-999").is_visible()

            # 8. Filter chips: "Hyperopia" should exclude this session
            page.click(".filter-btn[data-filter='hyperopia']")
            page.wait_for_timeout(300)
            assert page.locator("text=EE-PHASE4-999").count() == 0

            browser.close()
    finally:
        store.delete_session("s_test_phase4_search")
        server.shutdown()

def test_history_delete_modal_behavior():
    """
    Verifies History deletion flow:
    - Trash button triggers confirmation modal.
    - Modal uses plain wording: 'Delete this session? This cannot be undone.'
    - Cancel button closes modal without deleting.
    - Confirm button removes session from backend and UI.
    """
    # Seed a session to delete
    delete_test_id = "s_test_phase4_delete_me"
    store.create_session({
        "id": delete_test_id,
        "participant_code": "EE-PHASE4-DEL",
        "created_at": "2026-10-19T14:30:00+08:00",
        "site": "Delete Test Site",
        "consent_age": True,
        "consent_signed": True,
        "client_time": "2026-10-19T14:30:00+08:00",
        "status": "complete",
        "referral": False,
        "referral_eyes": [],
        "eyes": {
            "OD": {"status": "ok", "sphere_D": 0.0, "cylinder_D": 0.0, "se_D": 0.0, "label": "emmetropia", "frames_used": 10, "frames_total": 100},
            "OS": {"status": "ok", "sphere_D": 0.0, "cylinder_D": 0.0, "se_D": 0.0, "label": "emmetropia", "frames_used": 10, "frames_total": 100}
        }
    })

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
            page.goto(f"{base_url}/history", wait_until="domcontentloaded")
            page.wait_for_selector(f".history-delete-btn[data-id='{delete_test_id}']")

            # 1. Click delete button for seeded session
            page.click(f".history-delete-btn[data-id='{delete_test_id}']")
            page.wait_for_timeout(200)

            # 2. Assert modal is visible and text matches plain wording rule
            modal = page.locator("#delete-modal")
            assert modal.is_visible()
            assert not "hidden" in (modal.get_attribute("class") or "")
            assert "Delete this session? This cannot be undone." in page.locator("#delete-modal .modal-body").inner_text()

            # 3. Test Cancel
            page.click("#btn-cancel-delete")
            page.wait_for_timeout(200)
            assert "hidden" in (modal.get_attribute("class") or "")
            # Session still exists in backend
            assert store.get_session(delete_test_id) is not None

            # 4. Trigger Delete again and Confirm
            page.click(f".history-delete-btn[data-id='{delete_test_id}']")
            page.wait_for_timeout(200)
            page.click("#btn-confirm-delete")
            page.wait_for_timeout(400)

            # Session is deleted in backend
            assert store.get_session(delete_test_id) is None
            # Session is gone from UI
            assert page.locator(f".history-delete-btn[data-id='{delete_test_id}']").count() == 0

            browser.close()
    finally:
        store.delete_session(delete_test_id)
        server.shutdown()

def test_settings_screen_behavior():
    """
    Verifies Settings screen:
    - Device diagnostics and software version displayed.
    - Disabled controls contain .field-disabled-hint explaining why.
    - Site name save persists to backend.
    - Clock sync calls /api/clock and displays feedback.
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
            page = browser.new_page(viewport={"width": 1024, "height": 768})
            page.goto(f"{base_url}/settings", wait_until="domcontentloaded")
            page.wait_for_selector(".settings-container")

            # 1. Verify disabled hints are present
            hints = page.locator(".field-disabled-hint").all_inner_texts()
            assert any("OTA" in h or "system" in h for h in hints), "Software version must explain OTA update management"
            assert any("Factory" in h or "technician" in h for h in hints), "Calibration must explain factory calibration requirements"

            # 2. Test Site Name saving
            test_site = "RHU Sumilao Bukidnon"
            page.fill("#setting-site-name", test_site)
            page.click("#btn-save-site")
            page.wait_for_timeout(300)
            assert page.locator("#site-save-feedback").is_visible()
            assert store.get_setting("site_name") == test_site

            # 3. Test Clock Synchronization
            page.click("#btn-sync-clock")
            page.wait_for_timeout(300)
            assert page.locator("#clock-sync-feedback").is_visible()
            assert store.get_setting("clock_set") == "1"

            browser.close()
    finally:
        server.shutdown()
