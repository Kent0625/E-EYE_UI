import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import time
import socket
import threading
import csv
import io
import json
import glob
import re
from playwright.sync_api import sync_playwright
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

def test_zero_inline_styles_mandated_templates():
    """
    Guarantees 0 inline style= attributes across home, new, processing,
    record, and session_not_found (target: 0).
    Also asserts 0 inline styles across all templates in app/templates.
    """
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    templates_dir = os.path.join(base_dir, "app", "templates")
    mandated = ["home.html", "new.html", "processing.html", "record.html", "session_not_found.html"]

    for name in mandated:
        path = os.path.join(templates_dir, name)
        with open(path, "r", encoding="utf-8") as f:
            cnt = len(re.findall(r'\bstyle=', f.read()))
        assert cnt == 0, f"{name} must have 0 inline styles, found {cnt}"

    for path in glob.glob(os.path.join(templates_dir, "*.html")):
        with open(path, "r", encoding="utf-8") as f:
            cnt = len(re.findall(r'\bstyle=', f.read()))
        assert cnt == 0, f"{os.path.basename(path)} must have 0 inline styles, found {cnt}"

def test_csv_export_numeric_and_formula_escaping():
    """
    Verifies that sanitize_csv_cell is applied ONLY to free-text columns:
    - Code of =1+1 is exported with apostrophe ('=1+1).
    - Numeric values (e.g., -1.75 SE) export as raw numbers (-1.75) with no apostrophe.
    """
    test_id = "s_test_csv_numeric_bug"
    store.create_session({
        "id": test_id,
        "participant_code": "=1+1",
        "created_at": "2026-10-20T14:00:00+08:00",
        "site": "@BarangayHall",
        "consent_age": True,
        "consent_signed": True,
        "client_time": "2026-10-20T14:00:00+08:00",
        "status": "complete",
        "referral": True,
        "referral_eyes": ["OD"],
        "eyes": {
            "OD": {
                "status": "ok",
                "sphere_D": -1.50,
                "cylinder_D": -0.50,
                "se_D": -1.75,
                "label": "myopia_mild",
                "frames_used": 10,
                "frames_total": 100
            },
            "OS": {
                "status": "ok",
                "sphere_D": 0.50,
                "cylinder_D": 0.00,
                "se_D": 0.50,
                "label": "emmetropia",
                "frames_used": 10,
                "frames_total": 100
            }
        }
    })

    try:
        app = create_app()
        client = app.test_client()
        res = client.get("/api/export.csv")
        assert res.status_code == 200

        csv_text = res.data.decode("utf-8")
        reader = csv.reader(io.StringIO(csv_text))
        header = next(reader)
        code_idx = header.index("participant_code")
        od_se_idx = header.index("OD_se_D")
        od_sph_idx = header.index("OD_sphere_D")
        site_idx = header.index("site")

        found = False
        for row in reader:
            if row[0] == test_id:
                found = True
                # Free-text formula injection must be escaped with apostrophe
                assert row[code_idx] == "'=1+1", f"Code =1+1 must be escaped, got {row[code_idx]}"
                assert row[site_idx] == "'@BarangayHall", f"Site @BarangayHall must be escaped, got {row[site_idx]}"
                # Numeric diopter values must NOT have an apostrophe
                assert row[od_se_idx] == "-1.75", f"SE −1.75 must export as raw -1.75 with no apostrophe, got {row[od_se_idx]}"
                assert not row[od_se_idx].startswith("'"), f"SE must not start with apostrophe: {row[od_se_idx]}"
                assert row[od_sph_idx] in ("-1.5", "-1.50"), f"Sphere must export as raw number: {row[od_sph_idx]}"
                break
        assert found, "Test session was not found in exported CSV"
    finally:
        store.delete_session(test_id)

def test_home_storage_server_rendered_and_no_hardcoded_18_4():
    """
    Verifies that home.html uses server-rendered storage free value,
    not a hardcoded 18.4 string.
    """
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    home_tmpl = os.path.join(base_dir, "app", "templates", "home.html")
    with open(home_tmpl, "r", encoding="utf-8") as f:
        content = f.read()
    assert "18.4" not in content, "home.html must not contain hardcoded 18.4"
    assert "val-storage" in content
    assert "storage_free_gb" in content

