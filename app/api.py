import io
import csv
import json
import math
import time
from datetime import datetime
from flask import Blueprint, jsonify, request, Response, send_from_directory
from app import store
from app.clinical import compute_se
from app.config import (
    MOCK_MODE, MEDIA_FOLDER, DEVICE_NAME, DEVICE_SSID,
    DEVICE_IP, SOFTWARE_VERSION, get_storage_free_gb,
    get_storage_free_str, TOF_CALIBRATED_DATE, LED_DRIVE_SETTING
)
from app.mock.generator import generate_mock_distance_events, generate_mock_mjpeg_stream

api_bp = Blueprint("api", __name__)

@api_bp.route("/media/<path:filename>")
def serve_media(filename):
    return send_from_directory(MEDIA_FOLDER, filename)

@api_bp.route("/api/status", methods=["GET"])
def get_status():
    simulate_fail = request.args.get("fail")
    clock_set = store.get_setting("clock_set", "1") == "1"
    
    status_data = {
        "camera": "error" if simulate_fail == "camera" else "ok",
        "tof": "error" if simulate_fail == "tof" else "ok",
        "led": "error" if simulate_fail == "led" else "ok",
        "model": "error" if simulate_fail == "model" else "loaded",
        "storage_free_gb": get_storage_free_gb(),
        "clock_set": False if simulate_fail == "clock" else clock_set,
        "version": SOFTWARE_VERSION,
        "device_name": DEVICE_NAME,
        "ssid": DEVICE_SSID,
        "ip": DEVICE_IP,
        "mock_mode": MOCK_MODE
    }
    return jsonify(status_data)

@api_bp.route("/api/distance", methods=["GET"])
def stream_distance():
    return Response(
        generate_mock_distance_events(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no"
        }
    )

@api_bp.route("/api/preview.mjpg", methods=["GET"])
def stream_preview():
    return Response(
        generate_mock_mjpeg_stream(),
        mimetype="multipart/x-mixed-replace; boundary=frame"
    )

@api_bp.route("/api/precheck", methods=["POST"])
def run_precheck():
    # 5-second test capture simulation
    return jsonify({
        "crescent_frame_url": "/media/precheck_crescent.jpg",
        "tof_ok": True,
        "brightness_ok": True,
        "brightness_mean": 154
    })

@api_bp.route("/api/sessions", methods=["POST"])
def create_session():
    data = request.get_json() or {}
    now = datetime.now().strftime("%y%m%d")
    
    # Generate ID and participant code if not provided
    existing = store.list_sessions()
    seq = len(existing) + 1
    session_id = f"s_{int(time.time())}"
    code = data.get("participant_code") or f"EE-{now}-{seq:03d}"
    
    session_obj = {
        "id": session_id,
        "participant_code": code,
        "site": data.get("site", ""),
        "consent_age": bool(data.get("consent_age")),
        "consent_signed": bool(data.get("consent_signed")),
        "client_time": data.get("client_time", datetime.now().isoformat()),
        "status": "created",
        "referral": None,
        "referral_eyes": [],
        "eyes": {
            "OD": {"status": "not_recorded"},
            "OS": {"status": "not_recorded"}
        }
    }
    created = store.create_session(session_obj)
    return jsonify(created), 201

@api_bp.route("/api/sessions/<id>/record", methods=["POST"])
def record_eye(id):
    session = store.get_session(id)
    if not session:
        return jsonify({"error": "Session not found"}), 404
    data = request.get_json() or {}
    eye = data.get("eye", "OD")
    return jsonify({
        "status": "recording_started",
        "session_id": id,
        "eye": eye,
        "duration_s": 5
    })

@api_bp.route("/api/sessions/<id>/record/stream", methods=["GET"])
def stream_recording_countdown(id):
    session = store.get_session(id)
    if not session:
        return jsonify({"error": "Session not found"}), 404

    eye = request.args.get("eye", "OD")
    simulate = request.args.get("simulate", "normal")
    fast_mode = request.args.get("fast", "0") == "1"
    tick_delay = 0.2 if fast_mode else 1.0

    def event_generator():
        yield f"data: {json.dumps({'event': 'recording_started', 'eye': eye, 'seconds_total': 5})}\n\n"
        
        if simulate == "error":
            time.sleep(tick_delay)
            yield f"data: {json.dumps({'event': 'recording_complete', 'success': False, 'reason': 'capture_error', 'message': 'Camera capture failed.'})}\n\n"
            return

        for sec in range(4, 0, -1):
            time.sleep(tick_delay)
            if simulate == "drift" and sec == 2:
                yield f"data: {json.dumps({'event': 'distance_drift', 'cm': 16.8})}\n\n"
                time.sleep(tick_delay / 2.0)
                yield f"data: {json.dumps({'event': 'recording_complete', 'success': False, 'reason': 'distance_drift', 'message': 'Distance changed during recording. Retake.'})}\n\n"
                return
            yield f"data: {json.dumps({'event': 'tick', 'seconds_left': sec})}\n\n"

        time.sleep(tick_delay)
        yield f"data: {json.dumps({'event': 'recording_complete', 'success': True, 'frames_captured': 10})}\n\n"

    return Response(
        event_generator(),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
    )

