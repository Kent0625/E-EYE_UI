# Saving sessions on a phone or laptop

This update keeps a temporary Pi copy until a receiving app has checked its saved archive. It does not grant the Pi access to the whole phone. Folder/file permission comes from the phone or computer's own file picker.

## Operator workflow

When the owner-enabled ToF fallback is active, the screen shows **12.50 cm — estimated, ToF unavailable**. Use a ruler or fixed guide to position the eye manually. The number is a constant, not a measurement; movement cannot be checked during estimated frames. Recordings and result pages retain this distinction. A valid real sensor reading takes priority, and real out-of-range readings still block recording. Camera or LED failures still prevent capture. Disable `EEYE_ALLOW_ESTIMATED_DISTANCE` to restore the strict sensor requirement.

1. Finish the eye capture and confirm the printed autorefractor average in the participant's result.
2. Under **Save session to a phone or computer**, give the destination a useful name, such as Research phone.
3. Choose **Prepare session archive**, then **Save to this device**. Select local storage with enough space.
4. In the updated Android app, wait for the file to be saved, reopened and checked. The app then asks whether to remove the transferred files from the Pi. Choose **Keep on Pi** if you want both copies.
5. If you choose removal, the Pi retains the participant record, confirmed values, audit and saved-device location. Large transferred captures/receipt images live in the chosen ZIP. Use **Open saved files** in the Android app or the device's Files application to open it.

A normal browser download keeps the Pi originals. A browser's completed download alone does not prove that a readable local copy exists. The Python receiver below is the verified laptop alternative. Cancelled writes, full storage, wrong checksums and connection failures do not automatically discard originals. If the response to an explicit removal request is lost, keep the local file and retry confirmation; do not assume whether removal happened.

Keep earlier archives when adding a later retake or receipt. A later archive can contain new files plus references to files already saved in earlier archives. Those references name the device and original archive identity; they do not pretend that the older files are inside the new ZIP. The Pi cannot read an archive from a disconnected phone. Make a separate Windows/USB backup of important saved sessions.

## Reusable library

`eeye_storage` is a standard-library Python package independent of Flask, camera drivers and clinical calculations. A wheel is built under `output/dist`. Its public archive functions are `ArchiveFile`, `create_archive`, and `verify_archive`; see `eeye_storage/README.md` for examples.

```powershell
python -m pip install path\to\eeye_storage-1.0.0-py3-none-any.whl
eeye-storage receive --url http://192.168.137.106:5000 --session SESSION_ID --destination C:\E-Eye\Sessions --device-label "Research laptop"
```

That command keeps the Pi originals. Add `--release` only when you intend to remove the exported originals after verification. Rerun with the same destination after an interruption; it resumes a compatible preparation or safely prepares a fresh snapshot after record changes. Previously saved local ZIPs are retained.

The Flask adapter is `app/transfers.py`. Android separates the reusable plain-Java `ArchiveVerifier` from Android document handling in `TransferReceiver`. Every receiver checks both the full ZIP's SHA-256/byte count and every manifest entry. This also detects damage to the ZIP index/trailer. API acknowledgement tokens identify one transfer; they do not grant operating-system storage permissions.

## Update fallback

`deploy/install.sh` prepares a new per-release runtime, then calls `deploy/activate.sh`. Activation stops the service, snapshots the current data/configuration, selects the new release and checks the storage API plus real device mode. If startup or health fails, it selects the previous release and starts that code while preserving current session data.

`deploy/rollback.sh` selects the previous code release and keeps current data. An explicit maintenance `--restore-data SNAPSHOT` additionally restores snapshot data after preserving the newer data directory in a separate pre-rollback snapshot. Never discard phone/laptop archives during rollback: files already moved to those devices remain there. Restoring older Pi data does not recreate files collected and offloaded after that snapshot.

The current Pi code/data/configuration baseline was copied to Windows before this change: `Documents\E-Eye Backups\pre-device-storage-20261108`. Its archive SHA-256 is `885f296662bb7e11eb8b34f5dc7a13b5102432bbfb70883a29ac1eec80df3eff`. The original full filesystem backup is also retained. Neither is a tested bootable SD-card image.
