import sys
import threading
import time
from types import SimpleNamespace

import pytest

from app.capture import CapturePipeline
from app.hardware import PiHardware


@pytest.fixture
def drivers(monkeypatch):
    state = SimpleNamespace(buses=[], leds=[], cameras=[], sensor_failures=0,
                            camera_start_error=False, camera_stop_error=False, led_off_error=False)

    class Bus:
        def __init__(self, *args):
            self.deinit_calls = 0
            state.buses.append(self)

        def deinit(self):
            self.deinit_calls += 1

    class Led:
        def __init__(self, *args, **kwargs):
            self.off_calls = self.close_calls = 0
            state.leds.append(self)

        def off(self):
            self.off_calls += 1
            if state.led_off_error:
                raise RuntimeError('GPIO write failed')

        def close(self):
            self.close_calls += 1

    class Sensor:
        def __init__(self, bus):
            if state.sensor_failures:
                state.sensor_failures -= 1
                raise OSError('No I2C device at address 0x29')

        @property
        def range(self):
            raise OSError('Distance sensor disconnected')

    class Camera:
        def __init__(self):
            self.stop_calls = self.close_calls = 0
            state.cameras.append(self)

        def create_video_configuration(self, **kwargs):
            return kwargs

        def configure(self, config):
            pass

        def set_controls(self, controls):
            pass

        def start(self):
            if state.camera_start_error:
                raise RuntimeError('Camera start failed')

        def stop(self):
            self.stop_calls += 1
            if state.camera_stop_error:
                raise RuntimeError('Camera stop failed')

        def close(self):
            self.close_calls += 1

    monkeypatch.setitem(sys.modules, 'board', SimpleNamespace(SCL=1, SDA=2))
    monkeypatch.setitem(sys.modules, 'busio', SimpleNamespace(I2C=Bus))
    monkeypatch.setitem(sys.modules, 'adafruit_vl53l0x', SimpleNamespace(VL53L0X=Sensor))
    monkeypatch.setitem(sys.modules, 'picamera2', SimpleNamespace(Picamera2=Camera))
    monkeypatch.setitem(sys.modules, 'gpiozero', SimpleNamespace(LED=Led, PWMLED=Led))
    monkeypatch.setenv('EEYE_LED_PIN', '18')
    monkeypatch.setenv('EEYE_LED_DUTY', '1')
    monkeypatch.setenv('EEYE_TOF_OFFSET_MM', '0')
    return state


def test_disconnected_sensor_releases_bus_and_reports_camera_not_checked(drivers, tmp_path):
    drivers.sensor_failures = 1
    hardware = PiHardware()
    try:
        health = CapturePipeline(hardware, tmp_path).health()
        assert health['capture_available'] is False
        assert health['tof'] == 'error'
        assert health['camera'] == 'not_checked'
        assert health['led'] == 'stopped'
        assert '0x29' in health['hardware_error']
        assert not drivers.cameras
        assert drivers.buses[0].deinit_calls == 1
        assert drivers.leds[0].close_calls == 1
        assert hardware.sensor is None
        assert hardware.reading()['cm'] is None
        assert hardware.reading()['stable'] is False
    finally:
        hardware.close()


def test_retry_releases_each_attempt_and_cannot_reuse_stale_frame(drivers, monkeypatch):
    drivers.sensor_failures = 2
    hardware = PiHardware()
    monkeypatch.setattr(hardware, '_camera_loop', lambda *args: None)
    monkeypatch.setattr(hardware, '_sensor_loop', lambda *args: None)
    try:
        for _ in range(2):
            with pytest.raises(RuntimeError, match='0x29'):
                hardware.start()
        hardware.latest = {'sequence': 100, 'jpeg': b'old frame'}
        hardware.distance = 12
        hardware.distance_time = time.monotonic()
        hardware.stable_since = time.monotonic() - 3
        hardware.distance_history.append((time.monotonic(), 12))
        hardware.start()
        assert len(drivers.buses) == 3
        assert [bus.deinit_calls for bus in drivers.buses] == [1, 1, 0]
        assert hardware.latest is None
        assert not hardware.distance_history
        assert hardware.reading()['valid'] is False
        with pytest.raises(RuntimeError, match='frames'):
            hardware.frame(timeout=0.01)
        hardware.close()
        hardware.close()
        assert [bus.deinit_calls for bus in drivers.buses] == [1, 1, 1]
        assert [led.close_calls for led in drivers.leds] == [1, 1, 1]
    finally:
        hardware.close()


def test_cleanup_continues_when_camera_stop_or_led_off_raises(drivers):
    drivers.camera_start_error = True
    drivers.camera_stop_error = True
    drivers.led_off_error = True
    hardware = PiHardware()
    try:
        with pytest.raises(RuntimeError, match='Camera start failed'):
            hardware.start()
        assert drivers.cameras[0].close_calls == 1
        assert drivers.leds[0].close_calls == 1
        assert drivers.buses[0].deinit_calls == 1
        assert hardware.camera is hardware.sensor is hardware.led is hardware.i2c is None
    finally:
        hardware.close()


