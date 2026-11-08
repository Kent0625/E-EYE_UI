"""Single owner of the Pi camera, distance sensor and configured LED output."""
import atexit
import math
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
        self.distance_estimated = False
        self.allow_estimate = os.environ.get('EEYE_ALLOW_ESTIMATED_DISTANCE', '0') == '1'
        self.distance_history = deque(maxlen=100)
        self.stable_since = None
        self.sequence = 0
        self.error = None
        self.running = False
        self.camera = self.sensor = self.led = self.i2c = None
        self.active_until = 0
        self.start_lock = threading.RLock()
        self._stop = threading.Event()
        self._threads = []
        self._status = dict(camera='not_checked', tof='not_checked', led='not_checked')
        atexit.register(self.close)

    def start(self):
        with self.start_lock:
            if self.running:
                return
            self.close()
            if self._threads:
                raise RuntimeError('Hardware is still stopping. Retry after it has stopped.')
            with self.condition:
                self.error = None
                self._status = dict(camera='not_checked', tof='not_checked', led='not_checked')
            self._stop = threading.Event()
            component = 'led'
            try:
                from gpiozero import LED, PWMLED
                pin = os.environ.get('EEYE_LED_PIN')
                if not pin:
                    raise RuntimeError('LED pin is not configured. Use the verified device wiring.')
                self.led_duty = float(os.environ['EEYE_LED_DUTY'])
                if not 0 < self.led_duty <= 1:
                    raise RuntimeError('LED duty must match the verified device setting.')
                self.led = (LED(int(pin), initial_value=False) if self.led_duty == 1
                            else PWMLED(int(pin), initial_value=0, frequency=800))
                self._status['led'] = 'ok'
                component = 'tof'
                offset = os.environ.get('EEYE_TOF_OFFSET_MM')
                if offset is None:
                    raise RuntimeError('Sensor-to-camera offset is not configured.')
                self.offset_mm = float(offset)
                if not math.isfinite(self.offset_mm):
                    raise RuntimeError('Sensor-to-camera offset must be a finite measurement.')
                try:
                    self._open_sensor()
                    self._status['tof'] = 'starting'
                except Exception:
                    if not self.allow_estimate:
                        raise
                    self._status['tof'] = 'estimated'
                component = 'camera'
                from picamera2 import Picamera2
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
                self._status['camera'] = 'starting'
                self.running = True
                self._threads = [
                    threading.Thread(target=self._sensor_loop, args=(self._stop, self.sensor),
                                     daemon=True, name='eeye-distance'),
                    threading.Thread(target=self._camera_loop, args=(self._stop, self.camera, self.led),
                                     daemon=True, name='eeye-camera')]
                for thread in self._threads:
                    thread.start()
            except Exception as exc:
                self.error = str(exc)
                self._status[component] = 'error'
                self.close()
                raise RuntimeError(self.error) from exc

    def _open_sensor(self):
        import board
        import busio
        import adafruit_vl53l0x
        bus = busio.I2C(board.SCL, board.SDA)
        try:
            sensor = adafruit_vl53l0x.VL53L0X(bus)
            sensor.measurement_timing_budget = 33000
        except Exception:
            bus.deinit()
            raise
        self.i2c, self.sensor = bus, sensor

    def _sensor_loop(self, stop, sensor):
        retry_at = time.monotonic() + 5
        while not stop.is_set():
            now = time.monotonic()
            try:
                if sensor is None and now >= retry_at:
                    retry_at = now + 5
                    self._open_sensor()
                    sensor = self.sensor
                raw = float(sensor.range)
                cm = (raw + self.offset_mm) / 10 if 0 < raw < 2000 else None
            except Exception:
                cm = None
            estimated = cm is None and self.allow_estimate
            if estimated:
                cm = 12.5
            with self.condition:
                if stop.is_set():
                    return
                self._status['tof'] = 'estimated' if estimated else 'ok' if cm is not None else 'error'
                if now - self.distance_time >= 0.5:
                    self.stable_since = None
                self.distance, self.distance_time = cm, now
                self.distance_estimated = estimated
                self.distance_history.append((now, cm, estimated))
                if not estimated and cm is not None and 10 <= cm <= 15:
                    self.stable_since = self.stable_since or now
                else:
                    self.stable_since = None
            stop.wait(0.1)

    def _camera_loop(self, stop, camera, led):
        component = 'camera'
        try:
            import cv2
            while not stop.is_set():
                illuminated = time.monotonic() < self.active_until
                component = 'led'
                led.value = self.led_duty if illuminated else 0
                component = 'camera'
                request = camera.capture_request()
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
                    sensor_time, cm, estimated = samples[-1] if samples else (0, None, False)
                    if acquired-sensor_time > .5:
                        cm, estimated = None, False
                ok, jpg = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 95])
                if not ok:
                    raise RuntimeError('Could not encode the camera frame.')
                with self.condition:
                    if stop.is_set():
                        return
                    self.sequence += 1
                    now = time.monotonic()
                    self.latest = dict(sequence=self.sequence, jpeg=jpg.tobytes(),
                        monotonic=acquired, timestamp=time.time()-(now-acquired), cm=cm,
                        sensor_timestamp=sensor_time, illuminated=illuminated,
                        distance_estimated=estimated,
                        distance_source='estimated_constant' if estimated else 'tof' if cm is not None else 'unavailable',
                        camera_metadata={k: metadata.get(k) for k in
                            ('SensorTimestamp', 'ExposureTime', 'AnalogueGain', 'LensPosition')})
                    self._status['camera'] = 'ok'
                    self.condition.notify_all()
        except Exception as exc:
            with self.condition:
                if not stop.is_set():
                    self.error = str(exc)
                    self.running = False
                    stop.set()
                    self._clear_samples()
                    self._mark_stopped()
                    self._status[component] = 'error'
        finally:
            try:
                led.off()
            except Exception:
                pass

    def status(self):
        with self.condition:
            return self._status.copy()

    def reading(self):
        with self.condition:
            now = time.monotonic()
            fresh = self.running and now - self.distance_time < 0.5
            cm = self.distance if fresh else None
            valid = cm is not None
            return dict(cm=round(cm, 2) if valid else None, valid=valid,
                        estimated=bool(valid and self.distance_estimated),
                        source='estimated_constant' if valid and self.distance_estimated else 'tof' if valid else 'unavailable',
                        state='invalid' if not valid else ('too_close' if cm < 10 else 'too_far' if cm > 15 else 'ok'),
                        stable=bool(fresh and self.stable_since and now-self.stable_since >= 1),
                        ts=time.time())

    def illuminate(self, seconds=2):
        self.active_until = max(self.active_until, time.monotonic() + seconds)

    def frame(self, after=0, timeout=2):
        deadline = time.monotonic() + timeout
        with self.condition:
            while True:
                if not self.running or self.error:
                    raise RuntimeError(self.error or 'Camera stopped providing frames.')
                if self.latest and self.latest['sequence'] > after:
                    return self.latest.copy()
                left = deadline-time.monotonic()
                if left <= 0:
                    raise RuntimeError('Camera stopped providing frames.')
                self.condition.wait(left)

    def _clear_samples(self):
        self.latest = self.distance = self.stable_since = None
        self.distance_time = 0
        self.distance_estimated = False
        self.distance_history.clear()
        self.condition.notify_all()

    def _mark_stopped(self):
        for component, state in self._status.items():
            if state in ('ok', 'starting'):
                self._status[component] = 'stopped'

    def close(self):
        with self.start_lock:
            with self.condition:
                self.running = False
                self._stop.set()
                self.active_until = 0
                self._clear_samples()
                self._mark_stopped()
            # Every release is independent: a failed stop must not skip close/deinit.
            for resource, operation in ((self.led, 'off'), (self.camera, 'stop')):
                if resource is not None:
                    try:
                        getattr(resource, operation)()
                    except Exception:
                        pass
            for thread in self._threads:
                if thread is not threading.current_thread() and thread.is_alive():
                    thread.join(timeout=2)
            self._threads = [thread for thread in self._threads if thread.is_alive()]
            for resource, operation in ((self.camera, 'close'), (self.led, 'close'),
                                        (self.i2c, 'deinit')):
                if resource is not None:
                    try:
                        getattr(resource, operation)()
                    except Exception:
                        pass
            self.camera = self.sensor = self.led = self.i2c = None
