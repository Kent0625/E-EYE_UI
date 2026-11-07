#!/bin/bash
set -Eeuo pipefail
script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
source "$script_dir/release_common.sh"
restore=''
if [ "${1:-}" = '--restore-data' ]; then
  restore=$(realpath -e "${2:?Pass a deployment snapshot}")
  case "$restore" in "$snapshots_dir"/*) ;; *) echo 'Snapshot is outside the recovery directory.' >&2; exit 2;; esac
  test -d "$restore/data"
  shift 2
fi
target="${1:-}"
if [ -z "$target" ]; then target=$(cat "$deploy_root/previous-release"); fi
target=$(checked_release "$target")
current=$(checked_release "$deploy_root/current")
service_control stop eeye.service
before=$(snapshot_current)
if [ -n "$restore" ]; then
  # Preserve the entire newer data directory before an explicitly requested data restore.
  mv "$data_dir" "$before/live-data"
  cp -a "$restore/data" "$data_dir"
  if [ -f "$restore/device.env" ]; then cp -a "$restore/device.env" "$env_file"; fi
  if [ -f "$restore/eeye.service" ]; then cp -a "$restore/eeye.service" "$unit_file"; fi
fi
select_release "$target"
printf '%s\n' "$current" > "$deploy_root/previous-release"
service_control daemon-reload
service_control start eeye.service
service_control is-active eeye.service
echo "ROLLBACK_SELECTED $target"
echo "PRE_ROLLBACK_SNAPSHOT $before"
