#!/bin/bash
set -Eeuo pipefail

if [ -n "${EEYE_TEST_ROOT:-}" ]; then
  deploy_root=$(realpath -e "$EEYE_TEST_ROOT")
  case "$deploy_root" in /var/tmp/eeye-rollback-fixture-*) ;; *) echo 'Invalid isolated test root.' >&2; exit 2;; esac
  data_dir="$deploy_root/data"
  snapshots_dir="$deploy_root/snapshots"
  env_file="$deploy_root/device.env"
  unit_file="$deploy_root/eeye.service"
else
  if [ "$EUID" -ne 0 ]; then echo 'Run deployment with sudo.' >&2; exit 2; fi
  deploy_root=/opt/eeye
  data_dir=/var/lib/eeye
  snapshots_dir=/var/lib/eeye-snapshots
  env_file=/etc/eeye/device.env
  unit_file=/etc/systemd/system/eeye.service
fi

service_control() {
  if [ -n "${EEYE_TEST_ROOT:-}" ]; then "$deploy_root/bin/systemctl" "$@"; else systemctl "$@"; fi
}

checked_release() {
  local target
  target=$(realpath -e "$1")
  case "$target" in "$deploy_root"/releases/*) ;; *) echo 'Release is outside the deployment directory.' >&2; return 2;; esac
  test -f "$target/app/app.py"
  test -x "$target/.venv/bin/gunicorn"
  printf '%s\n' "$target"
}

select_release() {
  ln -sfn "$1" "$deploy_root/current.next"
  mv -Tf "$deploy_root/current.next" "$deploy_root/current"
}

snapshot_current() {
  install -d -m 700 "$snapshots_dir" || return
  local snapshot
  snapshot=$(mktemp -d "$snapshots_dir/$(date +%Y%m%d-%H%M%S)-XXXXXX") || return
  if [ -d "$data_dir" ]; then cp -a "$data_dir" "$snapshot/data" || return; fi
  if [ -f "$env_file" ]; then cp -a "$env_file" "$snapshot/device.env" || return; fi
  if [ -f "$unit_file" ]; then cp -a "$unit_file" "$snapshot/eeye.service" || return; fi
  if [ -e "$deploy_root/current" ]; then readlink -f "$deploy_root/current" > "$snapshot/previous-release"; fi
  printf '%s\n' "$snapshot"
}

wait_ready() {
  python3 - "${EEYE_HEALTH_URL:-http://127.0.0.1:5000/api/storage/status}" "${EEYE_HEALTH_TIMEOUT:-30}" <<'PY'
import json, sys, time, urllib.request
from urllib.parse import urlsplit
url, seconds = sys.argv[1], max(1,min(60,int(sys.argv[2])))
if urlsplit(url).hostname != '127.0.0.1':
    raise SystemExit('Deployment health checks must use loopback.')
deadline=time.monotonic()+seconds
last='No response'
while time.monotonic()<deadline:
    try:
        with urllib.request.urlopen(url,timeout=2) as response:
            result=json.load(response)
        parsed=urlsplit(url)
        with urllib.request.urlopen(parsed.scheme+'://'+parsed.netloc+'/api/settings',timeout=2) as response:
            device=json.load(response)
        if result.get('ready') is True and result.get('protocol_version')==1 and device.get('mock_mode') is False:
            raise SystemExit(0)
        last='Transfer API is not ready in real device mode'
    except Exception as error:
        last=str(error)
    time.sleep(.2)
raise SystemExit('Updated service failed its health check: '+last)
PY
}
