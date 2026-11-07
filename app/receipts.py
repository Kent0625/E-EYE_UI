import hashlib
import io
import json
import os
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
import re
import sqlite3
from urllib.parse import urlsplit
from uuid import uuid4
import warnings

from flask import Blueprint, jsonify, request, send_file, url_for
from PIL import Image, UnidentifiedImageError

from app import store
from app.clinical import compute_se
from app.config import PROJECT_ROOT


receipts_bp = Blueprint('receipts', __name__)
MAX_IMAGE_BYTES = 12 * 1024 * 1024
MAX_IMAGE_PIXELS = 25_000_000
RECEIPT_ID = re.compile(r'^[0-9a-f]{32}$')


def receipt_directory():
    return Path(os.environ.get('EEYE_RECEIPTS', str(Path(PROJECT_ROOT) / 'data' / 'receipts')))


def init_receipts_db():
    with store.get_connection() as db:
        db.executescript('''
            CREATE TABLE IF NOT EXISTS receipts (
                id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL REFERENCES sessions(id),
                created_at TEXT NOT NULL,
                mime_type TEXT NOT NULL,
                sha256 TEXT NOT NULL,
                byte_size INTEGER NOT NULL,
                width INTEGER NOT NULL,
                height INTEGER NOT NULL
            );
            CREATE INDEX IF NOT EXISTS receipts_session ON receipts(session_id);
            CREATE TABLE IF NOT EXISTS ground_truth_audit (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL REFERENCES sessions(id),
                eye TEXT NOT NULL,
                receipt_id TEXT,
                confirmed_at TEXT NOT NULL,
                previous_json TEXT,
                confirmed_json TEXT NOT NULL,
                ocr_text TEXT NOT NULL,
                ocr_draft_json TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS ground_truth_session ON ground_truth_audit(session_id);
        ''')


@receipts_bp.before_request
def require_research_session():
    if request.content_length and request.content_length > MAX_IMAGE_BYTES + 65536:
        return jsonify(error='Receipt exceeds 12 MB. Choose a smaller JPEG or PNG.'), 413
    if store.get_setting('research_mode', '0') != '1':
        return jsonify(error='Research mode is disabled. Enable it in Settings.'), 403
    origin = request.headers.get('Origin')
    if request.method == 'POST' and (request.headers.get('Sec-Fetch-Site') == 'cross-site'
            or (origin and urlsplit(origin).netloc != request.host)):
        return jsonify(error='Open the receipt form on this device before saving.'), 403
    session_id = (request.view_args or {}).get('id')
    if session_id and not store.get_session(session_id):
        return jsonify(error='Session not found. Reopen the participant record.'), 404


@receipts_bp.errorhandler(sqlite3.OperationalError)
def database_busy(error):
    if 'locked' in str(error).lower():
        return jsonify(error='The device is saving another change. Retry this save.'), 503
    raise error


def receipt_metadata(row):
    receipt = dict(row)
    receipt['image_url'] = url_for('receipts.get_receipt_image', id=row['session_id'], receipt_id=row['id'])
    return receipt


@receipts_bp.route('/api/sessions/<id>/receipts', methods=['GET', 'POST'])
def session_receipts(id):
    if request.method == 'GET':
        with store.get_connection() as db:
            rows = db.execute('SELECT * FROM receipts WHERE session_id = ? ORDER BY created_at', (id,)).fetchall()
        return jsonify(receipts=[receipt_metadata(row) for row in rows])
    upload = request.files.get('image')
    if upload is None:
        return jsonify(error='Choose a JPEG or PNG receipt photo.'), 400
    content = upload.stream.read(MAX_IMAGE_BYTES + 1)
    if len(content) > MAX_IMAGE_BYTES:
        return jsonify(error='Receipt exceeds 12 MB. Choose a smaller JPEG or PNG.'), 413
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(content)) as image:
                width, height = image.size
                image_format = image.format
                if image_format not in ('JPEG', 'PNG') or getattr(image, 'n_frames', 1) != 1:
                    raise ValueError('Use a single JPEG or PNG photo.')
                if width * height > MAX_IMAGE_PIXELS:
                    raise ValueError('Receipt exceeds 25 megapixels. Choose a smaller photo.')
                image.verify()
            with Image.open(io.BytesIO(content)) as image:
                image.load()
    except (ValueError, OSError, UnidentifiedImageError, Image.DecompressionBombError, Image.DecompressionBombWarning):
        return jsonify(error='Photo cannot be read or is too large. Choose a JPEG or PNG under 25 megapixels.'), 400
    receipt_id = uuid4().hex
    root = receipt_directory()
    root.mkdir(parents=True, exist_ok=True)
    target = root / receipt_id
    try:
        with store.get_connection() as db:
            db.execute('BEGIN IMMEDIATE')
            session = db.execute('SELECT participant_code FROM sessions WHERE id = ?', (id,)).fetchone()
            if session is None:
                return jsonify(error='Session was deleted. Reopen the participant record.'), 404
            if request.form.get('participant_code') != session['participant_code']:
                return jsonify(error='Participant code does not match this session.'), 409
            target.write_bytes(content)
            db.execute('INSERT INTO receipts VALUES (?, ?, ?, ?, ?, ?, ?, ?)', (
                receipt_id, id, datetime.now(timezone.utc).isoformat(),
                'image/jpeg' if image_format == 'JPEG' else 'image/png',
                hashlib.sha256(content).hexdigest(), len(content), width, height,
            ))
            row = db.execute('SELECT * FROM receipts WHERE id = ?', (receipt_id,)).fetchone()
    except Exception:
        target.unlink(missing_ok=True)
        raise
    return jsonify(receipt_metadata(row)), 201


