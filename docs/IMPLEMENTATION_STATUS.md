# Integration verification status

Local verification on 2026-11-08: 37 targeted Python tests passed. The browser test passed actual offline OCR for both eyes from an explicitly synthetic receipt, explicit confirmation, original receipt linkage, audit history, reload persistence, capture preservation, desktop/mobile layout, and zero external requests or JavaScript errors. Python compilation and Git whitespace checks passed.

The Android testing APK is in `output/eeye-operator-debug.apk`. Its SHA-256 is `4ad1c2c151a54e73cee2a558123cb4b0964c2819edce65c35bcbc2f5b35d4173`. It was built and its signatures verified; physical phone camera and hotspot operation remain untested. It is not published to Google Play.

The Windows project/configuration backup is verified at `C:\Users\ASUS\Documents\E-Eye Backups\20261107-175234\project-config.tar.gz`, with checksum and sample restoration recorded in `project-manifest.json`. The complete root archive exists on the Pi; its Windows transfer is incomplete (1,268,776,960 bytes in the resumable partial at this checkpoint). Do not treat either `.partial` file as a usable backup. Resume using `scripts/pi_access.py recover-root` with that backup directory when the Pi reconnects. Success creates `recovery-manifest.json`. No cold SD-card image has been made.

The service was installed and reported active in real mode. The first hardware health check found unsupported PWM on GPIO17. The local correction uses the original full-on LED setting; its final transfer/service verification was interrupted by the connection loss. Recheck the deployed hardware file and `/etc/eeye/device.env` before testing. Live camera, distance stability, recording duration, restart/recovery and physical receipt capture remain to be verified.

A pupil-segmentation model is available. A trained sphere/cylinder refraction model and validated preprocessing contract have not been located. The application explicitly reports predictions unavailable and retains captures and ground truth for collection; it must not claim screening predictions are complete.

The integration branch is `codex/pi-integrated-workflow` in the sibling `capstone-integration` worktree. It has not been merged into the original workspace. The original scripts on the Pi and the original workspace's unrelated files remain available.
