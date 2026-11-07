"""Authenticated Pi backup and deployment transport; credentials are never saved."""
import argparse
import getpass
import hashlib
import json
from pathlib import Path
import shlex
import tarfile
import time
from datetime import datetime
import paramiko


def connect(host, password=None):
    client = paramiko.SSHClient()
    client.load_host_keys(str(Path.home() / '.ssh' / 'known_hosts'))
    client.set_missing_host_key_policy(paramiko.RejectPolicy())
    password = password if password is not None else getpass.getpass('Pi password: ')
    client.connect(host, username='admin', password=password, timeout=12,
                   allow_agent=False, look_for_keys=False)
    client._eeye_password = password
    client.get_transport().set_keepalive(20)
    return client


def run(client, command):
    stdin, stdout, stderr = client.exec_command(command.replace('sudo -n ', "sudo -S -p '' "), timeout=120)
    stdout.channel.set_combine_stderr(True)
    if 'sudo -n ' in command:
        stdin.write(client._eeye_password + '\n')
        stdin.flush()
    stdin.channel.shutdown_write()
    output, error = stdout.read().decode(), stderr.read().decode()
    code = stdout.channel.recv_exit_status()
    if code:
        raise RuntimeError(f'Command failed ({code}): {error or output}')
    return output


def archive(client, destination, name, arguments):
    target = destination / (name + '.tar.gz')
    partial = target.with_suffix('.gz.partial')
    # Keep stdout binary; stderr and remote digest use a separate SSH channel.
    remote_log = '/tmp/eeye-backup-' + name + '.log'
    remote_hash = '/tmp/eeye-backup-' + name + '.sha256'
    command = ('bash -o pipefail -c ' + shlex.quote(
        f"sudo -S -p '' tar --acls --xattrs --numeric-owner {arguments} "
        f'2>{remote_log} | gzip -1 | tee >(sha256sum > {remote_hash}); '
        'status=$?; wait; exit $status'))
    stdin, stdout, stderr = client.exec_command(command)
    stdin.write(client._eeye_password + '\n')
    stdin.flush()
    stdin.channel.shutdown_write()
    digest = hashlib.sha256()
    total, last = 0, time.monotonic()
    with partial.open('wb') as handle:
        while chunk := stdout.read(1024 * 1024):
            handle.write(chunk)
            digest.update(chunk)
            total += len(chunk)
            if time.monotonic() - last >= 15:
                print(f'{name}: {total / 1024**2:.0f} MiB received', flush=True)
                last = time.monotonic()
    code = stdout.channel.recv_exit_status()
    error = stderr.read().decode()
    log = run(client, f'cat {remote_log}')
    (destination / (name + '-tar.log')).write_text(log + error, encoding='utf-8')
    if code not in (0, 1):
        raise RuntimeError(f'{name}: tar failed ({code}); partial archive retained')
    source_hash = run(client, f'cat {remote_hash}').split()[0]
    if digest.hexdigest() != source_hash:
        raise RuntimeError('Source and Windows checksums differ')
    partial.rename(target)
    count = 0
    required = set()
    with tarfile.open(target, 'r:gz') as tar:
        for member in tar:
            count += 1
            if member.name in ('home/admin/eeye/live_capture.py', 'home/admin/eeye_server.py'):
                data = tar.extractfile(member).read()
                restored = destination / 'restore-check' / Path(member.name).name
                restored.parent.mkdir(exist_ok=True)
                restored.write_bytes(data)
                remote = run(client, 'sha256sum ' + shlex.quote('/' + member.name)).split()[0]
                if hashlib.sha256(data).hexdigest() != remote:
                    raise RuntimeError(f'Restore check differs: {member.name}')
                required.add(member.name)
    if name == 'project-config' and len(required) != 2:
        raise RuntimeError('Expected working scripts missing from archive')
    print(f'VERIFIED {target.name}: {count} archive members, {total} bytes', flush=True)
    return dict(file=target.name, bytes=total, sha256=source_hash, members=count,
                tar_exit=code, warnings=log, restored_scripts=sorted(required))


