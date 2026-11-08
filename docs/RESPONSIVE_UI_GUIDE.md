# Testing the interface without the Raspberry Pi

This version refines the existing E-Eye interface for phone, tablet and laptop. It preserves the real capture/storage code and uses a separate, visibly labelled demo database for local preview. The Pi does not need to be connected for interface tests.

## Open the laptop preview

Run `scripts/start-ui-preview.ps1` from PowerShell. It uses the project Python environment, or the existing sibling integration environment. To choose another environment, pass `-Python C:\path\to\python.exe`. Open `http://127.0.0.1:5080` on this laptop. The launcher runs its helper hidden, records its process ID and logs under `output/ui-preview`, and stores demo records there. To stop it, stop the process ID recorded in `output/ui-preview/server.pid` after checking that it is the preview process.

The default launcher listens on the laptop's local network so a phone can preview the same screens. Join the same Wi-Fi, then use `http://LAPTOP-IP:5080` in the browser or the E-Eye APK's Connection panel. Use `-LocalOnly` to restrict the preview to this laptop. All displayed results are demo fixtures; no camera, ToF sensor or prediction model is running. A local-network connection may need Windows firewall access if the phone cannot open it.

If the built APK is present at `output/eeye-operator-debug.apk`, the preview also serves it at `http://LAPTOP-IP:5080/demo/operator.apk`. Download this on the phone to install/update the test app, then connect it to the laptop preview address. It is not a Play Store release.

## What changed

- Small-phone pages keep disabled-button explanations and the MOCK DATA label visible. Short screens let the Record button scroll with the page instead of covering distance information.
- Eye results wrap to fit narrow tablet windows; phone keyboard-sized views keep form actions reachable. Laptop navigation remains a side rail; phones retain bottom navigation.
- The processing screen shows backend stage states, elapsed processing time, unavailable stages and the actual failure reason. Rechecking a disconnected job observes the existing capture; it does not start another recording. Browser Back restoration reconnects the status stream.
- Five-second recording is unchanged. The manuscript and UI brief specify the recording interval, not a guaranteed processing deadline. The timer measures processing separately. Interrupted jobs without a recorded end time show unknown timing rather than counting server downtime.
- Android 0.3.0/code 3 collapses connection settings after a successful page load and exposes them again on connection failure. Connection and Open saved files remain accessible. Buttons can grow with system text size.

## Try the flow

1. Confirm MOCK DATA appears. Start a new test screening.
2. Check that Continue stays disabled until both consent checkboxes are checked.
3. Follow right-eye then left-eye recording. The preview, sensor readings and result are simulated in this mode.
4. Review receipt and storage controls on a phone-sized and laptop-sized window. Automatic receipt-reading limitations from the hardware test are not claimed fixed by this layout update.
5. Disconnect a test processing stream: the recovery panel should offer Check capture again and Open saved record.

## Verification and limits

`python -m scripts.check_responsive_ui` exercises 320, 390, 768, 1024 and 1440 px widths, landscape, keyboard-sized views, reduced motion, consent gating, real event rendering, connection recovery, retake and next-eye routing. `tests/test_processing_events.py` checks terminal timestamps and the real SSE endpoint without hardware. Existing receipt/storage browser checks and Java archive verification remain applicable.

Browser screenshots represent the shared web interface, not native Android screenshots. The APK builds and its signature is verified, but physical Android font scale, keyboard/insets and hotspot behavior need device testing. These web changes must be deployed to the Pi when it is connected; installing the new APK alone does not replace the Pi's pages. No live capture-speed or prescription accuracy claim is made.
