"""Flask/SQLite adapter for verified transfers. The archive library has no app dependency."""
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import threading
from urllib.parse import urlsplit
import uuid

from flask import Blueprint, current_app, jsonify, request, send_file
from app import store, config
from app.receipts import receipt_directory
from eeye_storage import ArchiveFile, create_archive
from eeye_storage.archive import canonical_json, file_digest, safe_member

transfers_bp = Blueprint('transfers', __name__)
_fallback_lock = threading.Lock()
_ID = re.compile(r'^[0-9a-f]{32}$')


class TransferConflict(ValueError):
    pass


def transfer_root():
    root = Path(os.environ.get('EEYE_DATA', config.DATA_DIR)) / 'transfers'
    root.mkdir(parents=True, exist_ok=True)
    root.chmod(0o700)
    return root.resolve()


def init_transfers_db():
    with store.get_connection() as db:
        db.executescript('''
          CREATE TABLE IF NOT EXISTS storage_transfers (
            id TEXT PRIMARY KEY, session_id TEXT NOT NULL, state TEXT NOT NULL,
            device_id TEXT NOT NULL, device_label TEXT NOT NULL, manifest_sha256 TEXT NOT NULL,
            token_sha256 TEXT NOT NULL, snapshot_sha256 TEXT NOT NULL,
            created_at TEXT NOT NULL, verified_at TEXT, released_at TEXT,
            archive_sha256 TEXT, archive_bytes INTEGER);
          CREATE INDEX IF NOT EXISTS storage_transfer_session ON storage_transfers(session_id);
          CREATE TABLE IF NOT EXISTS storage_transfer_files (
            transfer_id TEXT NOT NULL, archive_path TEXT NOT NULL, source_path TEXT NOT NULL,
            quarantine_path TEXT NOT NULL, sha256 TEXT NOT NULL, bytes INTEGER NOT NULL,
            PRIMARY KEY (transfer_id, archive_path));
          CREATE TABLE IF NOT EXISTS storage_receipt_locations (
            receipt_id TEXT PRIMARY KEY, transfer_id TEXT NOT NULL, device_id TEXT NOT NULL,
            device_label TEXT NOT NULL, verified_at TEXT NOT NULL);
        ''')
        columns={row['name'] for row in db.execute('PRAGMA table_info(storage_transfers)')}
        for name,kind in (('archive_sha256','TEXT'),('archive_bytes','INTEGER')):
            if name not in columns: db.execute('ALTER TABLE storage_transfers ADD COLUMN '+name+' '+kind)
        for row in db.execute('SELECT id FROM storage_transfers WHERE archive_sha256 IS NULL').fetchall():
            path=transfer_root()/(row['id']+'.zip')
            if _ID.fullmatch(row['id']) and path.is_file() and not path.is_symlink():
                db.execute('UPDATE storage_transfers SET archive_sha256=?,archive_bytes=? WHERE id=?',
                           (file_digest(path),path.stat().st_size,row['id']))
        pending = db.execute("SELECT id FROM storage_transfers WHERE state='releasing'").fetchall()
        for row in pending:
            _restore_quarantine(db, row['id'])
            db.execute("UPDATE storage_transfers SET state='verified' WHERE id=?", (row['id'],))
        finished = db.execute("SELECT id FROM storage_transfers WHERE state IN ('released','superseded')").fetchall()
        for row in finished:
            _remove_finished_payload(db, row['id'])


@transfers_bp.before_request
def transfer_request_guard():
    if request.content_length and request.content_length > 8192:
        return jsonify(error='Transfer request is too large.'), 413
    if request.method == 'POST':
        origin = request.headers.get('Origin')
        if (origin and urlsplit(origin).netloc != request.host) or request.headers.get('Sec-Fetch-Site') == 'cross-site':
            return jsonify(error='Open the E-Eye interface on this device before transferring files.'), 403


@transfers_bp.errorhandler(TransferConflict)
def transfer_conflict(error):
    return jsonify(error=str(error)), 409


@contextmanager
def mutation_guard():
    pipeline = current_app.extensions.get('capture_pipeline')
    lock = pipeline.lock if pipeline else _fallback_lock
    if not lock.acquire(blocking=False):
        raise TransferConflict('A capture or storage change is running. Wait and retry.')
    try:
        yield
    finally:
        lock.release()


