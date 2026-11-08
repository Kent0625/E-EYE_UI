# Estimated distance fallback implementation plan

Goal: implement the owner's requested constant 12.50 cm when ToF is unavailable, without calling it a measurement.

Design: an explicitly enabled device setting permits unavailable sensor startup and supplies estimated samples while keeping the real camera/LED error gates. Real valid sensor readings take priority, including out-of-range readings. Retry a missing sensor periodically. Estimated samples do not claim measured stability. Capture metadata, results and the UI identify estimated distance. Disabling the setting restores the strict sensor requirement.

1. Add failing hardware tests for missing sensor startup, read failures, measured recovery/out-of-range readings and camera failures.
2. Add minimal fallback to `app/hardware.py`, and preserve distance provenance in frames.
3. Test and update `app/capture.py` to permit explicitly estimated captures, retain provenance and avoid declaring a ToF precheck pass.
4. Update recording/home/result wording to identify estimated distance and manual positioning.
5. Run hardware/capture/storage tests and browser checks. Prepare snapshot-backed installation and run the isolated rollback fixture on the Pi before activation.
6. Deploy only when reachable. Phone installation and participant positioning require the owner; do not claim these physical actions were performed remotely.
