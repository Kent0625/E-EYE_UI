import os

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(BASE_DIR, ".."))

# Running in mock mode allows local UI dev without Pi hardware
MOCK_MODE = os.environ.get("EEYE_MOCK", "1") == "1"

# Database storage path
DATABASE_PATH = os.environ.get("EEYE_DB", os.path.join(PROJECT_ROOT, "eeye.db"))

# Static media storage for pupil thumbnails and precheck frames
MEDIA_FOLDER = os.path.join(BASE_DIR, "static", "media")
os.makedirs(MEDIA_FOLDER, exist_ok=True)

import shutil

# Device metadata defaults
DEVICE_NAME = os.environ.get("EEYE_DEVICE_NAME", "E-EYE-PROTOTYPE-01")
DEVICE_SSID = os.environ.get("EEYE_SSID", "E-Eye-Field-01")
DEVICE_IP = os.environ.get("EEYE_IP", "192.168.4.1")
SOFTWARE_VERSION = "v1.0.0"

# Hardware calibration values (read from config/env; defaults to empty if unrecorded)
TOF_CALIBRATED_DATE = os.environ.get("EEYE_TOF_CAL_DATE", "")
LED_DRIVE_SETTING = os.environ.get("EEYE_LED_DRIVE", "")

def get_storage_free_gb():
    """Computes actual free disk space in GB using shutil.disk_usage."""
    try:
        free_bytes = shutil.disk_usage(BASE_DIR).free
        return round(free_bytes / (1024 ** 3), 1)
    except Exception:
        return 0.0

def get_storage_free_str():
    return f"{get_storage_free_gb():.1f} GB"
