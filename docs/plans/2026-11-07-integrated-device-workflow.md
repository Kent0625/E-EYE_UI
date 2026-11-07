# E-Eye integrated device workflow

Approved by the owner on 2026-11-07: execute the backup, real capture pipeline, managed server, app access, and receipt/ground-truth integration. Windows is the backup destination. The existing E-Eye interface is the visual authority.

## Architecture

The Pi owns capture jobs, recordings, sensor timestamps, session records and predictions. Phone camera receipt capture and local OCR feed an operator-confirmed reference measurement into the same session. Device results and reference measurements remain independent. A missing regression model is reported explicitly; a pupil segmentation model cannot produce refractive predictions. The existing laptop hotspot connection remains available during deployment. Android access uses a local-network app shell or browser with camera-file-input fallback.

## Execution and verification

1. Create a dated Windows backup outside Git. Archive home, configuration, boot partition, package inventory, services and network configuration; also stream a root filesystem recovery archive. Check hashes, inspect archive members and restore representative project files into a separate verification folder. Record that live file backups are not a tested cold SD image. Never overwrite the source setup.
2. Add receipt upload, session ownership checks, bounded image validation, OCR draft values, operator confirmation and audit history. Confirmed values and raw readings are exported alongside device values. Tests cover malformed files, wrong session, missing confirmation, atomic writes, signs/eye mapping and restart persistence.
3. Add a single hardware controller, synchronized capture jobs, five-second capture, distance gating, raw frames and metadata, ten-frame selection and honest model availability. Persist capture status independently of browser SSE. Tests cover duplicate triggers, disconnects, sensor faults and absent model. Preserve existing scripts and calibration.
4. Connect hardware API routes, actual processing events, result states, settings and home health. Retain clearly labelled mock mode for development only. Add app manifest and native Android camera/file support if a build toolchain is obtainable. Browser fallback remains usable on the hotspot.
5. Deploy to a separate release directory only after verified backup. Configure one Gunicorn worker with threads, systemd restart, persistent data outside releases, explicit real mode, and rollback instructions. Keep current network connectivity; configure a fallback Pi hotspot only when it can be tested without losing the recovery route.
6. Run targeted Python tests, receipt parser/OCR checks, browser capture/receipt/session tests and desktop/mobile inspection. Request independent spec and code review, fix material findings, then merge the reviewed code to the original workspace. Report actual deployment and backup status separately from local tests.

## Recovery

Each release has a versioned directory. Switching the current symlink back restores application code; database/media stay outside the release. Before any schema change, snapshot the database with SQLite backup and copy media. Windows keeps the initial baseline and subsequent dated backups. A cold SD image requires an offline card reader or an alternate boot device and remains a documented recovery step until physically tested.

## Known dependencies

- Pi must be reachable at 192.168.137.106 before backup or live tests.
- A trained sphere/cylinder model and its preprocessing contract are required for prediction. Capture and ground-truth collection remain useful without that model.
- Google Play publication requires the owner's developer account, signing ownership and listing review; a local app build is a separate deliverable.
