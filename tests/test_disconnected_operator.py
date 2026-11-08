import importlib
import pytest
from app import store, config, api


@pytest.fixture
def operator(tmp_path, monkeypatch):
    module = importlib.import_module('app.app')
    monkeypatch.setattr(store, 'DATABASE_PATH', str(tmp_path/'operator.db'))
    monkeypatch.setattr(config, 'CAPTURE_FOLDER', str(tmp_path/'captures'))
    monkeypatch.setenv('EEYE_DATA', str(tmp_path/'data'))
    monkeypatch.setenv('EEYE_RECEIPTS', str(tmp_path/'receipts'))
    monkeypatch.setattr(module, 'MOCK_MODE', False)
    monkeypatch.setattr(api, 'MOCK_MODE', False)
    monkeypatch.setattr(module, 'DEVICE_DISCONNECTED', True, raising=False)
    monkeypatch.setattr(api, 'DEVICE_DISCONNECTED', True, raising=False)
    return module.create_app().test_client()


def test_operator_starts_empty_and_without_simulated_results(operator):
    assert operator.get('/api/sessions').json == []
    home = operator.get('/').data.decode()
    assert 'MOCK DATA' not in home
    assert 'Connect the Raspberry Pi' in home
    assert 'Capture and save' in home
    assert 'id="status-camera"' not in home


def test_disconnected_status_never_reports_ready_or_a_fake_distance(operator):
    status = operator.get('/api/status').json
    assert status['device_connected'] is False
    assert status['capture_available'] is False
    assert status['camera'] == 'not_connected'
    assert status['tof'] == 'not_connected'
    assert status['storage_free_gb'] is None


def test_disconnected_session_creation_is_blocked_with_guidance(operator):
    response = operator.post('/api/sessions', json={'participant_code':'TEST-NOT-SAVED'})
    assert response.status_code == 409
    assert 'Connect' in response.json['error']
    assert operator.get('/api/sessions').json == []


def test_disconnected_precheck_does_not_simulate_success(operator):
    response = operator.post('/api/precheck')
    assert response.status_code == 503
    assert 'Connect' in response.json['error']
