# E-Eye storage library

This Python 3.11+ package uses the standard library. It can create manifest-first archives, verify a saved archive by reading every entry from disk, and receive a session from a Pi. It does not import Flask, camera drivers, or clinical logic. The Flask/SQLite integration lives in `app/transfers.py`.

```powershell
python -m pip install .
python -m eeye_storage receive --url http://192.168.137.106:5000 --session SESSION_ID --destination C:\E-Eye\Sessions --device-label "Research laptop"
```

The destination folder is chosen by the person running the command. Saving and verifying does not remove the Pi originals. Add `--release` only when you intend to remove the exported capture/receipt files after verification. Keep another backup of important sessions. Acknowledging that one verified copy exists is not proof of a second backup.

The receiver closes and reopens the local file, verifies its manifest against the Pi's advertised SHA-256, then verifies every ZIP member's name, byte count, and SHA-256. It sends acknowledgement only after that check. Partial files and pending transfer metadata permit an interrupted download to retry with the same transfer; rerun the same command and destination. If the session changed, the Pi rejects release and retains its originals. Missing/revoked Android storage permission and failed phone writes are handled by the Android receiver; an API token does not grant filesystem permission.

```python
from eeye_storage import verify_archive
with open("session.zip", "rb") as saved:
    manifest = verify_archive(saved, expected_manifest_sha256)
print(manifest["participant_code"])
```

The `transfer-manifest.json` entry is first and bounded to 1 MiB. The manifest contains a random per-transfer acknowledgement capability. Treat the archive as private research data; never publish it. `files` describes every other entry exactly once. The API retains original files until an explicit verified release. After release, the Pi retains compact session/audit/location indexes and the receiving device owns the original files. The Pi cannot browse a disconnected phone; open its saved ZIP on that phone or restore a copy from your backup.

The API uses additive SQLite tables. File release first records a recoverable state, moves only recorded unchanged sources into private quarantine, commits location indexes, and removes the private transfer ZIP/quarantine payload. Startup restores originals from interrupted pre-commit releases. Session deletion removes associated private transfer records/files inside the same database transaction through the provided cleanup helpers.

Whole-ZIP SHA-256 and byte count are also checked, including the ZIP index/trailer. Saving only correct local entries with a missing ZIP trailer is not accepted. Earlier prepared Pi archives become superseded after a verified release so redundant staging copies do not fill the Pi. Local user archives are never deleted by this cleanup.

If a session gains a retake or receipt after an earlier offload, the next archive includes the new local files plus `metadata/external-archives.json` references to earlier verified archives. Keep those earlier files on their saved devices or backups; the new archive does not pretend to contain files that have already left the Pi. Existing saved-location indexes remain attached to their original archive. A changed receipt/reference after preparation requires a fresh snapshot; the receiver automatically prepares one on retry while preserving earlier local ZIPs.