@receipts_bp.route('/api/sessions/<id>/receipts/<receipt_id>/image')
def get_receipt_image(id, receipt_id):
    if not RECEIPT_ID.fullmatch(receipt_id):
        return jsonify(error='Receipt not found.'), 404
    with store.get_connection() as db:
        receipt = db.execute('SELECT * FROM receipts WHERE id = ? AND session_id = ?', (receipt_id, id)).fetchone()
    path = receipt_directory() / receipt_id
    if receipt is None or not path.is_file():
        return jsonify(error='Receipt photo is missing. Attach it again.'), 404
    response = send_file(path, mimetype=receipt['mime_type'], conditional=False)
    response.headers['Cache-Control'] = 'no-store'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    return response


def diopter(value):
    if value is None or isinstance(value, bool) or isinstance(value, (dict, list)):
        raise ValueError('Enter both sphere and cylinder for each selected eye.')
    try:
        number = Decimal(str(value).strip())
    except InvalidOperation as error:
        raise ValueError('Enter a number for sphere and cylinder.') from error
    if not number.is_finite() or not -20 <= number <= 20:
        raise ValueError('Sphere and cylinder must be between -20 and +20 D.')
    return number


def parse_eye(eye, reference_method):
    if not isinstance(eye, dict):
        raise ValueError('Each eye must contain sphere and cylinder measurements.')
    values = {}
    if reference_method == 'three_readings':
        readings = eye.get('readings')
        if not isinstance(readings, list) or len(readings) != 3 or any(not isinstance(r, dict) for r in readings):
            raise ValueError('Enter exactly three readings for each selected eye.')
        spheres = [diopter(reading.get('sphere_D')) for reading in readings]
        cylinders = [diopter(reading.get('cylinder_D')) for reading in readings]
        sphere, cylinder = sum(spheres) / 3, sum(cylinders) / 3
        values['readings'] = [dict(sphere_D=float(s), cylinder_D=float(c)) for s, c in zip(spheres, cylinders)]
    else:
        if eye.get('readings'):
            raise ValueError('Select Mean of three readings to save individual readings.')
        sphere, cylinder = diopter(eye.get('sphere_D')), diopter(eye.get('cylinder_D'))
    values.update(sphere_D=float(sphere), cylinder_D=float(cylinder), se_D=compute_se(sphere, cylinder))
    axis = eye.get('axis_deg')
    if axis is not None and axis != '':
        try:
            axis_decimal = Decimal(str(axis))
        except InvalidOperation as error:
            raise ValueError('Axis must be a whole number from 0 to 180.') from error
        if isinstance(axis, bool) or not axis_decimal.is_finite() or axis_decimal != int(axis_decimal) or not 0 <= axis_decimal <= 180:
            raise ValueError('Axis must be a whole number from 0 to 180.')
        values['axis_deg'] = int(axis_decimal)
    revision = eye.get('expected_revision', 0)
    if type(revision) is not int or revision < 0:
        raise ValueError('Invalid record revision. Reload this session.')
    return values, revision


