# Shut down from Settings

Once installed on the Raspberry Pi, open E-Eye **Settings → Device power → Shut down Raspberry Pi**. Finish recordings and downloads first. Read the confirmation, then choose Shut down Raspberry Pi. Cancel or Escape closes the dialog without sending a shutdown request.

The Pi performs an operating-system shutdown. The app disconnects afterward. Keep the power supply connected until shutdown finishes. To use the Pi again, reconnect its power supply. This control cannot turn an already powered-off Pi back on.

The button is disabled on the disconnected laptop interface, in developer simulation, and on a Pi without the installed shutdown helper. A recording or archive preparation in progress blocks the request. A confirmed accepted request keeps new capture jobs blocked while shutdown is pending. This does not erase session records or saved phone/Windows files.

## Installation

Install the full release with `deploy/install.sh`; an APK update alone cannot install this server-side feature. The installer places the root-owned `eeye-shutdown.service` and `49-eeye-shutdown.rules`, then activates the release. The main web service stays unprivileged with NoNewPrivileges. The rule permits only admin starting that exact service, not arbitrary service management. The helper is not enabled at boot; it runs only when requested. Its five-second delay gives the HTTP response time to reach the app before OS shutdown starts.

The API requires a same-origin, explicitly confirmed POST, checks capability and holds the shared capture/storage lock. The command and service name are fixed and accept no user-supplied shell text. An unconfirmed timeout keeps capture paused and allows the same fixed shutdown request to be retried. An unconfirmed network response is not proof that the Pi stayed on.

## Verification

Backend tests cover confirmation, origin, busy-device rejection, idempotence, fixed command, failure handling and disconnected/simulation rejection. The policy test evaluates allowed/denied user, unit, verb and action combinations. The browser test intercepts all shutdown responses and checks phone/laptop confirmation, keyboard focus, Cancel/Escape, one confirmed request and busy-error recovery. No real shutdown is executed by these tests.

Installed on the Pi at `172.24.183.58` in release `20261108-142150-ui-shutdown`. Root unit validation, admin action authorization, API availability and the real Settings confirmation/Cancel path passed. No actual poweroff was requested. A fresh verified Windows backup and previous-code activation snapshot are retained; see `IMPLEMENTATION_STATUS.md`.
