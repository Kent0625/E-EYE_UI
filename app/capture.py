"""Durable capture jobs. Browser connections observe jobs; they do not run them."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import threading
import time
import uuid
from app import store


def init_capture_db():
    with store.get_connection() as db:
        db.execute('''CREATE TABLE IF NOT EXISTS capture_jobs (
            id TEXT PRIMARY KEY, session_id TEXT NOT NULL, eye TEXT NOT NULL,
            state TEXT NOT NULL, payload TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)''')
        db.execute("UPDATE capture_jobs SET state='interrupted' WHERE state IN ('recording','processing')")


def latest_job(session_id, eye):
    with store.get_connection() as db:
        row = db.execute('SELECT * FROM capture_jobs WHERE session_id=? AND eye=? ORDER BY rowid DESC LIMIT 1',
                         (session_id, eye)).fetchone()
    if not row:
        return None
    return dict(json.loads(row['payload']), id=row['id'], state=row['state'])


class CapturePipeline:
    def __init__(self, hardware, root, duration=5):
        self.hardware = hardware
        self.root = Path(root)
        self.duration = duration
        self.lock = threading.Lock()

    def health(self):
        frame_attempted = False
        try:
            self.hardware.start()
            frame_attempted = True
            self.hardware.frame(timeout=3)
            reading = self.hardware.reading()
            return dict(camera='ok', tof='estimated' if reading.get('estimated') else 'ok' if reading['valid'] else 'error', led='ok',
                        distance_estimated=reading.get('estimated', False),
                        model='missing', capture_available=reading['valid'],
                        model_message='Refraction model is not installed. Receipt collection is available.',
                        capture_busy=self.lock.locked())
        except Exception as exc:
            status = (self.hardware.status() if callable(getattr(self.hardware, 'status', None))
                      else dict(camera='not_checked', tof='not_checked', led='not_checked'))
            if frame_attempted and status['camera'] in ('not_checked', 'starting', 'ok'):
                status['camera'] = 'error'
            return dict(status, model='missing', capture_available=False,
                        capture_busy=self.lock.locked(), hardware_error=str(exc))

    def start(self, session_id, eye):
        if eye not in ('OD', 'OS'):
            raise ValueError('Eye must be OD or OS.')
        if not self.lock.acquire(blocking=False):
            raise RuntimeError('A capture is already running. Wait for it to finish.')
        try:
            session = store.get_session(session_id)
            if not session:
                raise ValueError('Session not found.')
            if not session['consent_age'] or not session['consent_signed']:
                raise ValueError('Record consent before capture.')
            self.hardware.start()
            reading = self.hardware.reading()
            if not (reading['stable'] or (reading.get('estimated') and reading.get('valid'))):
                raise ValueError('Hold a valid 10 to 15 cm distance for one second.')
            self.root.mkdir(parents=True, exist_ok=True)
            if shutil.disk_usage(self.root).free < 250 * 1024**2:
                raise RuntimeError('Storage is low. Export and back up recordings before capturing.')
            job_id = uuid.uuid4().hex
            directory = self.root / job_id
            directory.mkdir()
            payload = dict(id=job_id, session_id=session_id, eye=eye,
                           started_at=time.time(), duration_s=self.duration, frames_captured=0)
            with store.get_connection() as db:
                db.execute('INSERT INTO capture_jobs (id,session_id,eye,state,payload) VALUES (?,?,?,?,?)',
                           (job_id, session_id, eye, 'recording', json.dumps(payload)))
            threading.Thread(target=self._capture, args=(payload, directory), daemon=True,
                             name='eeye-capture').start()
            return payload
        except Exception:
            self.lock.release()
            raise

    def _save(self, payload, state):
        with store.get_connection() as db:
            db.execute('UPDATE capture_jobs SET state=?,payload=? WHERE id=?',
                       (state, json.dumps(payload), payload['id']))

    def _update_eye(self, payload, result):
        # Read/merge under the write lock so concurrent receipt confirmation survives.
        with store.get_connection() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT eyes_data FROM sessions WHERE id=?', (payload['session_id'],)).fetchone()
            if not row:
                return
            eyes = json.loads(row['eyes_data'])
            previous = eyes.get(payload['eye'], {})
            eyes[payload['eye']] = dict(result, ground_truth=previous.get('ground_truth'))
            db.execute("UPDATE sessions SET eyes_data=?,status='captured',referral=NULL,referral_eyes='[]' WHERE id=?",
                       (json.dumps(eyes), payload['session_id']))

    def _capture(self, payload, directory):
        frames = []
        try:
            self.hardware.illuminate(self.duration + 1)
            last = self.hardware.frame()['sequence']
            start = time.monotonic()
            while time.monotonic()-start < self.duration:
                frame = self.hardware.frame(after=last, timeout=2)
                last = frame['sequence']
                elapsed = frame['monotonic']-start
                if elapsed < 0 or elapsed >= self.duration:
                    continue
                filename = f'{len(frames):04d}.jpg'
                (directory / filename).write_bytes(frame['jpeg'])
                entry = {k: v for k, v in frame.items() if k != 'jpeg'}
                entry.update(file=filename, elapsed_s=elapsed, sha256=hashlib.sha256(frame['jpeg']).hexdigest())
                frames.append(entry)
                payload['frames_captured'] = len(frames)
                self._save(payload, 'recording')
            if not frames:
                raise RuntimeError('The camera returned no frames during capture.')
            self._save(payload, 'processing')
            distances = [f['cm'] for f in frames if f['cm'] is not None]
            drift = any(f['cm'] is None or not 10 <= f['cm'] <= 15 for f in frames)
            estimated = any(f.get('distance_estimated', False) for f in frames)
            manifest = dict(payload, frames=frames, distance_drift=None if estimated and not drift else drift,
                            distance_estimated=estimated,
                            capture_format='timestamped-jpeg-sequence', version=1)
            (directory / 'capture.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
            result = dict(status='retake_needed' if drift else 'captured',
                capture_id=payload['id'], frames_total=len(frames), frames_used=0,
                distance_cm={'min': min(distances), 'max': max(distances)} if distances else None,
                distance_estimated=estimated,
                error_reason='Distance changed during capture. Retake this eye.' if drift else None,
                prediction_status='unavailable',
                message='Capture saved. Refraction prediction is unavailable until the trained model is installed.')
            if not drift:
                result.update(self._quality(directory, frames))
            self._update_eye(payload, result)
            payload.update(result=result, success=not drift,
                           message=result.get('message'), completed_at=time.time())
            self._save(payload, 'complete')
        except Exception as exc:
            payload.update(success=False, message=str(exc), frames_captured=len(frames), completed_at=time.time())
            (directory / 'capture.json').write_text(json.dumps(dict(payload, frames=frames), indent=2), encoding='utf-8')
            self._save(payload, 'failed')
            self._update_eye(payload, dict(status='retake_needed', capture_id=payload['id'],
                             frames_total=len(frames), frames_used=0, error_reason=str(exc)))
        finally:
            self.hardware.active_until = 0
            self.lock.release()

    def _quality(self, directory, frames):
        model = os.environ.get('EEYE_PUPIL_MODEL')
        if not model or not Path(model).is_file():
            return dict(quality_status='unavailable', message='Capture saved. Pupil and refraction models are not configured.')
        from app.pupil import analyse_sequence
        return analyse_sequence(directory, frames, model)

    def precheck(self):
        if not self.lock.acquire(blocking=False):
            raise RuntimeError('A capture is running. Wait before checking the device.')
        try:
            self.hardware.start()
            self.hardware.illuminate(6)
            end, after, readings, frame = time.monotonic()+5, 0, [], None
            estimated = False
            while time.monotonic() < end:
                frame = self.hardware.frame(after=after)
                after = frame['sequence']
                readings.append(frame['cm'])
                estimated = estimated or frame.get('distance_estimated', False)
            self.root.mkdir(parents=True, exist_ok=True)
            (self.root / 'precheck.jpg').write_bytes(frame['jpeg'])
            return dict(crescent_frame_url='/api/device/precheck.jpg',
                        distance_estimated=estimated,
                        tof_ok=not estimated and bool(readings) and all(cm is not None and 10 <= cm <= 15 for cm in readings),
                        brightness_ok=False, brightness_mean=None,
                        brightness_message='Confirm pupil visibility and calibrated brightness before participant capture.')
        finally:
            self.hardware.active_until = 0
            self.lock.release()
