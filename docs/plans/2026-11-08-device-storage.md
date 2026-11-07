# Connected-device storage and recoverable deployment

Owner approved implementation and Pi deployment on 2026-11-08, including restoration when an update fails. Preserve the receipt-summary changes and the existing E-Eye interface.

## Transfer contract

1. `POST /api/sessions/<id>/transfers` with `device_id` and `device_label` creates an immutable ZIP snapshot and returns `id`, `download_url`, `manifest_sha256`, and transfer state. Large source files remain on the Pi. Reject active captures, stale/missing sessions, symlinks, arbitrary paths, and insufficient temporary storage.
2. ZIP includes `transfer-manifest.json` with `schema_version=1`, `transfer_id`, `session_id`, `participant_code`, `device_id`, `device_label`, random `ack_token`, and `files=[{path, sha256, bytes}]`. Include session metadata, audit/source reference information, original receipt images, capture manifests and frame/quality files. Serve `X-EEye-Manifest-SHA256` and a safe attachment name. Every other ZIP entry must occur exactly once in the manifest. Use private temporary storage outside the release.
3. Receiving app chooses a local destination, saves, closes and reopens it, verifies the manifest hash and every entry's bytes/hash. Cancelling, missing permissions, insufficient local storage, corrupted/truncated files and disconnects cannot acknowledge or delete Pi files.
4. `POST /api/transfers/<id>/ack` accepts `ack_token`, `manifest_sha256`, `device_id`, `verified=true`. Match the transfer and immutable snapshot. Acknowledgement alone does not delete files.
5. Explicitly confirmed `POST /api/transfers/<id>/release` with the same payload releases only unchanged exported capture and receipt files. Revalidate current session snapshot/revisions and bytes. Preserve compact session/eye/location indexes and audit data. Serialize against capture/deletion/ground-truth writes. Make retries idempotent and crash-safe; never purge unrelated paths. Show saved-device locations when large files are no longer on the Pi.
6. Browser fallback downloads only and retains Pi files because a browser download is not proof of a verified disk save. Android implements read-back verification and explicit release confirmation. A reusable Python receiver supports Windows/laptop folder saving and the same verification/acknowledgement protocol. Do not claim that an API token grants filesystem permissions or lets the Pi browse a disconnected phone.

## Code ownership and checks

- Backend/library: pure Python `eeye_storage/` core, Flask adapter `app/transfers.py`, additive schema, tests for hash mismatch, stale snapshot, cancellation/no ack, device/token mismatch, duplicate ack/release, purge races and interrupted recovery. Parent registers the blueprint and makes existing capture/receipt/UI routes understand offloaded locations. Package a minimal reusable library with examples, not an entire framework.
- Android: framework Java receiver with archive validation, existing local-origin restrictions and SAF permission, readable saved-file status, no JS bridge or broad phone storage access. Build and verify a testing APK with the existing signing identity. Physical-phone verification must be reported separately.
- Parent: result-screen transfer controls; Windows receipt/download verification; deployment scripts with pre-update code/data/config snapshot and automatic code rollback if startup/API health fails. Preserve new records during rollback and provide an explicit restoration command for maintenance use.

## Deployment gate

Inspect Pi identity/storage/service/current release and verify the existing Windows recovery manifests. Snapshot current app data/config before mutation. Deploy to a new release with a private per-release runtime; health checks include real mode and transfer API, and must not require the physically disconnected VL53L0X. Rehearse rollback to the previous working code, then reapply and verify the update. Run synthetic transfer/ack/release tests and remove only their test records. Existing clinical records and original capture scripts remain intact. Full participant capture requires repaired sensor wiring; refraction prediction still needs the trained model/input contract.