def test_unused_ota_and_technician_strings_deleted():
    """
    Verifies that settings.disabledCalHint and settings.disabledVersionHint
    have been deleted from en.json and fil.json, and key parity remains 100%.
    """
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    en_path = os.path.join(base_dir, "app", "static", "i18n", "en.json")
    fil_path = os.path.join(base_dir, "app", "static", "i18n", "fil.json")

    with open(en_path, "r", encoding="utf-8") as f:
        en = json.load(f)
    with open(fil_path, "r", encoding="utf-8") as f:
        fil = json.load(f)

    assert "settings.disabledCalHint" not in en
    assert "settings.disabledVersionHint" not in en
    assert "settings.disabledCalHint" not in fil
    assert "settings.disabledVersionHint" not in fil
    assert set(en.keys()) == set(fil.keys())

def test_compute_se_on_ground_truth_api():
    """
    Verifies that /api/sessions/<id>/ground-truth computes ground-truth SE
    strictly using compute_se.
    """
    test_id = "s_test_gt_compute_se"
    orig_mode = store.get_setting("research_mode", "0")
    store.set_setting("research_mode", "1")
    store.create_session({
        "id": test_id,
        "participant_code": "EE-GT-001",
        "created_at": "2026-10-20T14:30:00+08:00",
        "site": "Test Site",
        "consent_age": True,
        "consent_signed": True,
        "client_time": "2026-10-20T14:30:00+08:00",
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

        # Submit OD ground truth: sphere -1.25, cylinder -0.50 -> expected SE -1.50
        res = client.post(f"/api/sessions/{test_id}/ground-truth", json={
            "eye": "OD",
            "sphere_D": -1.25,
            "cylinder_D": -0.50
        })
        assert res.status_code == 200
        data = res.get_json()
        od_gt = data["eyes"]["OD"]["ground_truth"]
        assert od_gt["sphere_D"] == -1.25
        assert od_gt["cylinder_D"] == -0.50
        assert od_gt["se_D"] == compute_se(-1.25, -0.50)
        assert od_gt["se_D"] == -1.50

        # Submit OS ground truth via dictionary payload: sphere +0.25, cylinder -0.50 -> expected SE 0.00
        res2 = client.post(f"/api/sessions/{test_id}/ground-truth", json={
            "OS": {
                "sphere_D": 0.25,
                "cylinder_D": -0.50
            }
        })
        assert res2.status_code == 200
        data2 = res2.get_json()
        os_gt = data2["eyes"]["OS"]["ground_truth"]
        assert os_gt["se_D"] == compute_se(0.25, -0.50)
        assert os_gt["se_D"] == 0.00
    finally:
        store.set_setting("research_mode", orig_mode)
        store.delete_session(test_id)

def test_research_mode_toggle_and_result_screen_behavior():
    """
    Playwright test driving:
    1. Research mode toggle in Settings (enables/disables).
    2. Result screen shows ground-truth section when enabled.
    3. Ground-truth inputs calculate and save paired autorefractor SE diopters.
    4. Result screen hides ground-truth section when disabled.
    5. Print slip button is present.
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

            # 1. Enable Research Mode in Settings
            page.goto(f"{base_url}/settings", wait_until="domcontentloaded")
            toggle = page.locator("#toggle-research-mode")
            assert toggle.is_visible()
            if not toggle.is_checked():
                toggle.check()
                page.wait_for_timeout(300)
            assert store.get_setting("research_mode") == "1"

            # 2. Visit Result screen with research mode enabled -> ground truth section visible
            page.goto(f"{base_url}/screen/s_mock_refer/result", wait_until="domcontentloaded")
            gt_section = page.locator("#ground-truth-section")
            assert gt_section.is_visible(), "Ground truth section must be visible when Research Mode is enabled"

            # 3. Fill and submit ground truth
            page.fill("#gt-od-sphere", "-1.25")
            page.fill("#gt-od-cylinder", "-0.50")
            page.click("#btn-save-ground-truth")
            page.wait_for_timeout(400)

            # Assert feedback shown and computed SE displayed with true minus
            assert page.locator("#gt-save-feedback").is_visible()
            od_text = page.locator("#gt-od-se-display").inner_text()
            assert "−1.50 D" in od_text or "-1.50 D" in od_text
            assert "−" in od_text, f"Displayed ground truth SE must contain Unicode minus '−', got {od_text}"

            # 4. Print slip button exists
            assert page.locator(".btn-print-slip").first.is_visible()

            # 5. Disable Research Mode in Settings
            page.goto(f"{base_url}/settings", wait_until="domcontentloaded")
            page.uncheck("#toggle-research-mode")
            page.wait_for_timeout(300)
            assert store.get_setting("research_mode") == "0"

            # 6. Revisit Result screen -> ground truth section is hidden
            page.goto(f"{base_url}/screen/s_mock_refer/result", wait_until="domcontentloaded")
            assert page.locator("#ground-truth-section").count() == 0 or not page.locator("#ground-truth-section").is_visible()

            browser.close()
    finally:
        server.shutdown()
