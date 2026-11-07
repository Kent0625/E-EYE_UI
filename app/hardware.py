"""Single owner of the Pi camera, distance sensor and configured LED output."""
import atexit
import os
import threading
import time
from collections import deque


class PiHardware:
    def __init__(self):
        self.condition = threading.Condition()
        self.latest = None
        self.distance = None
        self.distance_time = 0
        self.distance_history = deque(maxlen=100)
        self.stable_since = None
        self.sequence = 0
        self.error = None
        self.running = False
        self.camera = self.sensor = self.led = None
        self.active_until = 0
        self.start_lock = threading.Lock()
        atexit.register(self.close)

    def start(self):
        with self.start_lock:
            if self.running:
                return
            try:
                import board
                import busio
                import adafruit_vl53l0x
                from picamera2 import Picamera2
                from gpiozero import PWMLED
                pin = os.environ.get('EEYE_LED_PIN')
                if not pin:
                    raise RuntimeError('LED pin is not configured. Use the verified device wiring.')
                offset = os.environ.get('EEYE_TOF_OFFSET_MM')
                if offset is None:
                    raise RuntimeError('Sensor-to-camera offset is not configured.')
                self.offset_mm = float(offset)
                self.led_duty = float(os.environ['EEYE_LED_DUTY'])
                if not 0 < self.led_duty <= 1:
                    raise RuntimeError('LED duty must match the verified device setting.')
                self.led = PWMLED(int(pin), initial_value=0, frequency=800)
                self.sensor = adafruit_vl53l0x.VL53L0X(busio.I2C(board.SCL, board.SDA))
                self.sensor.measurement_timing_budget = 33000
                self.camera = Picamera2()
                config = self.camera.create_video_configuration(
                    main={'size': (640, 480), 'format': 'RGB888'},
                    controls={'FrameRate': 15}, buffer_count=4)
                self.camera.configure(config)
                controls = {}
                if os.environ.get('EEYE_EXPOSURE_US') and os.environ.get('EEYE_ANALOGUE_GAIN'):
                    controls.update(AeEnable=False,
                                    ExposureTime=int(os.environ['EEYE_EXPOSURE_US']),
                                    AnalogueGain=float(os.environ['EEYE_ANALOGUE_GAIN']))
                if os.environ.get('EEYE_LENS_POSITION'):
                    controls.update(AfMode=0, LensPosition=float(os.environ['EEYE_LENS_POSITION']))
                if controls:
                    self.camera.set_controls(controls)
                self.camera.start()
                self.running = True
                self.error = None
                threading.Thread(target=self._sensor_loop, daemon=True, name='eeye-distance').start()
                threading.Thread(target=self._camera_loop, daemon=True, name='eeye-camera').start()
            except Exception as exc:
                self.error = str(exc)
                self.close()
                raise RuntimeError(self.error) from exc

    def _sensor_loop(self):
        while self.running:
            now = time.monotonic()
            try:
                raw = float(self.sensor.range)
                cm = (raw + self.offset_mm) / 10 if 0 < raw < 2000 else None
            except Exception:
                cm = None
            with self.condition:
                if now - self.distance_time >= 0.5:
                    self.stable_since = None
                self.distance, self.distance_time = cm, now
                self.distance_history.append((now, cm))
                if cm is not None and 10 <= cm <= 15:
                    self.stable_since = self.stable_since or now
                else:
                    self.stable_since = None
            time.sleep(0.1)

    def _camera_loop(self):
        import cv2
        try:
            while self.running:
                illuminated = time.monotonic() < self.active_until
                self.led.value = self.led_duty if illuminated else 0
                request = self.camera.capture_request()
                try:
                    frame = request.make_array('main')
                    metadata = request.get_metadata()
                finally:
                    request.release()
                acquired = time.monotonic()
                sensor_ns = metadata.get('SensorTimestamp')
                if sensor_ns is not None and hasattr(time, 'CLOCK_BOOTTIME'):
                    acquired = sensor_ns / 1e9 + time.monotonic() - time.clock_gettime(time.CLOCK_BOOTTIME)
                with self.condition:
                    samples = [sample for sample in self.distance_history if sample[0] <= acquired]
                    sensor_time, cm = samples[-1] if samples else (0, None)
                    if acquired-sensor_time > .5:
                        cm = None
                ok, jpg = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 95])
                if not ok:
                    raise RuntimeError('Could not encode the camera frame.')
                with self.condition:
                    self.sequence += 1
                    now = time.monotonic()
                    self.latest = dict(sequence=self.sequence, jpeg=jpg.tobytes(),
                        monotonic=acquired, timestamp=time.time()-(now-acquired), cm=cm,
                        sensor_timestamp=sensor_time, illuminated=illuminated,
                        camera_metadata={k: metadata.get(k) for k in
                            ('SensorTimestamp', 'ExposureTime', 'AnalogueGain', 'LensPosition')})
                    self.condition.notify_all()
        except Exception as exc:
            self.error = str(exc)
            self.running = False
        finally:
            if self.led:
                self.led.off()

    def reading(self):
        with self.condition:
            now = time.monotonic()
            fresh = now - self.distance_time < 0.5
            cm = self.distance if fresh else None
            valid = cm is not None
            return dict(cm=round(cm, 2) if valid else None, valid=valid,
                        state='invalid' if not valid else ('too_close' if cm < 10 else 'too_far' if cm > 15 else 'ok'),
                        stable=bool(fresh and self.stable_since and now-self.stable_since >= 1),
                        ts=time.time())

    def illuminate(self, seconds=2):
        self.active_until = max(self.active_until, time.monotonic() + seconds)

    def frame(self, after=0, timeout=2):
        deadline = time.monotonic() + timeout
        with self.condition:
            while not self.latest or self.latest['sequence'] <= after:
                left = deadline-time.monotonic()
                if left <= 0 or self.error:
                    raise RuntimeError(self.error or 'Camera stopped providing frames.')
                self.condition.wait(left)
            return self.latest.copy()

    def close(self):
        self.running = False
        self.active_until = 0
        if self.led:
            self.led.off()
            self.led.close()
            self.led = None
        if self.camera:
            try:
                self.camera.stop()
                self.camera.close()
            except Exception:
                pass
            self.camera = None
