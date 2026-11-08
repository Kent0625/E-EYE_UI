# Testing the interface without the Raspberry Pi

This version refines the existing E-Eye interface for phone, tablet and laptop. The operator interface starts with empty history, connection instructions and a short capture-and-save guide. It does not create sample participants, simulated recordings or screening results. Real recording requires the Raspberry Pi.

## Open the laptop preview

Run `scripts/start-ui-preview.ps1` from PowerShell. It uses the project Python environment, or the existing sibling integration environment. To choose another environment, pass `-Python C:\path\to\python.exe`. Open `http://127.0.0.1:5080` on this laptop. The launcher runs its helper hidden, records its process ID and logs under `output/ui-preview`, and uses a separate `operator.sqlite3` database. To stop it, stop the process ID recorded in `output/ui-preview/server.pid` after checking that it is the operator-interface process.

The default launcher listens on the laptop's local network so a phone can open the same guidance screens. Join the same Wi-Fi, then use `http://LAPTOP-IP:5080` in the browser or the E-Eye APK's Connection panel. Use `-LocalOnly` to restrict the interface to this laptop. Recording and new-session creation stay blocked while disconnected. To operate the hardware, connect the app to the Pi's own address. A local-network connection may need Windows firewall access if the phone cannot open the laptop page.

If the built APK is present at `output/eeye-operator-debug.apk`, the preview also serves it at `http://LAPTOP-IP:5080/demo/operator.apk`. Download this on the phone to install/update the test app, then connect it to the laptop preview address. It is not a Play Store release.

## What changed

- Small-phone pages keep disabled-button explanations visible. Short screens let the Record button scroll with the page instead of covering distance information. No MOCK DATA label appears in the operator interface because it does not run a simulation.
- Eye results wrap to fit narrow tablet windows; phone keyboard-sized views keep form actions reachable. Laptop navigation remains a side rail; phones retain bottom navigation.
- The processing screen shows backend stage states, elapsed processing time, unavailable stages and the actual failure reason. Rechecking a disconnected job observes the existing capture; it does not start another recording. Browser Back restoration reconnects the status stream.
- Five-second recording is unchanged. The manuscript and UI brief specify the recording interval, not a guaranteed processing deadline. The timer measures processing separately. Interrupted jobs without a recorded end time show unknown timing rather than counting server downtime.
- Android 0.3.0/code 3 collapses connection settings after a successful page load and exposes them again on connection failure. Connection and Open saved files remain accessible. Buttons can grow with system text size.

## Try the flow

1. While disconnected, review the connection steps and empty History. Start screening is disabled.
2. Join the Pi's hotspot/network and enter its current address in the app. On a laptop, open the Pi address in a browser.
3. Create a participant code and confirm age and consent. Record the right eye, then the left eye.
4. Attach the receipt and confirm its printed summary values. Automatic receipt-reading limitations from the hardware test are not claimed fixed by this layout update.
5. Save and verify a complete session archive before choosing whether to remove the Pi copy.

## Verification and limits

`python -m scripts.check_operator_ui` checks the running clean operator page at phone/tablet/laptop widths. `tests/test_disconnected_operator.py` checks empty history, truthful disconnected status and blocked capture/session creation. Developer-only UI checks explicitly enable simulation in isolated databases; simulation is no longer the application default. Existing processing, receipt/storage browser checks and Java archive verification remain applicable.

Browser screenshots represent the shared web interface, not native Android screenshots. The APK builds and its signature is verified, but physical Android font scale, keyboard/insets and hotspot behavior need device testing. These web changes must be deployed to the Pi when it is connected; installing the new APK alone does not replace the Pi's pages. No live capture-speed or prescription accuracy claim is made.
