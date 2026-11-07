import io
import csv
import json
import math
import time
import uuid
import threading
from pathlib import Path
from datetime import datetime
from flask import Blueprint, jsonify, request, Response, send_from_directory, current_app, send_file
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
    if not MOCK_MODE:
        status_data.update(current_app.extensions['capture_pipeline'].health())
        status_data['clock_set'] = datetime.now().year >= 2026
    return jsonify(status_data)

@api_bp.route("/api/distance", methods=["GET"])
def stream_distance():
    if not MOCK_MODE:
        pipeline = current_app.extensions['capture_pipeline']
        def real_distance():
            try:
                pipeline.hardware.start()
            except RuntimeError:
                pass
            while True:
                yield f"data: {json.dumps(pipeline.hardware.reading())}\n\n"
                time.sleep(.2)
        return Response(real_distance(), mimetype='text/event-stream', headers={'Cache-Control':'no-store'})
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
    if not MOCK_MODE:
        hardware = current_app.extensions['capture_pipeline'].hardware
        try:
            hardware.start()
        except RuntimeError as exc:
            return jsonify(error=str(exc)), 503
        def preview():
            sequence = 0
            try:
                while True:
                    hardware.illuminate()
                    frame = hardware.frame(after=sequence)
                    sequence = frame['sequence']
                    yield b'--frame\r\nContent-Type: image/jpeg\r\n\r\n'+frame['jpeg']+b'\r\n'
            except RuntimeError:
                return
        return Response(preview(), mimetype='multipart/x-mixed-replace; boundary=frame')
    return Response(
        generate_mock_mjpeg_stream(),
        mimetype="multipart/x-mixed-replace; boundary=frame"
    )

@api_bp.route("/api/precheck", methods=["POST"])
def run_precheck():
    if not MOCK_MODE:
        try:
            return jsonify(current_app.extensions['capture_pipeline'].precheck())
        except RuntimeError as exc:
            return jsonify(error=str(exc)), 503
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
    session_id = f"s_{uuid.uuid4().hex}"
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
    if eye not in ('OD', 'OS'):
        return jsonify(error='Eye must be OD or OS.'), 400
    if not MOCK_MODE:
        try:
            job = current_app.extensions['capture_pipeline'].start(id, eye)
            return jsonify(dict(job, status='recording_started')), 202
        except ValueError as exc:
            return jsonify(error=str(exc)), 400
        except RuntimeError as exc:
            return jsonify(error=str(exc)), 409
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
    if eye not in ('OD','OS'):
        return jsonify(error='Eye must be OD or OS.'), 400
    if not MOCK_MODE:
        from app.capture import latest_job
        job = latest_job(id, eye)
        if not job:
            return jsonify(error='No capture was started for this eye.'), 404
        observed_id = request.args.get('job', job['id'])
        def observe_capture():
            while True:
                item = latest_job(id, eye)
                if not item or item['id'] != observed_id:
                    payload = dict(event='recording_complete', success=False, message='This capture was replaced. Reload the session.')
                elif item['state'] in ('complete','failed','interrupted'):
                    payload = dict(event='recording_complete', success=item.get('success', False),
                                   frames_captured=item.get('frames_captured',0),
                                   message=item.get('message','Capture interrupted by restart. Retake this eye.'))
                else:
                    left = max(0, int(item['duration_s'] - (time.time()-item['started_at']) + .99))
                    payload = dict(event='tick', seconds_left=left, state=item['state'])
                yield f'data: {json.dumps(payload)}\n\n'
                if payload['event']=='recording_complete':
                    return
                time.sleep(.25)
        return Response(observe_capture(), mimetype='text/event-stream', headers={'Cache-Control':'no-store'})
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
    if not store.get_session(id):
        return jsonify(error='Session not found'), 404
    if not MOCK_MODE:
        from app.capture import latest_job
        eye = request.args.get('eye','OD')
        def observe_processing():
            while True:
                job = latest_job(id,eye)
                done = not job or job['state'] in ('complete','failed','interrupted')
                result = (job or {}).get('result', {})
                payload = dict(step='done' if done else 'extracting', done=done,
                    status=result.get('status','retake_needed'),
                    label=result.get('message') or (job or {}).get('message','Capture is being saved.'))
                yield f'data: {json.dumps(payload)}\n\n'
                if done: return
                time.sleep(.3)
        return Response(observe_processing(), mimetype='text/event-stream', headers={'Cache-Control':'no-store'})
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
    lock = current_app.extensions['capture_pipeline'].lock if not MOCK_MODE else threading.Lock()
    if not lock.acquire(blocking=False):
        return jsonify(error='Wait for capture to finish before deleting sessions.'), 409
    from app.receipts import delete_session_receipts
    try:
        ok = delete_session_receipts(id)
    finally:
        lock.release()
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
    if not MOCK_MODE:
        return jsonify(error='Use the receipt confirmation form to save verified ground truth.'), 409
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
        "OS_gt_sphere_D", "OS_gt_cylinder_D", "OS_gt_se_D",
        "OD_reference_record_json", "OS_reference_record_json",
        "OD_capture_id", "OS_capture_id"
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
            os_gt.get("se_D", ""),
            json.dumps(od_gt, ensure_ascii=False, allow_nan=False),
            json.dumps(os_gt, ensure_ascii=False, allow_nan=False),
            od.get('capture_id',''), os_eye.get('capture_id','')
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
    if not MOCK_MODE:
        return jsonify(error='The device clock is managed by the operating system. Check its time in device settings.'), 409
    data = request.get_json() or {}
    iso_time = data.get("iso_timestamp")
    store.set_setting("clock_set", "1")
    return jsonify({"success": True, "device_time": iso_time or datetime.now().isoformat()})