def _rows(db, table, session_id):
    if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone():
        return []
    return [dict(row) for row in db.execute('SELECT * FROM '+table+' WHERE session_id=? ORDER BY rowid', (session_id,))]


def _snapshot(db, session_id):
    session = db.execute('SELECT * FROM sessions WHERE id=?', (session_id,)).fetchone()
    if not session:
        raise TransferConflict('Session no longer exists. Reopen the participant record.')
    jobs = _rows(db, 'capture_jobs', session_id)
    if any(job['state'] in ('recording', 'processing') for job in jobs):
        raise TransferConflict('Wait until all captures finish before saving this session.')
    return dict(session=dict(session), receipts=_rows(db, 'receipts', session_id),
                reference_audit=_rows(db, 'ground_truth_audit', session_id), capture_jobs=jobs)


def _snapshot_hash(snapshot):
    return hashlib.sha256(canonical_json(snapshot)).hexdigest()


def _controlled_file(root, relative):
    root = Path(root).resolve()
    target = root / relative
    for path in (target, *target.parents):
        if path == root:
            break
        if path.is_symlink():
            raise TransferConflict('A source path is a symbolic link. Files were kept on the Pi.')
    resolved = target.resolve()
    if not resolved.is_relative_to(root) or not resolved.is_file():
        raise TransferConflict('A source file is missing or outside the data directory. Files were kept on the Pi.')
    return resolved


def _archive_inputs(db, snapshot):
    session = snapshot['session']
    eyes = json.loads(session['eyes_data'] or '{}')
    files = [ArchiveFile('metadata/session.json', content=canonical_json(dict(
        session, eyes=eyes))), ArchiveFile('metadata/reference-audit.json', content=canonical_json(snapshot['reference_audit']))]
    references = {}
    def reference(row, kind, identifier):
        item=references.setdefault(row['id'],dict(transfer_id=row['id'],manifest_sha256=row['manifest_sha256'],
            archive_sha256=row['archive_sha256'],device_id=row['device_id'],device_label=row['device_label'],
            capture_ids=[],receipt_ids=[]))
        item[kind].append(identifier)
    capture_ids = {eye.get('capture_id') for eye in eyes.values() if isinstance(eye, dict) and eye.get('capture_id')}
    capture_ids.update(job['id'] for job in snapshot['capture_jobs'])
    for capture_id in sorted(capture_ids):
        if not _ID.fullmatch(capture_id):
            raise TransferConflict('Invalid capture identity. Files were kept on the Pi.')
        folder = Path(config.CAPTURE_FOLDER) / capture_id
        if folder.is_symlink():
            raise TransferConflict('A capture path is a symbolic link. Files were kept on the Pi.')
        previous=db.execute('''SELECT DISTINCT t.* FROM storage_transfers t
            JOIN storage_transfer_files f ON f.transfer_id=t.id
            WHERE t.session_id=? AND t.state='released' AND f.archive_path LIKE ?
            ORDER BY t.released_at DESC LIMIT 1''',(session['id'],'captures/'+capture_id+'/%')).fetchone()
        if previous and (not folder.exists() or (folder.is_dir() and not any(folder.iterdir()))):
            reference(previous,'capture_ids',capture_id)
            continue
        if folder.is_symlink() or not folder.is_dir():
            raise TransferConflict('Capture files were already moved or are missing. Open the saved device archive.')
        count = 0
        for source in sorted(folder.rglob('*')):
            if source.is_symlink():
                raise TransferConflict('A capture contains a symbolic link. Files were kept on the Pi.')
            if source.is_dir():
                continue
            source = _controlled_file(config.CAPTURE_FOLDER, source.relative_to(Path(config.CAPTURE_FOLDER)))
            files.append(ArchiveFile('captures/'+capture_id+'/'+source.relative_to(folder.resolve()).as_posix(), source=source))
            count += 1
        if not count:
            raise TransferConflict('Capture files were already moved or are missing. Open the saved device archive.')
    for receipt in snapshot['receipts']:
        receipt_id = receipt['id']
        if not _ID.fullmatch(receipt_id):
            raise TransferConflict('Invalid receipt identity. Files were kept on the Pi.')
        location=db.execute('''SELECT t.* FROM storage_receipt_locations l
            JOIN storage_transfers t ON t.id=l.transfer_id WHERE l.receipt_id=? AND t.state='released' ''',
            (receipt_id,)).fetchone()
        if location and not (receipt_directory()/receipt_id).exists():
            reference(location,'receipt_ids',receipt_id)
            continue
        source = _controlled_file(receipt_directory(), receipt_id)
        if source.stat().st_size != receipt['byte_size'] or file_digest(source) != receipt['sha256']:
            raise TransferConflict('A receipt differs from its saved record. Files were kept on the Pi.')
        suffix = '.png' if receipt['mime_type'] == 'image/png' else '.jpg'
        files.append(ArchiveFile('receipts/'+receipt_id+suffix, source=source))
    files.append(ArchiveFile('metadata/receipts.json', content=canonical_json(snapshot['receipts'])))
    files.append(ArchiveFile('metadata/capture-jobs.json', content=canonical_json(snapshot['capture_jobs'])))
    files.append(ArchiveFile('metadata/external-archives.json',content=canonical_json(list(references.values()))))
    files.append(ArchiveFile('README.txt', content=(
        'E-Eye saved session\nOriginal capture files: captures/\nOriginal autorefractor receipts: receipts/\n'
        'Session values and reference audit: metadata/\nVerify this archive before removing any Pi copy.\n'
        'Earlier offloaded files are listed in metadata/external-archives.json. Keep those saved archives too.\n'
        'A transfer acknowledgement is not a second backup. Copy important sessions to Windows or another drive.\n').encode()))
    return files


