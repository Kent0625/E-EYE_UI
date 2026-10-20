# E-Eye Hardware Seam & Hardware Abstraction Interface

This document specifies the exact interface boundary between the E-Eye Web Interface and the underlying physical hardware components (Raspberry Pi camera, Time-of-Flight distance sensor, and refraction inference pipeline).

Currently, all user interface interactions, API endpoints, and test suites run against mock implementations (`app/mock/fixtures.py`, `app/mock/generator.py`). Replacing the mock layer with physical hardware requires implementing the seams defined below without modifying the UI layer.

---

## 1. Architecture Overview

```
+-------------------------------------------------------------+
|               E-Eye Operator Web UI (Browser)               |
+-------------------------------------------------------------+
                              |
                     HTTP / SSE / MJPEG
                              v
+-------------------------------------------------------------+
|               Flask Application Layer (app/api.py)           |
+-------------------------------------------------------------+
                              |
               Hardware Seam Abstraction Layer
        (Currently conditionally dispatched via MOCK_MODE)
                              |
        +---------------------+---------------------+
        |                     |                     |
        v                     v                     v
+----------------+   +-----------------+   +------------------+
| Camera Seam    |   | ToF Distance    |   | ML Processing    |
| (Preview/Burst)|   | Sensor (I2C)    |   | Pipeline         |
+----------------+   +-----------------+   +------------------+
```

---

## 2. Sensor & Device Interfaces

### 2.1 Camera Interface (`CameraDevice`)

The camera subsystem provides two modes: continuous low-latency alignment preview and triggered high-speed capture.

#### A. Alignment Preview Stream
- **HTTP Endpoint**: `GET /api/preview.mjpg`
- **Protocol**: `multipart/x-mixed-replace; boundary=frame`
- **Output Format**: Continuous stream of JPEG frames (`image/jpeg`).
- **Resolution**: 640 x 480 pixels.
- **Target Frame Rate**: 10 to 15 frames per second.
- **Latency**: Under 150 ms end-to-end to permit operator alignment.
- **Hardware Implementation**:
  ```python
  from picamera2 import Picamera2

  def generate_real_mjpeg_stream(camera: Picamera2):
      """Yields multipart JPEG frames from real camera preview stream."""
      while True:
          frame_bytes = camera.capture_array("main") # or JPEG buffer
          yield (b"--frame\r\n"
                 b"Content-Type: image/jpeg\r\n\r\n" + frame_bytes + b"\r\n")
  ```

#### B. 5-Second Capture Burst
- **Trigger**: `POST /api/sessions/<id>/record` followed by `GET /api/sessions/<id>/record/stream?eye=OD`
- **Operation**: Synchronizes infrared LED illuminator firing with sensor frame exposure.
- **Capture Target**: 10 to 30 frames captured during continuous aligned positioning.
- **Output**: Saved uncompressed / high-quality frames in `/data/sessions/<id>/<eye>/`.

#### C. Precheck Capture
- **HTTP Endpoint**: `POST /api/precheck`
- **Operation**: Captures a single calibration frame under IR illumination and returns image brightness statistics.
- **Return Contract**:
  ```json
  {
    "crescent_frame_url": "/media/<filename>.jpg",
    "tof_ok": true,
    "brightness_ok": true,
    "brightness_mean": 154
  }
  ```

---

### 2.2 Time-of-Flight (ToF) Distance Interface (`DistanceSensor`)

The distance sensor continuously measures the physical distance from the photorefractor aperture to the participant's cornea.

- **HTTP Endpoint**: `GET /api/distance`
- **Protocol**: Server-Sent Events (`text/event-stream`)
- **Sampling Frequency**: ~5 Hz (every 200 ms).
- **Physical Sensor**: STMicroelectronics VL53L1X or VL53L0X connected via I2C (`/dev/i2c-1`), default 7-bit address `0x29`.
- **Target Measurement Band**: **10.0 cm to 15.0 cm** (nominal: 12.5 cm).
- **State Classification Rules**:
  - Distance $< 10.0\text{ cm}$: `too_close`
  - $10.0\text{ cm} \le \text{Distance} \le 15.0\text{ cm}$: `ok`
  - Distance $> 15.0\text{ cm}$: `too_far`
  - Signal clipped, sensor timeout, or out-of-range ($> 50.0\text{ cm}$): `invalid`
