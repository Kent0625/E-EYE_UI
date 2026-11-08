import subprocess
import threading
from types import SimpleNamespace
import pytest
from flask import Flask


@pytest.fixture
def device(monkeypatch):
    from app import power
    app = Flask(__name__)
    app.config.update(MOCK_MODE=False, DEVICE_DISCONNECTED=False)
    app.extensions['capture_pipeline'] = SimpleNamespace(lock=threading.Lock())
    app.register_blueprint(power.power_bp)
    monkeypatch.setattr(power, '_shutdown_installed', lambda: True)
    calls = []
    def run(command, **kwargs):
        calls.append(command)
        return subprocess.CompletedProcess(command, 0)
    monkeypatch.setattr(power.subprocess, 'run', run)
    return app, app.test_client(), calls


def post(client, confirmed=True, origin='http://localhost'):
    return client.post('/api/device/shutdown', json={'confirmed':confirmed}, headers={'Origin':origin})


def test_shutdown_requires_explicit_confirmation_and_same_origin(device):
    app, client, calls = device
    assert post(client, False).status_code == 400
    assert post(client, origin='http://other.local').status_code == 403
    assert client.post('/api/device/shutdown', json={'confirmed':True}).status_code == 403
    assert not calls


def test_capture_blocks_shutdown(device):
    app, client, calls = device
    app.extensions['capture_pipeline'].lock.acquire()
    assert post(client).status_code == 409
    assert not calls
    app.extensions['capture_pipeline'].lock.release()


def test_confirmed_shutdown_queues_only_fixed_unit_and_blocks_new_captures(device):
    app, client, calls = device
    assert post(client).status_code == 202
    assert calls == [['/usr/bin/systemctl', '--no-ask-password', '--no-block', 'start', 'eeye-shutdown.service']]
    assert app.extensions['capture_pipeline'].lock.locked()
    assert client.get('/api/device/power').json['pending'] is True
    assert post(client).status_code == 202
    assert len(calls) == 1


def test_failed_shutdown_releases_capture_lock(device, monkeypatch):
    from app import power
    app, client, calls = device
    def fail(*args, **kwargs): raise subprocess.CalledProcessError(1, args[0])
    monkeypatch.setattr(power.subprocess, 'run', fail)
    assert post(client).status_code == 503
    assert not app.extensions['capture_pipeline'].lock.locked()
    assert client.get('/api/device/power').json['pending'] is False


def test_unconfirmed_timeout_keeps_capture_paused_and_allows_retry(device, monkeypatch):
    from app import power
    app, client, calls = device
    original = power.subprocess.run
    def timeout(*args, **kwargs): raise subprocess.TimeoutExpired(args[0], 5)
    monkeypatch.setattr(power.subprocess, 'run', timeout)
    assert post(client).status_code == 503
    assert app.extensions['capture_pipeline'].lock.locked()
    assert client.get('/api/device/power').json['uncertain'] is True
    monkeypatch.setattr(power.subprocess, 'run', original)
    assert post(client).status_code == 202
    assert client.get('/api/device/power').json['uncertain'] is False


@pytest.mark.parametrize('setting', ['MOCK_MODE','DEVICE_DISCONNECTED'])
def test_simulation_and_disconnected_server_cannot_shutdown(device, setting):
    app, client, calls = device
    app.config[setting] = True
    assert client.get('/api/device/power').json['available'] is False
    assert post(client).status_code == 503
    assert not calls