def backup(client, root):
    destination = Path(root) / datetime.now().strftime('%Y%m%d-%H%M%S')
    destination.mkdir(parents=True, exist_ok=False)
    inventory = {}
    for name, command in {
        'identity': 'hostname; id; uname -a; cat /etc/os-release',
        'storage': 'lsblk -o NAME,SIZE,FSTYPE,UUID,MOUNTPOINTS; df -h; sudo -n sfdisk --dump /dev/mmcblk0',
        'packages': 'dpkg-query -W',
        'services': 'systemctl list-unit-files --no-pager; systemctl list-units --type=service --no-pager',
        'network': 'ip address; ip route; nmcli connection show',
    }.items():
        inventory[name] = run(client, command)
    (destination / 'inventory.json').write_text(json.dumps(inventory, indent=2), encoding='utf-8')
    records = []
    records.append(archive(client, destination, 'project-config',
        '-cf - -C / home etc boot/firmware'))
    records.append(archive(client, destination, 'root-filesystem',
        '--one-file-system --exclude=./proc --exclude=./sys --exclude=./dev '
        '--exclude=./run --exclude=./tmp --exclude=./mnt --exclude=./media '
        '--exclude=./swapfile --exclude=./var/swap --exclude=./lost+found -cf - -C / .'))
    manifest = dict(host='eeye', backup_type='live-file-recovery-archive',
                    cold_sd_image=False, archives=records, verified_at=datetime.now().isoformat())
    (destination / 'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    print('BACKUP_VERIFIED ' + str(destination), flush=True)


def recover_root(client, destination):
    destination = Path(destination)
    remote = '/var/tmp/eeye-recovery/root-filesystem.tar.gz'
    job = '''mkdir -p /var/tmp/eeye-recovery; chown admin:admin /var/tmp/eeye-recovery; chmod 700 /var/tmp/eeye-recovery
if [ ! -f /var/tmp/eeye-recovery/started ]; then
 touch /var/tmp/eeye-recovery/started
 nohup bash -c 'set -o pipefail; tar --acls --xattrs --numeric-owner --one-file-system --exclude=./proc --exclude=./sys --exclude=./dev --exclude=./run --exclude=./tmp --exclude=./mnt --exclude=./media --exclude=./var/tmp/eeye-recovery --exclude=./swapfile --exclude=./var/swap -cf - -C / . 2>/var/tmp/eeye-recovery/tar.log | gzip -1 > /var/tmp/eeye-recovery/root-filesystem.tar.gz; status=$?; if [ "$status" -le 1 ]; then sha256sum /var/tmp/eeye-recovery/root-filesystem.tar.gz > /var/tmp/eeye-recovery/done; else echo "$status" > /var/tmp/eeye-recovery/failed; fi' </dev/null >/var/tmp/eeye-recovery/job.log 2>&1 &
fi
'''
    run(client, 'sudo -n bash -c ' + shlex.quote(job))
    while True:
        state = run(client, 'if test -f /var/tmp/eeye-recovery/done; then cat /var/tmp/eeye-recovery/done; elif test -f /var/tmp/eeye-recovery/failed; then echo FAILED; else stat -c %s /var/tmp/eeye-recovery/root-filesystem.tar.gz; fi').strip()
        if state == 'FAILED':
            raise RuntimeError('Remote recovery archive failed; inspect /var/tmp/eeye-recovery/tar.log')
        if state and len(state.split()[0]) == 64:
            expected = state.split()[0]
            break
        print('Remote archive: ' + state + ' bytes', flush=True)
        time.sleep(20)
    run(client, 'sudo -n chown admin:admin ' + remote)
    run(client, 'chmod 600 ' + remote)
    target = destination / 'root-filesystem-resumable.tar.gz.partial'
    offset = target.stat().st_size if target.exists() else 0
    with client.open_sftp() as sftp, sftp.open(remote, 'rb') as source, target.open('ab') as output:
        source.seek(offset)
        source.prefetch(file_size=source.stat().st_size, max_concurrent_requests=32)
        while chunk := source.read(1024*1024):
            output.write(chunk)
            offset += len(chunk)
            if offset % (20*1024*1024) < 1024*1024:
                print(f'Recovery transfer: {offset//1024**2} MiB', flush=True)
    digest = hashlib.file_digest(target.open('rb'), 'sha256').hexdigest()
    if digest != expected:
        raise RuntimeError('Recovery checksum mismatch; partial retained')
    count = 0
    with tarfile.open(target, 'r:gz') as tar:
        for member in tar:
            count += 1
    final = target.with_suffix('')
    target.rename(final)
    manifest = dict(type='live-filesystem-backup', cold_sd_image=False,
        root_archive=final.name, sha256=digest, archive_members=count,
        verified_at=datetime.now().isoformat())
    (destination/'recovery-manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    print('RECOVERY_BACKUP_VERIFIED ' + str(final),flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--host', default='192.168.137.106')
    commands = parser.add_subparsers(dest='action', required=True)
    p = commands.add_parser('backup'); p.add_argument('destination')
    p = commands.add_parser('recover-root'); p.add_argument('destination')
    p = commands.add_parser('run'); p.add_argument('command')
    p = commands.add_parser('download'); p.add_argument('remote'); p.add_argument('local')
    p = commands.add_parser('upload'); p.add_argument('local'); p.add_argument('remote')
    p = commands.add_parser('deploy'); p.add_argument('verified_backup')
    args = parser.parse_args()
    client = connect(args.host)
    try:
        if args.action == 'backup':
            backup(client, args.destination)
        elif args.action == 'recover-root':
            password = client._eeye_password
            for attempt in range(6):
                try:
                    recover_root(client, args.destination)
                    break
                except (paramiko.SSHException, OSError, EOFError) as error:
                    print(f'Connection interrupted; recovery retry {attempt+1}/6: {type(error).__name__}',flush=True)
                    if attempt == 5:
                        raise
                    client.close()
                    time.sleep(10)
                    client = connect(args.host, password)
        elif args.action == 'deploy':
            baseline = json.loads((Path(args.verified_backup)/'project-manifest.json').read_text())
            archive_path = Path(args.verified_backup)/baseline['file']
            with archive_path.open('rb') as handle:
                if hashlib.file_digest(handle,'sha256').hexdigest() != baseline['sha256']:
                    raise RuntimeError('Baseline backup checksum failed; deployment stopped.')
            project = Path(__file__).resolve().parent.parent
            bundle = project/'output'/'eeye-release.tar.gz'
            with tarfile.open(bundle,'w:gz') as tar:
                for name in ('app','eeye_storage','deploy','requirements.txt','pyproject.toml'):
                    tar.add(project/name,arcname=name,filter=lambda info: None if '__pycache__' in info.name or info.name.endswith('.pyc') else info)
            with client.open_sftp() as sftp:
                sftp.put(str(bundle),'/tmp/eeye-release.tar.gz')
            release = '/opt/eeye/releases/' + datetime.now().strftime('%Y%m%d-%H%M%S-integrated')
            print(run(client, 'sudo -n mkdir -p '+release))
            print(run(client, 'sudo -n tar -xzf /tmp/eeye-release.tar.gz -C '+release))
            print(run(client, 'sudo -n bash '+release+'/deploy/install.sh '+release))
        elif args.action == 'run':
            print(run(client, args.command))
        else:
            with client.open_sftp() as sftp:
                if args.action == 'download':
                    sftp.get(args.remote, args.local)
                else:
                    sftp.put(args.local, args.remote)
    finally:
        client.close()


if __name__ == '__main__':
    main()
