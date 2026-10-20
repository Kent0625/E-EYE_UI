# E-Eye Hardware Seam & Hardware Abstraction Interface

This document specifies the interface boundary between the E-Eye Operator Web Interface and the physical hardware specified in the manuscript.

Currently, all user interface interactions, API endpoints, and test suites run against mock implementations (`app/mock/fixtures.py`, `app/mock/generator.py`). Replacing the mock layer with physical hardware requires implementing the seams defined below without modifying the UI layer.

---

## 1. Hardware Specification (Per Manuscript)

As specified in the research manuscript and brief (§3):
- **Host System**: Raspberry Pi 4 Model B (4 GB RAM).
- **Camera Sensor**: Raspberry Pi Camera Module 3 NoIR (infrared-sensitive, without infrared cut filter).
- **Light Source**: Single 850 nm infrared LED positioned eccentrically adjacent to the camera aperture for photorefraction crescent generation.
- **Distance Sensor**: STMicroelectronics VL53L0X Time-of-Flight (ToF) distance sensor (accuracy approx. ±3%) connected via I2C (`/dev/i2c-1`, default address `0x29`).
- **Nominal Working Distance**: **10.0 cm to 15.0 cm**. The backend applies the physical sensor-to-camera offset; the UI receives the corrected eye-to-camera distance.
- **Recording Instance**: Exactly **5 seconds per eye**.

---

## 2. Sensor & Subsystem Interfaces

### 2.1 Camera Subsystem (`CameraDevice`)

#### A. Alignment Preview Stream
- **HTTP Endpoint**: `GET /api/preview.mjpg`
- **Protocol**: `multipart/x-mixed-replace; boundary=frame`
- **Format**: Continuous stream of JPEG frames (`image/jpeg`).
- **Resolution**: 640 x 480 pixels.
- **Preview Frame Rate**: ~10–15 fps *(Unconfirmed assumption for the owner; balance CPU usage on Pi 4 with smooth alignment)*.
- **Latency Requirement**: Low latency to allow the operator to center the pupil on the crosshair.
- **Hardware Integration Target**:
  - Implemented using Raspberry Pi OS `libcamera` / `Picamera2` streaming from the Camera Module 3 NoIR.

#### B. 5-Second Recording Capture
- **HTTP Endpoint**: `POST /api/sessions/<id>/record` followed by `GET /api/sessions/<id>/record/stream?eye=OD`
- **Duration**: Exactly 5.0 seconds as specified by the manuscript.
- **Illumination**: Constant or continuous illumination from the single 850 nm IR LED during the capture window.
- **Frame Handling**: Frames captured during the 5-second window are passed to the quality filter and inference pipeline. *(Note: Exact capture frame count is an unconfirmed assumption for the owner / ML team)*.

#### C. Pre-Session Check
- **HTTP Endpoint**: `POST /api/precheck`
- **Specification (Brief §3)**: 5-second test capture verifying:
  1. Pupil crescent is visible.
  2. VL53L0X ToF reports plausible values (10.0 to 15.0 cm range).
  3. Image brightness is in the calibrated range (mean pupil intensity 128 to 200 on 8-bit grayscale).
- **Output**:
  ```json
  {
    "crescent_frame_url": "/media/precheck_crescent.jpg",
    "tof_ok": true,
    "brightness_ok": true,
    "brightness_mean": 154
  }
  ```

---

### 2.2 Time-of-Flight Distance Interface (`DistanceSensor`)

- **HTTP Endpoint**: `GET /api/distance`
- **Protocol**: Server-Sent Events (`text/event-stream`).
- **Physical Sensor**: STMicroelectronics VL53L0X over I2C (`0x29`).
- **Distance Range & States**:
  - Distance $< 10.0\text{ cm}$: `state: "too_close"`
  - $10.0\text{ cm} \le \text{Distance} \le 15.0\text{ cm}$: `state: "ok"`
  - Distance $> 15.0\text{ cm}$: `state: "too_far"`
  - Signal error, out-of-range, or reading failure: `state: "invalid"`
- **Streaming Frequency**: ~5 Hz *(Unconfirmed assumption for the owner — 200 ms polling interval recommended for responsive UI feedback without saturating the I2C bus)*.
- **Event Contract**:
  ```json
  data: {
    "cm": 12.8,
    "valid": true,
    "state": "ok",
    "ts": 1714500000.123
  }
  ```

---

### 2.3 Refraction Inference & Processing Pipeline

Following recording completion, the backend executes frame quality filtering and crescent feature extraction.

- **HTTP Endpoint**: `GET /api/sessions/<id>/events`
- **Protocol**: Server-Sent Events (`text/event-stream`).
- **Pipeline Stages**:
  - `extracting`: Extracting frames from the 5-second capture.
  - `quality_check`: Dropping frames with no detectable pupil or motion blur.
  - `feature_calc`: Measuring pupil crescent slope/width features under 850 nm illumination.
  - `inferring`: Estimating sphere and cylinder refractive error.
  - `saving`: Finalizing database record.
  - `complete`: Final pipeline signal.
- **Model Output Contract (Per Eye)**:
  - If valid frames threshold is met:
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
  - If valid frames threshold fails:
    ```json
    {
      "status": "retake_needed",
      "frames_used": 4,
      "frames_total": 110,
      "error_reason": "few_valid_frames"
    }
    ```
    *(Permitted `error_reason` keys: `few_valid_frames`, `blink`, `motion_blur`, `reflection`)*
    *(Note: The threshold of fewer than 10 valid frames triggering Retake is an unconfirmed assumption for the owner — see Brief §18 Q4)*.

- **Clinical Calculation Contract**:
  - Spherical Equivalent ($SE$) must be computed strictly via `app.clinical.compute_se(sphere_D, cylinder_D)`:
    $$SE = \text{round}\left(\text{sphere} + \frac{\text{cylinder}}{2}, 2\right)$$
  - Referral rule: Binary trigger if **either** eye has $|SE| > 0.50\text{ D}$ ($SE \le -0.50\text{ D}$ or $SE \ge +0.50\text{ D}$).

---

## 3. What Remains Untested on Real Hardware

Because software development and end-to-end verification have been conducted using the mock hardware simulator, the following physical characteristics remain untested on the actual Raspberry Pi 4 assembly:

1. **Pi Camera Module 3 NoIR Latency and Frame Rates**:
   - Camera initialization latency and whether `Picamera2` can simultaneously serve low-latency MJPEG preview and execute uncompressed 5-second capture bursts without frame dropping.
2. **VL53L0X I2C Driver Reliability**:
   - Continuous 5 Hz ranging on the Raspberry Pi 4 I2C bus (`/dev/i2c-1`) and recovery behavior if the VL53L0X sensor encounters an I2C timeout.
3. **850 nm LED Exposure & Contrast**:
   - Optimal exposure time and gain settings on the Camera Module 3 NoIR to ensure the photorefraction crescent is in the calibrated range (mean pupil intensity 128 to 200 on 8-bit grayscale) under actual room lighting.
4. **Pi 4 CPU Load & Thermal Behavior**:
   - Total CPU utilization and core temperature on the Raspberry Pi 4 when concurrently running Gunicorn (threaded HTTP server), MJPEG preview encoding, and inference feature extraction.