@api_bp.route("/api/sessions/delete-all", methods=["POST"])
def delete_all_sessions_endpoint():
    lock = current_app.extensions['capture_pipeline'].lock if not MOCK_MODE else threading.Lock()
    if not lock.acquire(blocking=False):
        return jsonify(error='Wait for capture to finish before deleting sessions.'), 409
    from app.receipts import delete_session_receipts
    try:
        delete_session_receipts()
    finally:
        lock.release()
    return jsonify({"success": True, "message": "All sessions deleted"})


@api_bp.get('/api/device/precheck.jpg')
def precheck_image():
    if MOCK_MODE:
        return send_from_directory(MEDIA_FOLDER, 'precheck_crescent.jpg')
    return send_from_directory(current_app.extensions['capture_pipeline'].root, 'precheck.jpg')


@api_bp.get('/api/sessions/<id>/captures/<job_id>/download')
def download_capture(id, job_id):
    import tempfile
    import zipfile
    if MOCK_MODE or not store.get_session(id):
        return jsonify(error='Capture not found'), 404
    for eye in store.get_session(id).get('eyes', {}).values():
        if eye.get('capture_id') == job_id and eye.get('external_storage'):
            location = eye['external_storage']
            return jsonify(error='Capture saved on '+location['device_label']+'. Open that device archive.',
                           external_storage=location), 410
    with store.get_connection() as db:
        row = db.execute('SELECT state FROM capture_jobs WHERE id=? AND session_id=?', (job_id,id)).fetchone()
    if not row or row['state'] not in ('complete','failed','interrupted'):
        return jsonify(error='Capture is not ready to download'), 409
    directory = current_app.extensions['capture_pipeline'].root / job_id
    if not directory.is_dir() or directory.is_symlink() or not any(directory.iterdir()):
        return jsonify(error='Capture files are no longer on the Pi. Open the saved device archive.'), 410
    temporary = tempfile.SpooledTemporaryFile(max_size=16*1024**2)
    with zipfile.ZipFile(temporary,'w',compression=zipfile.ZIP_STORED) as archive:
        for path in directory.iterdir():
            if path.is_file(): archive.write(path,path.name)
    temporary.seek(0)
    response = send_file(temporary, mimetype='application/zip', as_attachment=True,
                         download_name=f'{id}-{job_id}.zip')
    response.call_on_close(temporary.close)
    return response
