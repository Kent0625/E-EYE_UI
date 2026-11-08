"""Queue the fixed, root-owned Pi shutdown service after operator confirmation."""
from pathlib import Path
import subprocess
import sys
from flask import Blueprint, current_app, jsonify, request

power_bp = Blueprint('power', __name__)


def _shutdown_installed():
    return (sys.platform == 'linux'
            and Path('/etc/systemd/system/eeye-shutdown.service').is_file()
            and Path('/etc/polkit-1/rules.d/49-eeye-shutdown.rules').is_file())


def _available():
    return (not current_app.config.get('MOCK_MODE', True)
            and not current_app.config.get('DEVICE_DISCONNECTED', False)
            and _shutdown_installed())


@power_bp.get('/api/device/power')
def power_status():
    return jsonify(available=_available(), pending=current_app.extensions.get('shutdown_pending', False),
                   uncertain=current_app.extensions.get('shutdown_uncertain', False))


@power_bp.post('/api/device/shutdown')
def shutdown_device():
    if request.headers.get('Origin') != request.host_url.rstrip('/'):
        return jsonify(error='Open Settings on this device to request shutdown.'), 403
    body = request.get_json(silent=True)
    if not isinstance(body, dict) or body.get('confirmed') is not True:
        return jsonify(error='Confirm that you want to shut down the Raspberry Pi.'), 400
    if not _available():
        return jsonify(error='Shutdown is unavailable. Connect to a Pi with shutdown control installed.'), 503
    pending = current_app.extensions.get('shutdown_pending', False)
    uncertain = current_app.extensions.get('shutdown_uncertain', False)
    if pending and not uncertain:
        return jsonify(pending=True), 202
    pipeline = current_app.extensions.get('capture_pipeline')
    if not pipeline or (not pending and not pipeline.lock.acquire(blocking=False)):
        return jsonify(error='The device is busy. Wait for capture or file preparation to finish.'), 409
    try:
        subprocess.run(['/usr/bin/systemctl', '--no-ask-password', '--no-block', 'start', 'eeye-shutdown.service'],
                       check=True, capture_output=True, timeout=5)
    except subprocess.TimeoutExpired:
        current_app.extensions.update(shutdown_pending=True, shutdown_uncertain=True)
        return jsonify(error='Shutdown was not confirmed. Capture is paused; check the Pi or retry shutdown.'), 503
    except (OSError, subprocess.SubprocessError):
        if not uncertain:
            pipeline.lock.release()
        return jsonify(error='Shutdown was not confirmed. Check the Pi before retrying.'), 503
    # Keep capture locked until the OS exits so another eye cannot start in the delay.
    current_app.extensions['shutdown_pending'] = True
    current_app.extensions['shutdown_uncertain'] = False
    return jsonify(pending=True), 202
