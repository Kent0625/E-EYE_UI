from app.capture import processing_event


def test_missing_job_is_an_explicit_recovery_state():
    event = processing_event(None, now=100)
    assert event['done'] is True
    assert event['status'] == 'retake_needed'
    assert 'not found' in event['label'].lower()
    assert event['processing_elapsed_s'] is None


def test_recording_does_not_claim_quality_or_prediction_finished():
    event = processing_event(dict(state='recording', started_at=100, duration_s=5,
                                  frames_captured=20), now=102)
    assert event['done'] is False
    assert event['frames_captured'] == 20
    assert event['processing_elapsed_s'] is None
    assert event['phases']['saving'] == 'running'
    assert event['phases']['quality'] == 'waiting'
    assert event['phases']['prediction'] == 'unavailable'


def test_completed_capture_reports_actual_processing_time_and_missing_models():
    job = dict(state='complete', started_at=100, processing_started_at=105,
               completed_at=107.25, frames_captured=75,
               result=dict(status='captured', quality_status='unavailable',
                           prediction_status='unavailable', message='Capture saved.'))
    event = processing_event(job, now=150)
    assert event['processing_elapsed_s'] == 2.25
    assert event['done'] is True
    assert event['phases'] == dict(saving='complete', quality='unavailable', prediction='unavailable')


def test_failed_capture_uses_actual_error_and_stops_timing():
    event = processing_event(dict(state='failed', started_at=100, completed_at=103,
                                  frames_captured=0, message='Camera stopped.'), now=150)
    assert event['status'] == 'retake_needed'
    assert event['label'] == 'Camera stopped.'
    assert event['phases']['saving'] == 'failed'


def test_interrupted_job_without_end_does_not_count_downtime_as_processing():
    job = dict(state='interrupted', started_at=100, processing_started_at=105)
    assert processing_event(job, now=10000)['processing_elapsed_s'] is None
    assert 'interrupted' in processing_event(job, now=10000)['label'].lower()


def test_real_event_endpoint_emits_saved_job_without_starting_hardware(tmp_path, monkeypatch):
    import json
    from app import api, store
    from app.app import create_app
    from app.capture import init_capture_db
    monkeypatch.setattr(store, 'DATABASE_PATH', str(tmp_path/'test.db'))
    monkeypatch.setenv('EEYE_DATA', str(tmp_path/'data'))
    monkeypatch.setenv('EEYE_RECEIPTS', str(tmp_path/'receipts'))
    app = create_app(); init_capture_db()
    payload = dict(started_at=100, processing_started_at=105, completed_at=107.25,
                   frames_captured=75, result=dict(status='captured', quality_status='unavailable'))
    with store.get_connection() as db:
        db.execute('INSERT INTO capture_jobs(id,session_id,eye,state,payload) VALUES (?,?,?,?,?)',
                   ('test-job', 's_mock_refer', 'OD', 'complete', json.dumps(payload)))
    monkeypatch.setattr(api, 'MOCK_MODE', False)
    response = app.test_client().get('/api/sessions/s_mock_refer/events?eye=OD')
    assert response.status_code == 200
    event = json.loads(response.data.decode().strip().removeprefix('data: '))
    assert event['done'] is True
    assert event['processing_elapsed_s'] == 2.25
    assert event['phases']['prediction'] == 'unavailable'
