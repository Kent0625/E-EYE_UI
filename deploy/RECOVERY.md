# Backup and recovery

The initial backup destination is `C:\Users\ASUS\Documents\E-Eye Backups\20261107-175234`.
`project-config.tar.gz` was checked against the remote SHA-256 and its 12,554 archive members were read successfully. `restore-check` contains two working scripts whose hashes matched their Pi originals. It contains home directories, device configuration and boot firmware. It is private and is outside Git.

The first root filesystem transfer disconnected. A `.partial` file is not a verified backup. `scripts/pi_access.py recover-root <backup-folder>` creates a persistent archive on the Pi and resumes its Windows download. Only `recovery-manifest.json` indicates successful checksum and archive verification. Keep the project archive even if the filesystem archive is incomplete.

These are live file backups. A bootable SD image has not been made or restore-tested. To recover from SD failure, first install compatible Raspberry Pi OS on a spare card, then restore the required project/configuration files and reinstall the package inventory from `inventory.json`. Review network configuration before restoring it. For exact disk recovery, shut the Pi down and image the SD card using a Windows card reader; verify a second card boots from that image. Do not write an image onto the only working card.

## Release rollback

Code releases live in `/opt/eeye/releases`; `/opt/eeye/current` selects the active release. Data stays in `/var/lib/eeye` and is not overwritten by release installation. The original `/home/admin/eeye` and scripts remain available. After a verified backup, install an extracted release with `sudo bash deploy/install.sh /opt/eeye/releases/<version>`.

To roll back an installed release, stop `eeye.service`, inspect `/opt/eeye/previous-release`, switch the current symlink to that exact verified release, then start the service. Restore a SQLite snapshot only while the service is stopped and after preserving newer records. Do not copy a live SQLite file without its WAL; use Python's SQLite backup API.

The connected-device storage update adds `activate.sh` and `rollback.sh`. Activation snapshots stopped-service data/config and automatically selects the previous code if the new storage API is not ready in real mode. To select the prior code while keeping current records, run `sudo bash /opt/eeye/current/deploy/rollback.sh`. The script prints a pre-rollback snapshot path. For an explicitly chosen data restoration, pass `--restore-data /var/lib/eeye-snapshots/<exact-snapshot>` and optionally an exact release path. Newer data is moved into the pre-rollback snapshot before restoration; it is not erased. Files previously offloaded to a phone/laptop stay on that device and must be retained there.

A fresh baseline before this update is on Windows in `Documents\E-Eye Backups\pre-device-storage-20261108`, including current app/data/config/unit and release pointers. SHA-256 `885f296662bb7e11eb8b34f5dc7a13b5102432bbfb70883a29ac1eec80df3eff` matches the Pi archive. The original full backup remains available separately.

Keep the laptop hotspot connection during initial deployment. No hotspot change has been applied by these scripts. A Pi-hosted hotspot needs a separate connection test and recovery route before activation.

The refraction prediction model is not supplied. The pipeline stores real captures and confirmed receipt ground truth but does not manufacture sphere, cylinder, or a no-referral result. Quality filtering also needs the verified pupil model and eye crop. Google Play publication and a signed Android release remain separate deployment steps.
