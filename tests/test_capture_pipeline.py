import json
import threading
import time
import pytest
from app import store
from app.capture import CapturePipeline, init_capture_db, latest_job


class Camera:
    active_until = 0
    def __init__(self, drift=False):
        self.sequence = 0
        self.drift = drift
    def start(self):
        pass
    def reading(self):
        return {'stable': True, 'valid': True, 'cm': 12.0}
    def illuminate(self, seconds):
        pass
    def frame(self, after=0, timeout=2):
        time.sleep(.01)
        self.sequence += 1
        return dict(sequence=self.sequence, jpeg=b'raw-test-frame', monotonic=time.monotonic(),
                    timestamp=time.time(), cm=None if self.drift else 12.0)


@pytest.fixture
def pipeline(tmp_path, monkeypatch):
    monkeypatch.setattr(store, 'DATABASE_PATH', str(tmp_path/'db.sqlite3'))
    monkeypatch.delenv('EEYE_PUPIL_MODEL', raising=False)
    store.init_db()
    init_capture_db()
    store.create_session(dict(id='case', participant_code='TEST-001', consent_age=True,
        consent_signed=True, eyes={'OD': {'status':'not_recorded'}, 'OS': {'status':'not_recorded'}}))
    return CapturePipeline(Camera(), tmp_path/'captures', duration=.15)


def wait_complete(pipeline):
    assert pipeline.lock.acquire(timeout=3), 'Capture did not finish'
    pipeline.lock.release()
    return latest_job('case','OD')


def test_capture_persists_without_browser_and_never_fabricates_prediction(pipeline):
    job = pipeline.start('case','OD')
    complete = wait_complete(pipeline)
    assert complete['state'] == 'complete'
    assert complete['frames_captured'] > 0
    eye = store.get_session('case')['eyes']['OD']
    assert eye['status'] == 'captured'
    assert eye['prediction_status'] == 'unavailable'
    assert 'sphere_D' not in eye
    assert (pipeline.root/job['id']/'capture.json').exists()


def test_duplicate_capture_rejected_and_ground_truth_preserved(pipeline):
    pipeline.start('case','OD')
    with pytest.raises(RuntimeError, match='already running'):
        pipeline.start('case','OD')
    store.update_session('case', eyes={'OD': {'ground_truth': {'sphere_D': -1}}, 'OS': {'status':'not_recorded'}})
    wait_complete(pipeline)
    assert store.get_session('case')['eyes']['OD']['ground_truth']['sphere_D'] == -1


def test_sensor_failure_flags_retake_and_preserves_capture(pipeline):
    pipeline.hardware.drift=True
    pipeline.start('case','OD')
    assert wait_complete(pipeline)['success'] is False
    assert store.get_session('case')['eyes']['OD']['status'] == 'retake_needed'


def test_bad_eye_unstable_distance_and_missing_consent_block_capture(pipeline):
    with pytest.raises(ValueError): pipeline.start('case','left')
    pipeline.hardware.reading=lambda: {'stable':False}
    with pytest.raises(ValueError, match='10 to 15'): pipeline.start('case','OD')
    assert not pipeline.lock.locked()


def test_restart_marks_incomplete_jobs_interrupted(pipeline):
    with store.get_connection() as db:
        db.execute("INSERT INTO capture_jobs(id,session_id,eye,state,payload) VALUES ('old','case','OD','recording','{}')")
    init_capture_db()
    assert latest_job('case','OD')['state']=='interrupted'
