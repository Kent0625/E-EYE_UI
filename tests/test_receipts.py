import hashlib
import io
import json
from pathlib import Path
import shutil
import subprocess

import pytest
from flask import Flask
from PIL import Image

from app import store
from app.receipts import init_receipts_db, receipts_bp


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(store, 'DATABASE_PATH', str(tmp_path / 'sessions.db'))
    monkeypatch.setenv('EEYE_RECEIPTS', str(tmp_path / 'receipts'))
    store.init_db()
    init_receipts_db()
    store.set_setting('research_mode', '1')
    for session_id in ('first', 'second'):
        store.create_session({
            'id': session_id, 'participant_code': 'TEST-' + session_id,
            'status': 'captured', 'eyes': {
                'OD': {'status': 'captured', 'capture_path': 'original/OD', 'sphere_D': -2.5},
                'OS': {'status': 'captured', 'capture_path': 'original/OS'},
            },
        })
    app = Flask(__name__)
    app.config['TESTING'] = True
    app.register_blueprint(receipts_bp)
    return app.test_client()


def image_bytes():
    buffer = io.BytesIO()
    Image.new('RGB', (100, 100), 'white').save(buffer, 'JPEG')
    return buffer.getvalue()


def upload(client, session='first'):
    return client.post(f'/api/sessions/{session}/receipts', data={
        'participant_code': 'TEST-' + session,
        'image': (io.BytesIO(image_bytes()), '../../receipt.jpg'),
    }, content_type='multipart/form-data')


def submission(**updates):
    payload = {
        'confirmed': True, 'participant_code': 'TEST-first',
        'reference_method': 'manual', 'eyes': {
            'OD': {'sphere_D': -1.25, 'cylinder_D': -0.5, 'expected_revision': 0},
            'OS': {'sphere_D': 0.25, 'cylinder_D': -0.25, 'expected_revision': 0},
        },
    }
    payload.update(updates)
    return payload


def confirm(client, payload):
    return client.post('/api/sessions/first/confirmed-ground-truth', json=payload)


def test_receipt_preserves_source_and_is_scoped_to_session(client):
    response = upload(client)
    assert response.status_code == 201
    receipt = response.get_json()
    assert receipt['sha256'] == hashlib.sha256(image_bytes()).hexdigest()
    assert '..' not in receipt['id']
    image = client.get(receipt['image_url'])
    assert image.data == image_bytes()
    assert image.headers['Cache-Control'] == 'no-store'
    assert client.get(receipt['image_url'].replace('/first/', '/second/')).status_code == 404
    assert len(client.get('/api/sessions/first/receipts').json['receipts']) == 1


def test_research_mode_and_cross_origin_are_checked(client):
    store.set_setting('research_mode', '0')
    assert upload(client).status_code == 403
    assert confirm(client, submission()).status_code == 403
    store.set_setting('research_mode', '1')
    assert client.post('/api/sessions/first/confirmed-ground-truth',
        json=submission(), headers={'Origin': 'https://unrelated.example'}).status_code == 403


def test_receipt_requires_participant_and_valid_bounded_image(client):
    assert client.post('/api/sessions/first/receipts', data={
        'participant_code': 'WRONG', 'image': (io.BytesIO(image_bytes()), 'a.jpg')
    }).status_code == 409
    assert client.post('/api/sessions/first/receipts', data={
        'participant_code': 'TEST-first', 'image': (io.BytesIO(b'<svg/>'), 'a.jpg')
    }).status_code == 400
    assert client.post('/api/sessions/first/receipts', data={
        'participant_code': 'TEST-first',
        'image': (io.BytesIO(b'x' * (12 * 1024 * 1024 + 1)), 'a.jpg'),
    }).status_code == 413


@pytest.mark.parametrize('updates', [
    {'confirmed': False}, {'confirmed': 'true'}, {'participant_code': 'WRONG'},
    {'reference_method': 'printed_average'}, {'reference_method': 'unknown'},
    {'eyes': {'OD': {'sphere_D': -1}}},
    {'eyes': {'OD': {'sphere_D': True, 'cylinder_D': 0}}},
    {'eyes': {'OD': {'sphere_D': 'NaN', 'cylinder_D': 0}}},
    {'eyes': {'RIGHT': {'sphere_D': 1, 'cylinder_D': 0}}},
])
def test_confirmation_rejects_unsafe_or_incomplete_values(client, updates):
    assert confirm(client, submission(**updates)).status_code in (400, 409)
    assert 'ground_truth' not in store.get_session('first')['eyes']['OD']


