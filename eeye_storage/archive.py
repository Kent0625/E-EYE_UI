from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import zipfile

MANIFEST_NAME = 'transfer-manifest.json'
MAX_MANIFEST_BYTES = 1024 * 1024


def canonical_json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf-8')


def safe_member(name):
    path = PurePosixPath(name)
    return (isinstance(name, str) and bool(name) and '\\' not in name and ':' not in name
            and not name.startswith('/') and all(part not in ('', '.', '..') for part in name.split('/'))
            and str(path) == name and not name.endswith('/'))


def file_digest(path):
    with Path(path).open('rb') as handle:
        return hashlib.file_digest(handle, 'sha256').hexdigest()


@dataclass(frozen=True)
class ArchiveFile:
    name: str
    source: Path | None = None
    content: bytes | None = None

    def metadata(self):
        if not safe_member(self.name) or self.name == MANIFEST_NAME:
            raise ValueError('Invalid archive member path.')
        if (self.source is None) == (self.content is None):
            raise ValueError('Archive entry needs exactly one source.')
        if self.source is not None:
            source = Path(self.source)
            if source.is_symlink() or not source.is_file():
                raise ValueError('Source file is missing or is a symbolic link.')
            return dict(path=self.name, bytes=source.stat().st_size, sha256=file_digest(source))
        return dict(path=self.name, bytes=len(self.content), sha256=hashlib.sha256(self.content).hexdigest())


def create_archive(destination, fields, files):
    """Write an immutable manifest-first ZIP and detect a source changing during creation."""
    entries = [entry.metadata() for entry in files]
    if len({entry['path'] for entry in entries}) != len(entries):
        raise ValueError('Duplicate archive member path.')
    manifest = dict(fields, schema_version=1, files=entries)
    raw = canonical_json(manifest)
    if len(raw) > MAX_MANIFEST_BYTES:
        raise ValueError('The transfer contains too many files for one archive.')
    destination = Path(destination)
    descriptor=os.open(destination,os.O_WRONLY|os.O_CREAT|os.O_EXCL|getattr(os,'O_BINARY',0),0o600)
    identity=os.fstat(descriptor)
    try:
        with os.fdopen(descriptor,'wb') as handle:
            with zipfile.ZipFile(handle, 'w', compression=zipfile.ZIP_STORED, allowZip64=True) as archive:
                archive.writestr(MANIFEST_NAME, raw)
                for entry, expected in zip(files, entries):
                    if entry.content is not None:
                        archive.writestr(entry.name, entry.content)
                    else:
                        digest, size = hashlib.sha256(), 0
                        with Path(entry.source).open('rb') as source, archive.open(entry.name, 'w', force_zip64=True) as target:
                            while chunk := source.read(1024 * 1024):
                                digest.update(chunk); size += len(chunk); target.write(chunk)
                        if size != expected['bytes'] or digest.hexdigest() != expected['sha256']:
                            raise ValueError('A source changed while the transfer was being prepared. Retry.')
            handle.flush()
            os.fsync(handle.fileno())
        destination.chmod(0o600)
    except Exception:
        try:
            current=destination.stat(follow_symlinks=False)
            if (current.st_dev,current.st_ino)==(identity.st_dev,identity.st_ino):
                destination.unlink()
        except FileNotFoundError:
            pass
        raise
    return manifest, hashlib.sha256(raw).hexdigest()


def verify_archive(source, expected_manifest_sha256, max_total_bytes=16 * 1024**3,
                   expected_archive_sha256=None, expected_archive_bytes=None):
    """Read every saved byte. Return manifest only after all names, sizes and hashes agree."""
    try:
        if expected_archive_sha256 is not None or expected_archive_bytes is not None:
            if isinstance(source,(str,Path)):
                with Path(source).open('rb') as handle:
                    _verify_whole_file(handle,expected_archive_sha256,expected_archive_bytes)
            else:
                _verify_whole_file(source,expected_archive_sha256,expected_archive_bytes)
        with zipfile.ZipFile(source, 'r') as archive:
            infos = archive.infolist()
            if not infos or infos[0].filename != MANIFEST_NAME or infos[0].file_size > MAX_MANIFEST_BYTES:
                raise ValueError('The archive has no bounded, first-entry transfer manifest.')
            if len({entry.filename for entry in infos}) != len(infos):
                raise ValueError('The archive has duplicate entries.')
            raw = archive.read(MANIFEST_NAME)
            if hashlib.sha256(raw).hexdigest() != expected_manifest_sha256:
                raise ValueError('Saved manifest checksum does not match the Pi.')
            manifest = json.loads(raw)
            if manifest.get('schema_version') != 1 or not isinstance(manifest.get('files'), list):
                raise ValueError('Unsupported transfer manifest.')
            expected = {}
            total = 0
            for item in manifest['files']:
                name, size, digest = item.get('path'), item.get('bytes'), item.get('sha256')
                if (not isinstance(name, str) or not safe_member(name) or name == MANIFEST_NAME or name in expected
                        or type(size) is not int or size < 0 or not isinstance(digest, str) or len(digest) != 64
                        or any(c not in '0123456789abcdef' for c in digest)):
                    raise ValueError('Invalid transfer file metadata.')
                expected[name] = item; total += size
            if total > max_total_bytes or set(expected) != {entry.filename for entry in infos[1:]}:
                raise ValueError('Archive entries differ from the manifest or exceed the allowed size.')
            for entry in infos[1:]:
                item = expected[entry.filename]
                if entry.is_dir() or entry.file_size != item['bytes']:
                    raise ValueError('Saved file size differs from the manifest.')
                digest, size = hashlib.sha256(), 0
                with archive.open(entry) as handle:
                    while chunk := handle.read(1024 * 1024):
                        size += len(chunk)
                        if size > item['bytes']:
                            raise ValueError('Saved file exceeds its declared size.')
                        digest.update(chunk)
                if size != item['bytes'] or digest.hexdigest() != item['sha256']:
                    raise ValueError('Saved file checksum does not match the Pi.')
            for key in ('transfer_id', 'session_id', 'participant_code', 'device_id', 'device_label', 'ack_token'):
                if not isinstance(manifest.get(key), str) or not manifest[key]:
                    raise ValueError('Required transfer identity is missing.')
            return manifest
    except (zipfile.BadZipFile, KeyError, TypeError, UnicodeError, json.JSONDecodeError, RuntimeError) as error:
        raise ValueError('The saved transfer archive cannot be verified.') from error


def _verify_whole_file(handle, expected_sha256, expected_bytes):
    handle.seek(0,2)
    size=handle.tell(); handle.seek(0)
    if expected_bytes is not None and size!=expected_bytes:
        raise ValueError('The saved ZIP is incomplete or has extra bytes.')
    if expected_sha256 is not None and hashlib.file_digest(handle,'sha256').hexdigest()!=expected_sha256:
        raise ValueError('The complete saved ZIP checksum does not match the Pi.')
    handle.seek(0)