- **SSE Event Contract**:
  ```json
  data: {
    "cm": 13.2,
    "valid": true,
    "state": "ok",
    "ts": 1714500000.123
  }
  ```

---

### 2.3 Refraction Inference & Processing Pipeline

Following recording completion, the backend executes frame quality filtering and crescent feature calculation.

- **HTTP Endpoint**: `GET /api/sessions/<id>/events`
- **Protocol**: Server-Sent Events (`text/event-stream`)
- **Progress Events**:
  ```
  data: {"step": "extracting", "label": "Extracting frames..."}
  data: {"step": "quality_check", "label": "Checking frame quality..."}
  data: {"step": "feature_calc", "label": "Computing pupil crescent features..."}
  data: {"step": "inferring", "label": "Estimating refractive state..."}
  data: {"step": "saving", "label": "Finalizing session..."}
  data: {"step": "complete", "status": "ok"}  // or "retake_needed"
  ```
- **Session Data Result Contract**:
  If quality threshold is met ($\ge 8$ valid frames):
  ```json
  {
    "status": "ok",
    "sphere_D": -1.50,
    "cylinder_D": -0.50,
    "se_D": -1.75,
    "label": "myopia_mild",
    "frames_used": 10,
    "frames_total": 118,
    "distance_cm": {"min": 12.1, "max": 13.4},
    "thumbnail_url": "/media/<session_id>_OD_crop.jpg",
    "ground_truth": null
  }
  ```
  If quality threshold fails ($< 8$ valid frames):
  ```json
  {
    "status": "retake_needed",
    "frames_used": 4,
    "frames_total": 110,
    "error_reason": "few_valid_frames"
  }
  ```
  *(Permitted `error_reason` keys: `few_valid_frames`, `blink`, `motion_blur`, `reflection`)*

- **Referral Calculation Contract**:
  Spherical Equivalent ($SE$) must be computed strictly via `app.clinical.compute_se(sphere_D, cylinder_D)`:
  $$SE = \text{round}\left(\text{sphere} + \frac{\text{cylinder}}{2}, 2\right)$$
  The screening referral rule triggers if **either** eye has $SE < -0.50\text{ D}$ or $SE > +0.50\text{ D}$.

---

## 3. What Remains Untested on Real Hardware

Because development and validation occurred without physical Raspberry Pi hardware attached, the following operational behaviors remain untested on real hardware:

1. **Camera Sensor Initialization & Stream Latency under `Picamera2`**:
   - Whether simultaneous low-latency MJPEG streaming and burst capturing requires dual stream buffers or causes I/O bottlenecks on Raspberry Pi OS.
2. **Ambient Tropical Sunlight Interference with VL53L1X ToF Sensor**:
   - In rural outdoor or non-darkened clinic environments in Bukidnon/Sumilao, high ambient infrared sunlight can reduce the maximum ranging distance of 940 nm VCSEL ToF sensors or trigger false timeouts.
3. **Hardware Strobe Synchronization**:
   - Synchronization timing between GPIO pulses driving the infrared LED ring and the camera's rolling shutter readout window.
4. **Thermal Throttling Under Extended Use**:
   - Raspberry Pi 4/5 CPU core temperature and potential thermal throttling when running continuous back-to-back 5-second video captures and feature extraction without active cooling.
5. **I2C Bus Recovery on Ribbon Cable Disconnect**:
   - Behavior of the Linux I2C kernel driver (`i2c-bcm2835`) if the ToF flex cable experiences physical vibration or intermittent contact during device repositioning.
6. **SQLite Write-Ahead Logging & Sudden Power Loss**:
   - Resiliency of the database storage when power is abruptly cut by battery disconnection during active field operation.