@api_bp.route("/api/sessions/<id>/events", methods=["GET"])
def stream_processing_events(id):
    def event_generator():
        steps = [
            ("extracting", "Extracting frames..."),
            ("quality_check", "Checking frame quality..."),
            ("feature_calc", "Computing pupil crescent features..."),
            ("inference", "Estimating refraction..."),
            ("done", "Complete")
        ]
        for step_code, label in steps:
            time.sleep(0.7)
            payload = json.dumps({"step": step_code, "label": label, "done": step_code == "done"})
            yield f"data: {payload}\n\n"
    
    return Response(
        event_generator(),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
    )

@api_bp.route("/api/sessions/<id>", methods=["GET"])
def get_session_detail(id):
    session = store.get_session(id)
    if not session:
        return jsonify({"error": "Session not found"}), 404
    return jsonify(session)

@api_bp.route("/api/sessions", methods=["GET"])
def list_sessions_endpoint():
    q = request.args.get("q", "")
    filter_type = request.args.get("filter", "all")
    sessions = store.list_sessions(q=q, filter_type=filter_type)
    return jsonify(sessions)

@api_bp.route("/api/sessions/<id>", methods=["DELETE"])
def delete_session_endpoint(id):
    ok = store.delete_session(id)
    if not ok:
        return jsonify({"error": "Session not found"}), 404
    return jsonify({"success": True, "id": id})

def parse_diopter(val):
    """
    Parses and validates diopter input:
    - Rejects blank/None values
    - Rejects non-numeric text
    - Rejects NaN/Infinity
    - Validates physiological autorefractor measurement range [-20.0, +20.0] D
    """
    if val is None or val == "":
        raise ValueError("Diopter value cannot be blank")
    try:
        num = float(val)
    except (ValueError, TypeError):
        raise ValueError("Diopter value must be numeric")
    if math.isnan(num) or math.isinf(num):
        raise ValueError("Diopter value cannot be NaN or Inf")
    if num < -20.0 or num > 20.0:
        raise ValueError("Diopter value out of range [-20.0, +20.0] D")
    return num

@api_bp.route("/api/sessions/<id>/ground-truth", methods=["POST"])
def update_ground_truth(id):
    if store.get_setting("research_mode", "0") != "1":
        return jsonify({"error": "Research mode is disabled"}), 403

    session = store.get_session(id)
    if not session:
        return jsonify({"error": "Session not found"}), 404
    data = request.get_json() or {}
    
    eyes = session.get("eyes", {})
    
    if "eye" in data:
        eye = data.get("eye")  # "OD" or "OS"
        if eye not in ("OD", "OS"):
            return jsonify({"error": "Invalid eye"}), 400
        try:
            sph = parse_diopter(data.get("sphere_D"))
            cyl = parse_diopter(data.get("cylinder_D"))
        except ValueError as e:
            return jsonify({"error": str(e)}), 400

        eye_data = eyes.get(eye, {})
        eye_data["ground_truth"] = {
            "sphere_D": sph,
            "cylinder_D": cyl,
            "se_D": compute_se(sph, cyl)
        }
        eyes[eye] = eye_data
    else:
        has_entry = False
        for eye_key in ("OD", "OS"):
            if eye_key in data:
                has_entry = True
                e_data = data[eye_key]
                if not isinstance(e_data, dict):
                    return jsonify({"error": f"{eye_key} payload must be an object"}), 400
                try:
                    sph = parse_diopter(e_data.get("sphere_D"))
                    cyl = parse_diopter(e_data.get("cylinder_D"))
                except ValueError as e:
                    return jsonify({"error": str(e)}), 400

                eye_data = eyes.get(eye_key, {})
                eye_data["ground_truth"] = {
                    "sphere_D": sph,
                    "cylinder_D": cyl,
                    "se_D": compute_se(sph, cyl)
                }
                eyes[eye_key] = eye_data
        
        if not has_entry:
            return jsonify({"error": "No valid ground truth data provided"}), 400

    updated = store.update_session(id, eyes=eyes)
    return jsonify(updated)