def _public(row):
    return dict(id=row['id'], session_id=row['session_id'], state=row['state'], device_id=row['device_id'],
        device_label=row['device_label'], manifest_sha256=row['manifest_sha256'], created_at=row['created_at'],
        verified_at=row['verified_at'], released_at=row['released_at'],
        archive_sha256=row['archive_sha256'],archive_bytes=row['archive_bytes'],
        download_url='/api/transfers/'+row['id']+'/archive' if row['state'] not in ('released','superseded') else None)


@transfers_bp.get('/api/storage/status')
def storage_status():
    root = transfer_root()
    return jsonify(ready=True,protocol_version=1,api_version=1, temporary_copy=True, release_requires_verified_ack=True,
                   free_bytes=shutil.disk_usage(root).free)


@transfers_bp.route('/api/sessions/<id>/transfers', methods=['GET', 'POST'])
def session_transfers(id):
    if request.method == 'GET':
        if not store.get_session(id):
            return jsonify(error='Session not found.'), 404
        with store.get_connection() as db:
            rows = db.execute('SELECT * FROM storage_transfers WHERE session_id=? ORDER BY created_at DESC', (id,)).fetchall()
        return jsonify(transfers=[_public(row) for row in rows])
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify(error='Choose a receiving device name.'), 400
    device_id, label = data.get('device_id'), data.get('device_label')
    if any(not isinstance(value, str) or not value.strip() or len(value) > limit
           or any(ord(char) < 32 for char in value) for value, limit in ((device_id,128),(label,80))):
        return jsonify(error='Use a device identifier under 128 characters and a device name under 80 characters.'), 400
    token, transfer_id = secrets.token_urlsafe(32), uuid.uuid4().hex
    root = transfer_root(); archive_path = root/(transfer_id+'.zip')
    archive_created=False
    try:
        with mutation_guard(), store.get_connection() as db:
            db.execute('BEGIN IMMEDIATE')
            snapshot = _snapshot(db,id)
            snapshot_hash = _snapshot_hash(snapshot)
            existing = db.execute("SELECT * FROM storage_transfers WHERE session_id=? AND device_id=? AND device_label=? AND snapshot_sha256=? AND state IN ('ready','verified') ORDER BY created_at DESC LIMIT 1",
                (id,device_id,label,snapshot_hash)).fetchone()
            if existing:
                prepared=root/(existing['id']+'.zip')
                if prepared.is_file() and not prepared.is_symlink():
                    return jsonify(_public(existing)),201
            files = _archive_inputs(db, snapshot)
            required = sum(entry.source.stat().st_size if entry.source else len(entry.content) for entry in files)
            if shutil.disk_usage(root).free < required + 64*1024**2:
                raise TransferConflict('Not enough Pi storage to prepare a safe transfer. Existing files were kept.')
            now = datetime.now(timezone.utc).isoformat()
            manifest, manifest_hash = create_archive(archive_path, dict(transfer_id=transfer_id, session_id=id,
                participant_code=snapshot['session']['participant_code'],device_id=device_id,device_label=label,
                created_at=now,ack_token=token), files)
            archive_created=True
            archive_hash=file_digest(archive_path)
            archive_bytes=archive_path.stat().st_size
            db.execute('''INSERT INTO storage_transfers
                (id,session_id,state,device_id,device_label,manifest_sha256,token_sha256,
                 snapshot_sha256,created_at,verified_at,released_at,archive_sha256,archive_bytes)
                 VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                (transfer_id,id,'ready',device_id,label,manifest_hash,hashlib.sha256(token.encode()).hexdigest(),
                 snapshot_hash,now,None,None,archive_hash,archive_bytes))
            by_name = {entry['path']:entry for entry in manifest['files']}
            for entry in files:
                if entry.source is not None:
                    expected = by_name[entry.name]
                    quarantine = root/'quarantine'/transfer_id/entry.name
                    db.execute('INSERT INTO storage_transfer_files VALUES (?,?,?,?,?,?)',
                        (transfer_id,entry.name,str(entry.source),str(quarantine),expected['sha256'],expected['bytes']))
            row = db.execute('SELECT * FROM storage_transfers WHERE id=?',(transfer_id,)).fetchone()
        return jsonify(_public(row)), 201
    except (ValueError, OSError) as error:
        if archive_created: archive_path.unlink(missing_ok=True)
        raise TransferConflict(str(error)) from error
    except Exception:
        if archive_created: archive_path.unlink(missing_ok=True)
        raise


def _transfer_row(db, transfer_id):
    if not _ID.fullmatch(transfer_id):
        return None
    return db.execute('SELECT * FROM storage_transfers WHERE id=?',(transfer_id,)).fetchone()


@transfers_bp.get('/api/transfers/<transfer_id>/archive')
def transfer_archive(transfer_id):
    with store.get_connection() as db:
        row = _transfer_row(db,transfer_id)
    if row is None:
        return jsonify(error='Transfer not found.'),404
    if row['state'] == 'superseded':
        return jsonify(error='This preparation was replaced after a verified save. Check the session saved-device locations.'),410
    if row['state'] == 'released':
        return jsonify(error='Files are saved on '+row['device_label']+'. Open that device archive.'),410
    path=transfer_root()/(transfer_id+'.zip')
    if not path.is_file() or path.is_symlink():
        return jsonify(error='The prepared transfer is missing. Prepare a new transfer; originals were kept.'),409
    response=send_file(path,mimetype='application/zip',as_attachment=True,
                       download_name='eeye-session-'+transfer_id+'.zip',conditional=True)
    response.headers['X-EEye-Manifest-SHA256']=row['manifest_sha256']
    response.headers['X-EEye-Archive-SHA256']=row['archive_sha256']
    response.headers['X-EEye-Archive-Bytes']=str(row['archive_bytes'])
    response.headers['Cache-Control']='no-store'
    return response


def _check_proof(row,data):
    if not isinstance(data,dict) or data.get('verified') is not True:
        raise TransferConflict('The receiving app must verify its saved archive before acknowledging it.')
    token = data.get('ack_token')
    if (not isinstance(token,str) or len(token)>256
            or not hmac.compare_digest(hashlib.sha256(token.encode()).hexdigest(),row['token_sha256'])
            or data.get('manifest_sha256') != row['manifest_sha256'] or data.get('device_id') != row['device_id']):
        raise TransferConflict('Transfer identity or saved checksum does not match. Pi files were kept.')


@transfers_bp.post('/api/transfers/<transfer_id>/ack')
def acknowledge_transfer(transfer_id):
    with mutation_guard(),store.get_connection() as db:
        db.execute('BEGIN IMMEDIATE')
        row=_transfer_row(db,transfer_id)
        if row is None: return jsonify(error='Transfer not found.'),404
        _check_proof(row,request.get_json(silent=True))
        if row['state']=='ready':
            if _snapshot_hash(_snapshot(db,row['session_id'])) != row['snapshot_sha256']:
                raise TransferConflict('The session changed after this transfer. Prepare a new archive.')
            db.execute("UPDATE storage_transfers SET state='verified',verified_at=? WHERE id=?",
                       (datetime.now(timezone.utc).isoformat(),transfer_id))
        return jsonify(_public(_transfer_row(db,transfer_id)))


def _source_rows(db, transfer_id):
    return db.execute('SELECT * FROM storage_transfer_files WHERE transfer_id=?',(transfer_id,)).fetchall()


def _private_paths(row):
    """Persisted paths remain untrusted during recovery; rederive them from the public member name."""
    name,transfer_id=row['archive_path'],row['transfer_id']
    if not _ID.fullmatch(transfer_id) or not safe_member(name):
        raise TransferConflict('Invalid recovery file identity. Files were kept for review.')
    parts=name.split('/')
    if len(parts)>=3 and parts[0]=='captures' and _ID.fullmatch(parts[1]):
        source=Path(config.CAPTURE_FOLDER).resolve().joinpath(*parts[1:])
        source_root=Path(config.CAPTURE_FOLDER).resolve()
    elif len(parts)==2 and parts[0]=='receipts' and _ID.fullmatch(Path(parts[1]).stem) and Path(parts[1]).suffix in ('.jpg','.png'):
        source_root=receipt_directory().resolve(); source=source_root/Path(parts[1]).stem
    else:
        raise TransferConflict('Recovery source is outside the capture or receipt directory.')
    root=transfer_root(); quarantine=root/'quarantine'/transfer_id/name
    if str(source)!=row['source_path'] or str(quarantine)!=row['quarantine_path']:
        raise TransferConflict('Recovery paths changed. Files were kept for review.')
    for path,base in ((source,source_root),(quarantine,root)):
        if not path.resolve().is_relative_to(base):
            raise TransferConflict('A recovery path escaped its private directory.')
        for ancestor in (path,*path.parents):
            if ancestor==base: break
            if ancestor.is_symlink():
                raise TransferConflict('A recovery path became a symbolic link. Files were kept for review.')
    return source,quarantine


def _validate_source(row):
    source,quarantine=_private_paths(row)
    path=source if source.exists() else quarantine
    if path.is_symlink() or not path.is_file() or path.stat().st_size!=row['bytes'] or file_digest(path)!=row['sha256']:
        raise TransferConflict('An exported source changed or is missing. Pi files were kept; prepare a new transfer.')
    if source.exists() and quarantine.exists():
        raise TransferConflict('Both original and recovery copy exist. Pi files were kept for review.')
    return source,quarantine,path


def _restore_quarantine(db, transfer_id):
    for row in _source_rows(db,transfer_id):
        source,quarantine=_private_paths(row)
        if quarantine.exists():
            if source.exists():
                raise TransferConflict('A recovery copy conflicts with an original. Both files were kept.')
            if quarantine.is_symlink() or file_digest(quarantine)!=row['sha256']:
                raise TransferConflict('The recovery copy checksum differs. Files were kept for review.')
            source.parent.mkdir(parents=True,exist_ok=True)
            os.replace(quarantine,source)


def _remove_finished_payload(db, transfer_id):
    # These are private, exact transfer paths recorded before any source was moved.
    for row in _source_rows(db,transfer_id):
        _,path=_private_paths(row)
        if path.exists() and not path.is_symlink() and file_digest(path)==row['sha256']:
            try: path.unlink()
            except OSError: pass  # A concurrent download may hold a Windows handle; startup retries cleanup.
    path=transfer_root()/(transfer_id+'.zip')
    if path.is_file() and not path.is_symlink():
        try: path.unlink()
        except OSError: pass


@transfers_bp.post('/api/transfers/<transfer_id>/release')
def release_transfer(transfer_id):
    with mutation_guard():
        with store.get_connection() as db:
            db.execute('BEGIN IMMEDIATE')
            row=_transfer_row(db,transfer_id)
            if row is None: return jsonify(error='Transfer not found.'),404
            _check_proof(row,request.get_json(silent=True))
            if row['state']=='released': return jsonify(_public(row))
            if row['state'] not in ('verified','releasing'):
                raise TransferConflict('The saved archive has not been verified. Pi files were kept.')
            if _snapshot_hash(_snapshot(db,row['session_id'])) != row['snapshot_sha256']:
                _restore_quarantine(db,transfer_id)
                raise TransferConflict('The session changed after export. Pi files were kept; prepare a new archive.')
            for source_row in _source_rows(db,transfer_id): _validate_source(source_row)
            db.execute("UPDATE storage_transfers SET state='releasing' WHERE id=?",(transfer_id,))
        try:
            with store.get_connection() as db:
                db.execute('BEGIN IMMEDIATE')
                row=_transfer_row(db,transfer_id)
                if _snapshot_hash(_snapshot(db,row['session_id'])) != row['snapshot_sha256']:
                    raise TransferConflict('The session changed after export. Prepare a new archive.')
                snapshot=_snapshot(db,row['session_id'])
                for source_row in _source_rows(db,transfer_id):
                    source,quarantine,existing=_validate_source(source_row)
                    if existing==source:
                        quarantine.parent.mkdir(parents=True,exist_ok=True)
                        os.replace(source,quarantine)
                location=dict(transfer_id=transfer_id,device_id=row['device_id'],device_label=row['device_label'],verified_at=row['verified_at'])
                exported_captures=set()
                exported_receipts=set()
                for source_row in _source_rows(db,transfer_id):
                    parts=source_row['archive_path'].split('/')
                    if parts[0]=='captures': exported_captures.add(parts[1])
                    if parts[0]=='receipts': exported_receipts.add(Path(parts[1]).stem)
                eyes=json.loads(snapshot['session']['eyes_data'] or '{}')
                for eye in eyes.values():
                    if isinstance(eye,dict) and eye.get('capture_id') in exported_captures:
                        eye['external_storage']=location
                db.execute('UPDATE sessions SET eyes_data=? WHERE id=?',(json.dumps(eyes),row['session_id']))
                for receipt in snapshot['receipts']:
                    if receipt['id'] not in exported_receipts: continue
                    db.execute('INSERT OR REPLACE INTO storage_receipt_locations VALUES (?,?,?,?,?)',
                        (receipt['id'],transfer_id,row['device_id'],row['device_label'],row['verified_at']))
                db.execute("UPDATE storage_transfers SET state='released',released_at=? WHERE id=?",
                           (datetime.now(timezone.utc).isoformat(),transfer_id))
                db.execute("UPDATE storage_transfers SET state='superseded' WHERE session_id=? AND id<>? AND state IN ('ready','verified')",
                           (row['session_id'],transfer_id))
            with store.get_connection() as db:
                _remove_finished_payload(db,transfer_id)
                for other in db.execute("SELECT id FROM storage_transfers WHERE session_id=? AND state='superseded'",(row['session_id'],)):
                    _remove_finished_payload(db,other['id'])
                return jsonify(_public(_transfer_row(db,transfer_id)))
        except Exception:
            with store.get_connection() as db:
                row=_transfer_row(db,transfer_id)
                if row and row['state']=='releasing':
                    _restore_quarantine(db,transfer_id)
                    db.execute("UPDATE storage_transfers SET state='verified' WHERE id=?",(transfer_id,))
            raise


def external_location_for_receipt(receipt_id):
    with store.get_connection() as db:
        if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='storage_receipt_locations'").fetchone():
            return None
        row=db.execute('SELECT * FROM storage_receipt_locations WHERE receipt_id=?',(receipt_id,)).fetchone()
    return dict(row) if row else None


def delete_transfer_rows(db, session_id=None):
    """Inside the caller's session-delete transaction; unlink returned private paths after commit."""
    if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='storage_transfers'").fetchone():
        return []
    where,params=(' WHERE session_id=?',(session_id,)) if session_id else ('',())
    transfers=db.execute('SELECT id FROM storage_transfers'+where,params).fetchall()
    paths=[]
    for transfer in transfers:
        transfer_id=transfer['id']
        if not _ID.fullmatch(transfer_id): continue
        paths.append(transfer_root()/(transfer_id+'.zip'))
        paths.extend(_private_paths(row)[1] for row in _source_rows(db,transfer_id))
        db.execute('DELETE FROM storage_receipt_locations WHERE transfer_id=?',(transfer_id,))
        db.execute('DELETE FROM storage_transfer_files WHERE transfer_id=?',(transfer_id,))
        db.execute('DELETE FROM storage_transfers WHERE id=?',(transfer_id,))
    return paths


def cleanup_paths(paths):
    root=transfer_root()
    for path in paths:
        path=Path(path)
        if path.resolve().is_relative_to(root) and path.is_file() and not path.is_symlink():
            path.unlink(missing_ok=True)
