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
if systemctl is-active --quiet eeye.service; then systemctl stop eeye.service; fi
snapshot="/var/lib/eeye-snapshots/$(date +%Y%m%d-%H%M%S)"
install -d -m 700 "$snapshot"
cp -a /var/lib/eeye "$snapshot/data"
if [ -f /etc/eeye/device.env ]; then cp -a /etc/eeye/device.env "$snapshot/device.env"; fi
if [ -e /opt/eeye/current ]; then
 readlink -f /opt/eeye/current > /opt/eeye/previous-release
fi
ln -sfn "$release" /opt/eeye/current.next
mv -Tf /opt/eeye/current.next /opt/eeye/current
install -m 644 "$release/deploy/eeye.service" /etc/systemd/system/eeye.service
systemctl daemon-reload
systemctl enable --now eeye.service
systemctl restart eeye.service
systemctl is-active eeye.service