def test_close_wakes_frame_waiter_and_invalidates_distance(drivers, monkeypatch):
    hardware = PiHardware()
    monkeypatch.setattr(hardware, '_camera_loop', lambda *args: None)
    monkeypatch.setattr(hardware, '_sensor_loop', lambda *args: None)
    hardware.start()
    failures = []
    waiting = threading.Event()

    def wait_frame():
        waiting.set()
        try:
            hardware.frame(timeout=10)
        except RuntimeError as error:
            failures.append(str(error))

    waiter = threading.Thread(target=wait_frame)
    waiter.start()
    assert waiting.wait(1)
    hardware.close()
    waiter.join(1)
    assert not waiter.is_alive()
    assert failures
    assert hardware.reading()['valid'] is False


@pytest.mark.parametrize('worker', ['camera', 'sensor'])
def test_driver_reply_during_close_cannot_restore_old_samples(drivers, monkeypatch, worker):
    entered, released = threading.Event(), threading.Event()
    request_releases = []

    def delayed_reply(*args):
        entered.set()
        assert released.wait(2)
        if worker == 'sensor':
            return 120
        return SimpleNamespace(make_array=lambda stream: b'pixels', get_metadata=lambda: {},
                               release=lambda: request_releases.append(True))

    camera_driver = sys.modules['picamera2'].Picamera2
    monkeypatch.setattr(camera_driver, 'stop', lambda self: released.set())
    hardware = PiHardware()
    if worker == 'camera':
        monkeypatch.setattr(camera_driver, 'capture_request', delayed_reply, raising=False)
        monkeypatch.setattr(hardware, '_sensor_loop', lambda *args: None)
        monkeypatch.setitem(sys.modules, 'cv2', SimpleNamespace(
            IMWRITE_JPEG_QUALITY=1,
            imencode=lambda *args: (True, SimpleNamespace(tobytes=lambda: b'old frame'))))
    else:
        monkeypatch.setattr(sys.modules['adafruit_vl53l0x'].VL53L0X, 'range', property(delayed_reply))
        monkeypatch.setattr(hardware, '_camera_loop', lambda *args: None)
    try:
        hardware.start()
        assert entered.wait(1)
        hardware.close()
        assert not hardware._threads
        assert hardware.latest is None
        assert hardware.distance is None
        assert not hardware.distance_history
        assert hardware.reading()['valid'] is False
        with pytest.raises(RuntimeError, match='frames'):
            hardware.frame(timeout=0.01)
        if worker == 'camera':
            assert request_releases == [True]
        assert drivers.buses[0].deinit_calls == 1
    finally:
        released.set()
        hardware.close()


def test_valid_camera_does_not_mask_disconnected_distance_sensor(tmp_path):
    class RunningHardware:
        def start(self):
            pass
        def frame(self, **kwargs):
            return {'jpeg': b'observed frame'}
        def reading(self):
            return {'valid': False, 'stable': False, 'cm': None}

    health = CapturePipeline(RunningHardware(), tmp_path).health()
    assert health['camera'] == 'ok'
    assert health['tof'] == 'error'
    assert health['capture_available'] is False


def test_enabled_estimate_allows_missing_sensor_without_claiming_measurement(drivers, monkeypatch):
    monkeypatch.setenv('EEYE_ALLOW_ESTIMATED_DISTANCE', '1')
    drivers.sensor_failures = 100
    hardware = PiHardware()
    monkeypatch.setattr(hardware, '_camera_loop', lambda *args: None)
    try:
        hardware.start()
        deadline = time.monotonic() + 1
        while hardware.reading()['cm'] is None and time.monotonic() < deadline:
            time.sleep(.01)
        reading = hardware.reading()
        assert reading['cm'] == 12.5
        assert reading['estimated'] is True
        assert reading['stable'] is False
        assert hardware.status()['tof'] == 'estimated'
        assert drivers.cameras
    finally:
        hardware.close()
    assert hardware.reading()['cm'] is None


def test_estimate_never_overrides_valid_out_of_range_sensor(drivers, monkeypatch):
    monkeypatch.setenv('EEYE_ALLOW_ESTIMATED_DISTANCE', '1')
    values = [None]
    def distance(self):
        if values[0] is None:
            raise OSError('disconnected')
        return values[0]
    monkeypatch.setattr(sys.modules['adafruit_vl53l0x'].VL53L0X, 'range', property(distance))
    hardware = PiHardware()
    monkeypatch.setattr(hardware, '_camera_loop', lambda *args: None)
    try:
        hardware.start()
        time.sleep(.15)
        assert hardware.reading()['estimated'] is True
        values[0] = 200
        time.sleep(.15)
        reading = hardware.reading()
        assert reading['cm'] == 20
        assert reading['estimated'] is False
        assert reading['state'] == 'too_far'
        assert reading['stable'] is False
    finally:
        hardware.close()


def test_estimated_distance_cannot_hide_camera_failure(drivers, monkeypatch, tmp_path):
    monkeypatch.setenv('EEYE_ALLOW_ESTIMATED_DISTANCE', '1')
    drivers.sensor_failures = 1
    drivers.camera_start_error = True
    hardware = PiHardware()
    try:
        health = CapturePipeline(hardware, tmp_path).health()
        assert health['capture_available'] is False
        assert health['camera'] == 'error'
        assert hardware.reading()['valid'] is False
    finally:
        hardware.close()
