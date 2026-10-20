# E-Eye Photorefractor Operator Web Interface

An offline-first, mobile-responsive operator web interface for the E-Eye portable eccentric photorefractor, designed for rapid community vision screening in rural health units (RHUs) and barangay health stations in the Philippines.

---

## Key Highlights & Architectural Guardrails

- **Zero External Runtime Requests**: Operates 100% offline. Zero CDNs, Google Fonts, external analytics, or remote scripts. The Inter variable font is self-hosted (`/static/fonts/`), SVG icons are bundled in an inline sprite, and all UI copy is localized locally (`en.json` and `fil.json`).
- **Clinical Math Precision**: Spherical Equivalent ($SE = \text{sphere} + \frac{\text{cylinder}}{2}$) is computed strictly in Python `Decimal` with half-up rounding to 0.01 D (`app/clinical.py`). The referral threshold triggers if either eye is outside $[-0.50, +0.50]\text{ D}$.
- **Persistent Concurrency Architecture**: Uses threaded serving (`deploy/gunicorn.conf.py`) to handle long-lived Server-Sent Events (SSE: `/api/distance`, `/api/sessions/<id>/events`) and MJPEG video streaming (`/api/preview.mjpg`) concurrently without starving standard HTTP REST requests.
- **Responsive Layout**: Validated across viewports from 320 px (iPhone SE / compact smartphones) up to 1440 px desktop monitors with 0 horizontal page overflow (`scrollX == 0`).
- **Zero Inline Styles**: All templates maintain 0 inline `style=` attributes across the entire application shell.

---

## Repository Structure

```
├── app/
│   ├── app.py                # Application factory, web routes, context processors
│   ├── api.py                # REST API, SSE streaming endpoints, session management
│   ├── clinical.py           # Spherical Equivalent math, condition classification, referral logic
│   ├── config.py             # Hardware parameters, site settings, calibration dates
│   ├── store.py              # SQLite storage layer with WAL mode
│   ├── mock/
│   │   ├── fixtures.py       # Deterministic clinical fixtures (refer, no_refer, retake)
│   │   └── generator.py      # Mock ToF distance events and MJPEG frame generator
│   ├── static/
│   │   ├── css/app.css       # Complete UI stylesheet, print stylesheet (@media print)
│   │   ├── fonts/            # Self-hosted Inter Latin variable font
│   │   ├── icons/sprite.svg  # Consolidated SVG icon sprite
│   │   ├── i18n/             # en.json and fil.json localization dictionaries
│   │   └── js/               # Frontend controllers (api.js, i18n.js, record.js, history.js)
│   └── templates/            # Jinja2 templates (0 inline styles)
├── deploy/
│   ├── gunicorn.conf.py      # Production threaded Gunicorn configuration
│   ├── eeye.service          # Systemd unit file for Raspberry Pi OS
│   └── HOTSPOT.md            # Wi-Fi Access Point setup guide (192.168.4.1)
├── docs/
│   ├── HARDWARE_SEAM.md      # Camera, ToF, and ML inference hardware integration contract
│   ├── contrast_audit_raw.json # Raw computed element-level color contrast audit data
│   ├── phase1_1/ ... phase6/ # Viewport screenshots and print-media artifacts
├── tests/                    # Pytest and Playwright automated end-to-end suite
├── requirements.txt          # Pinned production runtime dependencies
└── requirements-dev.txt      # Pinned development and testing dependencies
```

---

## 1. Windows Setup & Run (Mock Mode)

In Windows development environments, the application runs with simulated Time-of-Flight distance sensor readings and mock camera preview streams (`MOCK_MODE=1` default).

### Prerequisites
- Python 3.11+
- Git

### Quickstart

1. **Clone repository**:
   ```powershell
   git clone https://github.com/Kent0625/E-EYE_UI.git
   cd E-EYE_UI
   ```

2. **Create and activate a virtual environment**:
   ```powershell
   python -m venv .venv
   .\.venv\Scripts\activate
   ```

3. **Install dependencies**:
   ```powershell
   pip install -r requirements.txt
   pip install -r requirements-dev.txt
   playwright install chromium
   ```

4. **Run development server**:
   ```powershell
   python -m app.app
   ```
   Open your browser to `http://127.0.0.1:5000`.

5. **Run automated test suite**:
   ```powershell
   pytest
   ```

---

## 2. Raspberry Pi OS Setup & Deployment

When deploying to physical Raspberry Pi hardware (Raspberry Pi 4 Model B or Raspberry Pi 5 running Raspberry Pi OS 64-bit):

### Prerequisites
```bash
sudo apt update
sudo apt install -y python3-venv python3-pip git libcamera-dev
```

### 1. Setup Application Directory
```bash
cd /home/pi
git clone https://github.com/Kent0625/E-EYE_UI.git
cd E-EYE_UI
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure Wi-Fi Hotspot (`192.168.4.1`)
Follow the step-by-step instructions in [`deploy/HOTSPOT.md`](deploy/HOTSPOT.md) to enable the Wi-Fi Access Point `E-Eye-Refractor`.

### 3. Install & Start Systemd Service
```bash
sudo cp deploy/eeye.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable eeye.service
sudo systemctl start eeye.service
```

### 4. Check Service Status & Logs
```bash
sudo systemctl status eeye.service
journalctl -u eeye.service -f
```

---

## 3. Hardware Integration Seam

Physical sensors and computer vision pipelines interface with the web service via the seams documented in [`docs/HARDWARE_SEAM.md`](docs/HARDWARE_SEAM.md):
- **Camera Seam**: MJPEG streaming at `GET /api/preview.mjpg` via `libcamera` / `Picamera2` and high-speed burst capture on `POST /api/sessions/<id>/record`.
- **ToF Sensor Seam**: I2C distance measurement stream at `GET /api/distance` using ST VL53L1X.
- **Inference Seam**: Frame feature extraction and crescent analysis computing refractive error.

---

## 4. Verification & Automated Test Suite

The test suite covers unit, integration, accessibility, and end-to-end browser workflows:
- **Clinical Math**: Precision Decimal rounding, referral boundary tests ($-0.504$, $-0.505$, $+0.505$ D), cylinder independence.
- **Accessibility & Contrast**: 0 zero-contrast failures across 1,450+ audited elements, full keyboard navigation, ARIA live regions.
- **Responsive Overflow**: Viewport testing at 320, 390, 768, 1024, and 1440 px asserting `scrollX == 0`.
- **Concurrency & Memory**: Proves 3 concurrent active streams (SSE + MJPEG) do not block REST endpoints, maintaining < 150 MB memory RSS.
- **Security**: Formula injection escaping on CSV export (`=`, `+`, `-`, `@`), HTML escaping on participant codes, and input range validation on ground-truth entry.