def sanitize_csv_cell(val):
    """
    Prevents spreadsheet formula injection in CSV exports for free-text cells
    by prefixing strings starting with '=', '+', '-', '@', '\t', or '\r' with a single quote.
    Only applied to free-text columns (session_id, participant_code, site).
    """
    if val is None:
        return ""
    s = str(val)
    if s and s[0] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + s
    return s

@api_bp.route("/api/export.csv", methods=["GET"])
def export_csv():
    sessions = store.list_sessions()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "session_id", "participant_code", "created_at", "site",
        "referral", "referral_eyes",
        "OD_status", "OD_sphere_D", "OD_cylinder_D", "OD_se_D", "OD_label", "OD_frames",
        "OS_status", "OS_sphere_D", "OS_cylinder_D", "OS_se_D", "OS_label", "OS_frames",
        "OD_gt_sphere_D", "OD_gt_cylinder_D", "OD_gt_se_D",
        "OS_gt_sphere_D", "OS_gt_cylinder_D", "OS_gt_se_D"
    ])
    for s in sessions:
        eyes = s.get("eyes", {})
        od = eyes.get("OD", {})
        os_eye = eyes.get("OS", {})
        od_gt = od.get("ground_truth") or {}
        os_gt = os_eye.get("ground_truth") or {}
        
        row = [
            sanitize_csv_cell(s.get("id", "")),
            sanitize_csv_cell(s.get("participant_code", "")),
            s.get("created_at", ""),
            sanitize_csv_cell(s.get("site", "")),
            "REFERRAL" if s.get("referral") else ("NO_REFERRAL" if s.get("referral") is False else "INCOMPLETE"),
            ";".join(s.get("referral_eyes", [])),
            od.get("status", ""),
            od.get("sphere_D", ""),
            od.get("cylinder_D", ""),
            od.get("se_D", ""),
            od.get("label", ""),
            od.get("frames_used", ""),
            os_eye.get("status", ""),
            os_eye.get("sphere_D", ""),
            os_eye.get("cylinder_D", ""),
            os_eye.get("se_D", ""),
            os_eye.get("label", ""),
            os_eye.get("frames_used", ""),
            od_gt.get("sphere_D", ""),
            od_gt.get("cylinder_D", ""),
            od_gt.get("se_D", ""),
            os_gt.get("sphere_D", ""),
            os_gt.get("cylinder_D", ""),
            os_gt.get("se_D", "")
        ]
        writer.writerow(row)
    
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=eeye_sessions_export.csv"}
    )

@api_bp.route("/api/settings", methods=["GET", "POST"])
def manage_settings():
    if request.method == "POST":
        data = request.get_json() or {}
        for k, v in data.items():
            if k == "research_mode":
                val = "1" if v in (True, 1, "1", "true", "True") else "0"
                store.set_setting(k, val)
            else:
                store.set_setting(k, v)
        return jsonify({"success": True})
    
    return jsonify({
        "lang": store.get_setting("lang", "en"),
        "site_name": store.get_setting("site_name", ""),
        "clock_set": store.get_setting("clock_set", "1") == "1",
        "research_mode": store.get_setting("research_mode", "0") == "1",
        "device_name": DEVICE_NAME,
        "ssid": DEVICE_SSID,
        "ip": DEVICE_IP,
        "version": SOFTWARE_VERSION,
        "storage_free_gb": get_storage_free_str(),
        "tof_calibrated_date": TOF_CALIBRATED_DATE or "Not recorded",
        "led_drive_setting": LED_DRIVE_SETTING or "Not set",
        "mock_mode": MOCK_MODE
    })

@api_bp.route("/api/clock", methods=["POST"])
def set_clock():
    data = request.get_json() or {}
    iso_time = data.get("iso_timestamp")
    store.set_setting("clock_set", "1")
    return jsonify({"success": True, "device_time": iso_time or datetime.now().isoformat()})

@api_bp.route("/api/sessions/delete-all", methods=["POST"])
def delete_all_sessions_endpoint():
    store.delete_all_sessions()
    return jsonify({"success": True, "message": "All sessions deleted"})
