#!/bin/bash
set -Eeuo pipefail
script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
source "$script_dir/release_common.sh"
release=$(checked_release "${1:?Pass a prepared release directory}")
previous=''
if [ -e "$deploy_root/current" ]; then previous=$(checked_release "$deploy_root/current"); fi
if [ "$previous" = "$release" ]; then echo 'The prepared release must differ from the active release.' >&2; exit 2; fi
snapshot=''

activation_failed() {
  local code="$1"
  trap - ERR INT TERM
  set +e
  service_control stop eeye.service
  if [ -n "$previous" ]; then
    select_release "$previous"
    if [ -n "$snapshot" ] && [ -f "$snapshot/eeye.service" ]; then cp -a "$snapshot/eeye.service" "$unit_file"; fi
    if [ -n "$snapshot" ] && [ -f "$snapshot/device.env" ]; then cp -a "$snapshot/device.env" "$env_file"; fi
    service_control daemon-reload
    service_control start eeye.service
    echo "Automatic rollback selected $previous. Current session data was preserved. Snapshot: $snapshot" >&2
  else
    echo "No previous release exists. Service stopped; restore using snapshot $snapshot." >&2
  fi
  exit "$code"
}
trap 'activation_failed "$?"' ERR
trap 'activation_failed 130' INT TERM
service_control stop eeye.service
snapshot=$(trap - ERR; snapshot_current)
select_release "$release"
if [ -z "${EEYE_TEST_ROOT:-}" ]; then install -m 644 "$release/deploy/eeye.service" "$unit_file"; fi
service_control daemon-reload
service_control enable eeye.service
service_control start eeye.service
wait_ready
if [ -n "$previous" ]; then printf '%s\n' "$previous" > "$deploy_root/previous-release"; fi
printf '%s\n' "$release" > "$snapshot/activated-release"
printf '%s\n' "$snapshot" > "$deploy_root/last-update-snapshot"
trap - ERR INT TERM
echo "UPDATE_VERIFIED $release"
echo "RESTORE_SNAPSHOT $snapshot"
