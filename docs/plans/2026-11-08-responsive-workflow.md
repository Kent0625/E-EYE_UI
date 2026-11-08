# Responsive E-Eye workflow

The owner authorized an offline refinement for phone and laptop, following the manuscript and existing UI brief. Preserve the teal/light visual system and current data workflows. Do not change optical settings or prediction rules.

Reference: manuscript PDF pages 34 and 44 specify a five-second recording and pre-session check. Pages 51 and 56 describe three-to-five-second sequences. The UI brief chooses five seconds per eye and real processing events. No fixed total inference-time promise was found in the reviewed timing passages; measure elapsed time rather than inventing a deadline.

Plan:
1. Capture incumbent screens locally at phone/tablet/laptop widths in an isolated mock database. Record concrete layout and interaction problems.
2. Add failing tests for actual processing states, elapsed time, disconnected recovery and responsive access to controls.
3. Implement backend-derived processing states and a small external processing controller. Keep unavailable model/quality stages explicit. Show measured elapsed time and retry/view-record actions; never invent completion percentages.
4. Refine responsive CSS for readable small-phone layouts, landscape/keyboard use, wrapping labels, receipt fields, result actions and accessible controls. Preserve mobile bottom navigation and desktop rail.
5. Refine the Android connection controls so they consume less space and wrap for narrow/large-text devices. Build a test APK; do not claim emulator/physical-phone verification if unavailable.
6. Run functional browser checks at 320, 390, 768, 1024 and 1440 px, plus landscape, reduced motion and zoom. Inspect phone/laptop screenshots in one batched pass, fix observed defects, then confirm once.
7. Run relevant Python/browser/Java checks, package the APK and a local preview launcher. Integrate verified changes into the main Windows project. The Pi is disconnected; deployment and real capture/inference speed remain pending.
