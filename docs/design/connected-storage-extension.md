# Connected storage extension

Decision: ship the result-screen storage controls within the existing E-Eye interface.

The controls preserve the incumbent white grouped panels, pale page background, teal primary actions, outlined secondary actions, typography, rounded fields and spacing. Desktop keeps the existing result and action columns. Mobile stacks the actions and wraps the instructions without clipping the storage panel. This extension introduces no new visual tokens or unrelated layout changes.

The task sequence is explicit: name the receiving device, prepare the archive, then save it. The visible explanation distinguishes browser downloads, which keep the Pi copy, from the Android app, which checks the saved file and asks before removing transferred files. A separate instruction tells operators to keep earlier archives when adding retakes or receipts.

## Review evidence

Reviewed `.impeccable/review/desktop-storage.png` and `.impeccable/review/mobile-storage.png` on 2026-11-08 using the actual captured images. Both show the prepared-archive state. The desktop storage controls fit within their panel; mobile controls fit and remain readable above the existing bottom navigation. The captures visibly identify MOCK DATA and use TEST participant/device labels. No realistic participant information or invented clinical claims were introduced.

This is a narrow visual review of the storage controls. It does not establish physical-phone verification or Pi deployment. The hidden receipt preview awaiting an uploaded image is outside this surface's visible screenshot state.

No recapture, rebuild or visual correction is required for this reviewed state. Functional transfer and release verification is recorded separately in the storage tests and deployment notes.
