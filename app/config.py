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

# Device metadata defaults
DEVICE_NAME = os.environ.get("EEYE_DEVICE_NAME", "E-EYE-PROTOTYPE-01")
DEVICE_SSID = os.environ.get("EEYE_SSID", "E-Eye-Field-01")
DEVICE_IP = os.environ.get("EEYE_IP", "192.168.4.1")
SOFTWARE_VERSION = "v1.0.0"
