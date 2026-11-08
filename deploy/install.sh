#!/bin/bash
set -euo pipefail
if [ "$EUID" -ne 0 ]; then echo 'Run with sudo.' >&2; exit 1; fi
release=$(realpath "${1:?Pass the extracted release directory}")
case "$release" in /opt/eeye/releases/*) ;; *) echo 'Release must be below /opt/eeye/releases.' >&2; exit 1;; esac
test -f "$release/app/app.py"
install -d -o admin -g admin -m 700 /var/lib/eeye /var/lib/eeye/receipts /var/lib/eeye/captures
install -d -m 755 /etc/eeye /opt/eeye
if [ ! -f /etc/eeye/device.env ]; then
 install -m 600 -o admin -g admin "$release/deploy/device.env.example" /etc/eeye/device.env
fi
python3 -m venv --system-site-packages "$release/.venv"
"$release/.venv/bin/pip" install -r "$release/requirements.txt"
if ! "$release/.venv/bin/python" -c 'import board,busio,adafruit_vl53l0x'; then
 "$release/.venv/bin/pip" install Adafruit-Blinka adafruit-circuitpython-vl53l0x
fi
"$release/.venv/bin/python" -c 'import picamera2,cv2,gpiozero,board,busio,adafruit_vl53l0x'
"$release/.venv/bin/python" -c 'import sys; sys.path.insert(0,sys.argv[1]); from eeye_storage import verify_archive' "$release"
install -m 644 -o root -g root "$release/deploy/eeye-shutdown.service" /etc/systemd/system/eeye-shutdown.service
install -d -m 755 /etc/polkit-1/rules.d
install -m 644 -o root -g root "$release/deploy/49-eeye-shutdown.rules" /etc/polkit-1/rules.d/49-eeye-shutdown.rules
bash "$release/deploy/activate.sh" "$release"
