import os
import json
from flask import Flask, render_template, redirect, url_for, request
from app.config import (
    MOCK_MODE, MEDIA_FOLDER, SOFTWARE_VERSION, DEVICE_NAME,
    DEVICE_SSID, DEVICE_IP, BASE_DIR, get_storage_free_str,
    TOF_CALIBRATED_DATE, LED_DRIVE_SETTING
)
from app import store
from app.api import api_bp
from app.mock.fixtures import seed_fixtures_if_empty
from app.mock.generator import ensure_sample_media

# Load i18n dictionaries at startup for server-side rendering
I18N_DICTS = {}
for lang in ("en", "fil"):
    dict_path = os.path.join(BASE_DIR, "static", "i18n", f"{lang}.json")
    if os.path.exists(dict_path):
        with open(dict_path, "r", encoding="utf-8") as f:
            I18N_DICTS[lang] = json.load(f)

def translate(key, lang="en", **kwargs):
    d = I18N_DICTS.get(lang, I18N_DICTS.get("en", {}))
    text = d.get(key, key)
    for k, v in kwargs.items():
        text = text.replace(f"{{{k}}}", str(v))
    return text

def create_app():
    app = Flask(__name__)
    app.config["MOCK_MODE"] = MOCK_MODE
    app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 0
    
    # Initialize SQLite store
    store.init_db()
    
    # Initialize sample media assets
    ensure_sample_media(MEDIA_FOLDER)
    
    # Seed mock fixtures if in mock mode
    if MOCK_MODE:
        seed_fixtures_if_empty(store)
    
    # Register API and Media Blueprint
    app.register_blueprint(api_bp)
    
    # Context processor to make version, mock status, device metadata and server-rendered strings available
    @app.context_processor
    def inject_app_context():
        lang = request.cookies.get("eeye_lang") or store.get_setting("lang", "en")
        if lang not in ("en", "fil"):
            lang = "en"
        return {
            "mock_mode": MOCK_MODE,
            "software_version": SOFTWARE_VERSION,
            "device_name": DEVICE_NAME,
            "storage_free_gb": get_storage_free_str(),
            "research_mode": store.get_setting("research_mode", "0") == "1",
            "current_lang": lang,
            "t": lambda key, **kw: translate(key, lang=lang, **kw)
        }
    
    from datetime import datetime

    def generate_next_participant_code():
        today = datetime.now().strftime("%y%m%d")
        sessions = store.list_sessions()
        seq = len(sessions) + 1
        return f"EE-{today}-{seq:03d}"

    # UI Page Routes
    @app.route("/")
    def page_home():
        return render_template("home.html", active_nav="home")
    
    @app.route("/screen/new")
    def page_new_screening():
        suggested_code = generate_next_participant_code()
        default_site = store.get_setting("site_name", "")
        return render_template("new.html", active_nav="screen", suggested_code=suggested_code, default_site=default_site)
    
    @app.route("/screen/<id>/<eye>")
    def page_record(id, eye):
        session = store.get_session(id)
        if not session:
            return render_template("session_not_found.html", session_id=id, active_nav="screen"), 404
        return render_template("record.html", active_nav="screen", session=session, eye=eye)
    
    @app.route("/screen/<id>/processing")
    def page_processing(id):
        session = store.get_session(id)
        if not session:
            return render_template("session_not_found.html", session_id=id, active_nav="screen"), 404
        return render_template("processing.html", active_nav="screen", session=session)
    
    @app.route("/screen/<id>/result")
    def page_result(id):
        session = store.get_session(id)
        if not session:
            return render_template("session_not_found.html", session_id=id, active_nav="screen"), 404
        return render_template("result.html", active_nav="screen", session=session)
    
    @app.route("/history")
    def page_history():
        sessions = store.list_sessions()
        return render_template("history.html", active_nav="history", sessions=sessions)
    
    @app.route("/settings")
    def page_settings():
        settings_data = {
            "device_name": DEVICE_NAME,
            "ssid": DEVICE_SSID,
            "ip": DEVICE_IP,
            "storage_free_gb": get_storage_free_str(),
            "software_version": SOFTWARE_VERSION,
            "site_name": store.get_setting("site_name", ""),
            "clock_set": store.get_setting("clock_set", "1") == "1",
            "research_mode": store.get_setting("research_mode", "0") == "1",
            "tof_calibrated_date": TOF_CALIBRATED_DATE or "Not recorded",
            "led_drive_setting": LED_DRIVE_SETTING or "Not set",
            "mock_mode": MOCK_MODE
        }
        return render_template("settings.html", active_nav="settings", settings_data=settings_data)
    
    return app

app = create_app()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