def test_both_eyes_save_atomically_without_changing_device_data(client):
    payload = submission()
    payload['eyes']['OS']['cylinder_D'] = None
    assert confirm(client, payload).status_code == 400
    assert 'ground_truth' not in store.get_session('first')['eyes']['OD']
    response = confirm(client, submission())
    assert response.status_code == 200
    od = response.json['eyes']['OD']
    assert od['sphere_D'] == -2.5
    assert od['capture_path'] == 'original/OD'
    assert od['ground_truth']['se_D'] == -1.5
    assert od['ground_truth']['revision'] == 1
    assert confirm(client, submission()).status_code == 409
    assert store.get_session('first')['eyes']['OD']['ground_truth']['revision'] == 1


def test_wrong_session_receipt_cannot_be_confirmed(client):
    receipt = upload(client, 'second').json
    assert confirm(client, submission(reference_method='printed_average',
        receipt_id=receipt['id'])).status_code == 400


def test_three_readings_are_averaged_by_server_and_preserved(client):
    receipt = upload(client).json
    payload = submission(receipt_id=receipt['id'], reference_method='three_readings', eyes={
        'OD': {'sphere_D': 99, 'cylinder_D': 99, 'expected_revision': 0, 'readings': [
            {'sphere_D': -1, 'cylinder_D': -0.25},
            {'sphere_D': -1.25, 'cylinder_D': -0.5},
            {'sphere_D': -1.25, 'cylinder_D': -0.5},
        ]},
    })
    response = confirm(client, payload)
    assert response.status_code == 200
    truth = response.json['eyes']['OD']['ground_truth']
    assert truth['sphere_D'] == pytest.approx(-3.5 / 3)
    assert truth['cylinder_D'] == pytest.approx(-1.25 / 3)
    assert len(truth['readings']) == 3
    assert truth['se_D'] == -1.38


def test_audit_persists_after_reinitialization_and_records_correction(client):
    assert confirm(client, submission()).status_code == 200
    payload = submission()
    for eye in payload['eyes'].values():
        eye['expected_revision'] = 1
    payload['eyes']['OD']['sphere_D'] = -1.5
    payload['ocr_text'] = 'OD -1.00 -0.50 90'
    assert confirm(client, payload).status_code == 200
    init_receipts_db()
    with store.get_connection() as db:
        audits = db.execute('SELECT * FROM ground_truth_audit WHERE session_id = ? ORDER BY id', ('first',)).fetchall()
    assert len(audits) == 4
    assert json.loads(audits[2]['previous_json'])['sphere_D'] == -1.25
    assert json.loads(audits[2]['confirmed_json'])['sphere_D'] == -1.5
    assert audits[2]['ocr_text'] == payload['ocr_text']


def test_deleted_session_cannot_receive_or_expose_receipts(client):
    receipt = upload(client).json
    store.delete_session('first')
    assert client.get(receipt['image_url']).status_code == 404
    assert upload(client).status_code == 404
    assert confirm(client, submission()).status_code == 404


def test_receipt_parser_requires_explicit_eye_signs_and_reference_rows():
    node = shutil.which('node')
    if not node:
        pytest.skip('Node is needed for the browser parser test')
    source = (Path(__file__).resolve().parents[1] / 'app/static/js/receipt-parser.js').read_text(encoding='utf-8')
    script = source.replace('export function', 'function') + r'''
const assert = require('node:assert/strict');
const parsed = parseReceiptDraft('<R>\nAVG -1.25 -0.50 90\n<L>\nAVG +0.25 -0.25 180');
assert.equal(parsed.eyes.OD.sphere_D, -1.25);
assert.equal(parsed.eyes.OS.sphere_D, 0.25);
assert.equal(parsed.eyes.OS.axis_deg, 180);
assert.equal(parsed.requiresConfirmation, true);
for (const text of ['AVG -1.25 -0.50 90', '<R>\nAVG 1.25 -0.50 90', '<R>\nAVG -1.25 0.50 90', '<R>\n-1.25 -0.50 90', 'OD OS\nAVG -1.25 -0.50 90']) {
  assert.deepEqual(parseReceiptDraft(text).eyes, {});
}
const three = parseReceiptDraft('OD\n-1.00 -0.25 90\n-1.25 -0.50 90\n-1.25 -0.50 90');
assert.equal(three.eyes.OD.method, 'three_readings');
assert.equal(three.eyes.OD.readings.length, 3);
assert.deepEqual(parseReceiptDraft('OD\nKER\nAVG -1.25 -0.50 90').eyes, {});
'''
    result = subprocess.run([node, '-e', script], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_incomplete_capture_never_renders_no_referral(client):
    app = Flask(__name__, template_folder=str(Path(__file__).resolve().parents[1] / 'app/templates'))
    with app.test_request_context():
        rendered = app.jinja_env.get_template('result.html').render(
            session=store.get_session('first'), research_mode=True, mock_mode=False,
            t=lambda key, **kwargs: key, current_lang='en', active_nav='screen',
        )
    assert 'result.incomplete' in rendered
    assert 'result.noRefer' not in rendered
    assert 'Capture saved. Prediction unavailable.' in rendered
    assert '_sample.jpg' not in rendered