@receipts_bp.route('/api/sessions/<id>/confirmed-ground-truth', methods=['POST'])
def confirmed_ground_truth(id):
    if request.content_length and request.content_length > 65536:
        return jsonify(error='Receipt transcription is too long.'), 413
    data = request.get_json(silent=True)
    if not isinstance(data, dict) or data.get('confirmed') is not True:
        return jsonify(error='Review the receipt and confirm its values before saving.'), 400
    method = data.get('reference_method')
    if method not in ('printed_average', 'three_readings', 'manual'):
        return jsonify(error='Choose how the reference measurements were obtained.'), 400
    receipt_id = data.get('receipt_id') or None
    if method != 'manual' and receipt_id is None:
        return jsonify(error='Attach the receipt or choose manual entry.'), 400
    if receipt_id is not None and (not isinstance(receipt_id, str) or not RECEIPT_ID.fullmatch(receipt_id)):
        return jsonify(error='Receipt not found in this session.'), 400
    eyes = data.get('eyes')
    if not isinstance(eyes, dict) or not eyes or any(key not in ('OD', 'OS') for key in eyes):
        return jsonify(error='Enter measurements for right eye (OD) or left eye (OS).'), 400
    ocr_text, ocr_draft = data.get('ocr_text', ''), data.get('ocr_draft', {})
    if not isinstance(ocr_text, str) or len(ocr_text) > 20000 or not isinstance(ocr_draft, dict):
        return jsonify(error='Receipt transcription is invalid or too long.'), 400
    try:
        draft_json = json.dumps(ocr_draft, allow_nan=False)
        if len(draft_json) > 20000:
            raise ValueError('Receipt draft is too long.')
        parsed = {key: parse_eye(value, method) for key, value in eyes.items()}
    except (ValueError, TypeError, OverflowError) as error:
        return jsonify(error=str(error)), 400
    confirmed_at = datetime.now(timezone.utc).isoformat()
    with store.get_connection() as db:
        db.execute('BEGIN IMMEDIATE')
        row = db.execute('SELECT * FROM sessions WHERE id = ?', (id,)).fetchone()
        if row is None:
            return jsonify(error='Session was deleted. Reopen the participant record.'), 404
        if data.get('participant_code') != row['participant_code']:
            return jsonify(error='Participant code does not match this session.'), 409
        if receipt_id and not db.execute('SELECT 1 FROM receipts WHERE id = ? AND session_id = ?', (receipt_id, id)).fetchone():
            return jsonify(error='Receipt not found in this session.'), 400
        stored_eyes = json.loads(row['eyes_data'] or '{}')
        # Check every revision before making any changes; a stale browser cannot overwrite a correction.
        for key, (_, revision) in parsed.items():
            previous = stored_eyes.get(key, {}).get('ground_truth') or {}
            if previous.get('revision', 0) != revision:
                return jsonify(error='Ground truth changed in another window. Reload before editing.'), 409
        for key, (values, revision) in parsed.items():
            eye = stored_eyes.setdefault(key, {})
            previous = eye.get('ground_truth')
            values.update(receipt_id=receipt_id, reference_method=method, confirmed_at=confirmed_at,
                          revision=revision + 1, confirmed=True)
            db.execute('''INSERT INTO ground_truth_audit
                (session_id, eye, receipt_id, confirmed_at, previous_json, confirmed_json, ocr_text, ocr_draft_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)''', (
                id, key, receipt_id, confirmed_at, json.dumps(previous), json.dumps(values), ocr_text, draft_json,
            ))
            eye['ground_truth'] = values
        db.execute('UPDATE sessions SET eyes_data = ? WHERE id = ?', (json.dumps(stored_eyes), id))
    return jsonify(store.get_session(id))


def delete_session_receipts(session_id=None):
    """Call as part of a confirmed session deletion, including delete-all."""
    with store.get_connection() as db:
        db.execute('BEGIN IMMEDIATE')
        where, params = (' WHERE session_id = ?', (session_id,)) if session_id else ('', ())
        rows = db.execute('SELECT id FROM receipts' + where, params).fetchall()
        db.execute('DELETE FROM ground_truth_audit' + where, params)
        db.execute('DELETE FROM receipts' + where, params)
        if session_id:
            deleted = db.execute('DELETE FROM sessions WHERE id=?', (session_id,)).rowcount
        else:
            deleted = db.execute('DELETE FROM sessions').rowcount
    root = receipt_directory()
    for row in rows:
        if RECEIPT_ID.fullmatch(row['id']):
            (root / row['id']).unlink(missing_ok=True)
    return deleted
