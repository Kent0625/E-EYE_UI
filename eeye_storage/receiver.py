import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import socket
import urllib.error
import urllib.parse
import urllib.request
import uuid

from .archive import canonical_json, verify_archive


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError('The Pi redirected the transfer. Reconnect using its exact local address.')


def _origin(url):
    parsed=urllib.parse.urlsplit(url)
    if parsed.scheme not in ('http','https') or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in ('','/'):
        raise ValueError('Use the Pi origin, such as http://192.168.137.106:5000, without credentials or a path.')
    return url.rstrip('/')


def receive_session(url, session_id, destination, device_label=None, release=False, timeout=30):
    """Save, reopen, verify, acknowledge, then optionally release. Failed saves never acknowledge."""
    base=_origin(url)
    destination=Path(destination).expanduser().resolve()
    destination.mkdir(parents=True,exist_ok=True)
    identity=destination/'.eeye-device-id'
    if identity.exists():
        device_id=identity.read_text(encoding='utf-8').strip()
    else:
        device_id=uuid.uuid4().hex
        with identity.open('x',encoding='utf-8') as handle: handle.write(device_id)
        identity.chmod(0o600)
    label=device_label or socket.gethostname()
    opener=urllib.request.build_opener(NoRedirect)

    def request_json(path,body=None):
        if not path.startswith('/api/') or path.startswith('//'):
            raise ValueError('Invalid Pi API path.')
        req=urllib.request.Request(base+path,data=canonical_json(body) if body is not None else None,
            headers={'Accept':'application/json','Content-Type':'application/json','Origin':base})
        try:
            with opener.open(req,timeout=timeout) as response:
                raw=response.read(1024*1024+1)
                if len(raw)>1024*1024: raise ValueError('Pi response is too large.')
                return json.loads(raw)
        except urllib.error.HTTPError as error:
            detail=error.read(8192).decode('utf-8',errors='replace')
            raise ValueError('Pi rejected this storage operation: '+detail) from error

    request_key=hashlib.sha256((base+'\n'+session_id).encode()).hexdigest()[:24]
    pending=destination/('.eeye-pending-'+request_key+'.json')
    transfer=None
    if pending.is_file() and not pending.is_symlink():
        candidate=json.loads(pending.read_text(encoding='utf-8'))
        if candidate.get('origin')==base and candidate.get('session_id')==session_id and candidate.get('device_id')==device_id:
            transfer=candidate['transfer']
    collection='/api/sessions/'+urllib.parse.quote(session_id,safe='')+'/transfers'
    if transfer is not None:
        listed=request_json(collection).get('transfers',[])
        current=next((item for item in listed if item.get('id')==transfer.get('id')),None)
        # A completed release can be safely retried from its verified local archive.
        transfer=current if current and current.get('state')=='released' else None
    if transfer is None:
        # Preparing is idempotent for unchanged snapshots and creates a fresh archive
        # after a reference edit or a deleted preparation. Earlier local ZIPs stay intact.
        transfer=request_json(collection,dict(device_id=device_id,device_label=label))
    temporary=pending.with_name(pending.name+'.'+uuid.uuid4().hex+'.new')
    try:
        with temporary.open('x',encoding='utf-8') as handle:
            json.dump(dict(origin=base,session_id=session_id,device_id=device_id,transfer=transfer),handle)
        temporary.chmod(0o600)
        if pending.is_symlink(): raise ValueError('Refusing a symbolic link as transfer state.')
        os.replace(temporary,pending)
    finally:
        temporary.unlink(missing_ok=True)
    transfer_id=transfer.get('id','')
    if not re.fullmatch('[0-9a-f]{32}',transfer_id): raise ValueError('Pi returned an invalid transfer identity.')
    expected_path='/api/transfers/'+transfer_id+'/archive'
    if transfer.get('download_url')!=expected_path and transfer.get('state')!='released':
        raise ValueError('Pi returned an unexpected archive location.')
    target=destination/('eeye-session-'+transfer_id+'.zip')
    partial=target.with_suffix('.zip.partial')
    if target.is_symlink() or partial.is_symlink(): raise ValueError('Refusing a symbolic link as a saved archive.')
    expected=transfer['manifest_sha256']
    archive_hash,archive_bytes=transfer.get('archive_sha256'),transfer.get('archive_bytes')
    if not isinstance(archive_hash,str) or not re.fullmatch('[0-9a-f]{64}',archive_hash) or type(archive_bytes) is not int or archive_bytes<=0:
        raise ValueError('Pi did not advertise a complete archive checksum and byte count. Pi files were kept.')
    def verify_saved(handle):
        return verify_archive(handle,expected,expected_archive_sha256=archive_hash,expected_archive_bytes=archive_bytes)
    if partial.is_file() and not target.exists():
        try:
            with partial.open('rb') as handle: verify_saved(handle)
        except ValueError:
            pass
        else:
            partial.rename(target)
    if not target.exists():
        offset=partial.stat().st_size if partial.exists() else 0
        headers={'Range':f'bytes={offset}-'} if offset else {}
        try:
            response=opener.open(urllib.request.Request(base+expected_path,headers=headers),timeout=timeout)
        except urllib.error.HTTPError as error:
            if error.code!=416: raise
            # A full but damaged partial must be downloaded again, not acknowledged.
            response=opener.open(urllib.request.Request(base+expected_path),timeout=timeout)
            offset=0
        with response:
            if response.headers.get('X-EEye-Manifest-SHA256')!=expected:
                raise ValueError('Pi manifest checksum changed. No acknowledgement was sent.')
            if response.headers.get('X-EEye-Archive-SHA256')!=archive_hash or response.headers.get('X-EEye-Archive-Bytes')!=str(archive_bytes):
                raise ValueError('Pi archive checksum changed. No acknowledgement was sent.')
            append=offset>0 and response.status==206
            remaining=int(response.headers.get('Content-Length','0'))
            if remaining and shutil.disk_usage(destination).free < remaining+16*1024**2:
                raise ValueError('Not enough local storage. Pi files were kept.')
            with partial.open('ab' if append else 'wb') as output:
                while chunk:=response.read(1024*1024): output.write(chunk)
                output.flush()
                os.fsync(output.fileno())
        partial.chmod(0o600)
        # Read-back happens from the closed disk file, never from the download buffer.
        with partial.open('rb') as handle: manifest=verify_saved(handle)
        partial.rename(target)
    else:
        with target.open('rb') as handle: manifest=verify_saved(handle)
    if manifest['transfer_id']!=transfer_id or manifest['session_id']!=session_id or manifest['device_id']!=device_id:
        raise ValueError('Saved transfer belongs to a different session or device. Pi files were kept.')
    proof=dict(ack_token=manifest['ack_token'],manifest_sha256=expected,device_id=device_id,verified=True)
    acknowledged=request_json('/api/transfers/'+transfer_id+'/ack',proof)
    if acknowledged.get('state') not in ('verified','released'):
        raise ValueError('Pi did not confirm the verified save. Pi files were kept.')
    if release:
        released=request_json('/api/transfers/'+transfer_id+'/release',proof)
        if released.get('state')!='released': raise ValueError('Pi did not confirm storage release.')
    pending.unlink(missing_ok=True)
    return dict(path=str(target),manifest=manifest,pi_files_released=release)
