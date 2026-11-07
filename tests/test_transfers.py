import hashlib
import io
import json
from pathlib import Path
import threading
import zipfile

import pytest
from flask import Flask
from app import store
from app.capture import init_capture_db
from app.receipts import init_receipts_db


@pytest.fixture
def transfer_app(tmp_path, monkeypatch):
    monkeypatch.setattr(store, 'DATABASE_PATH', str(tmp_path/'state.db'))
    monkeypatch.setenv('EEYE_DATA', str(tmp_path/'data'))
    monkeypatch.setenv('EEYE_RECEIPTS', str(tmp_path/'receipts'))
    from app import config
    monkeypatch.setattr(config, 'CAPTURE_FOLDER', str(tmp_path/'captures'))
    store.init_db(); init_receipts_db(); init_capture_db()
    store.create_session(dict(id='test-session', participant_code='TEST-STORAGE-001',
        eyes={'OD': {'status':'captured','capture_id':'a'*32}, 'OS': {'status':'not_recorded'}}))
    directory=tmp_path/'captures'/('a'*32); directory.mkdir(parents=True)
    (directory/'0000.jpg').write_bytes(b'synthetic-frame-bytes')
    (directory/'capture.json').write_text('{"synthetic":true}')
    receipt=tmp_path/'receipts'; receipt.mkdir()
    (receipt/('b'*32)).write_bytes(b'synthetic-receipt')
    with store.get_connection() as db:
        db.execute('INSERT INTO receipts VALUES (?,?,?,?,?,?,?,?)', ('b'*32,'test-session','now','image/png',
            hashlib.sha256(b'synthetic-receipt').hexdigest(),17,1,1))
        db.execute('INSERT INTO capture_jobs(id,session_id,eye,state,payload) VALUES (?,?,?,?,?)',
            ('a'*32,'test-session','OD','complete','{}'))
    app=Flask(__name__); app.config['TESTING']=True
    app.extensions['capture_pipeline']=type('Pipeline',(),{'lock':threading.Lock()})()
    return app, tmp_path


def client_for(app):
    from app.transfers import transfers_bp, init_transfers_db
    init_transfers_db(); app.register_blueprint(transfers_bp)
    return app.test_client()


def start(client):
    result=client.post('/api/sessions/test-session/transfers',json={'device_id':'test-laptop','device_label':'Test laptop'})
    assert result.status_code==201, result.get_json()
    return result.json


def proof(client, transfer):
    response=client.get(transfer['download_url'])
    assert response.status_code==200
    with zipfile.ZipFile(io.BytesIO(response.data)) as z:
        raw=z.read('transfer-manifest.json'); manifest=json.loads(raw)
        assert hashlib.sha256(raw).hexdigest()==response.headers['X-EEye-Manifest-SHA256']
        assert set(z.namelist())=={'transfer-manifest.json'}|{f['path'] for f in manifest['files']}
        for entry in manifest['files']:
            data=z.read(entry['path'])
            assert len(data)==entry['bytes']
            assert hashlib.sha256(data).hexdigest()==entry['sha256']
    return dict(ack_token=manifest['ack_token'],device_id=manifest['device_id'],
        manifest_sha256=transfer['manifest_sha256'],verified=True), response.data


def test_download_and_ack_do_not_delete_originals(transfer_app):
    app,root=transfer_app; client=client_for(app); transfer=start(client)
    payload,archive=proof(client,transfer)
    assert b'synthetic-frame' not in json.dumps(transfer).encode()
    assert client.post('/api/transfers/'+transfer['id']+'/ack',json=payload).status_code==200
    assert (root/'captures'/('a'*32)/'0000.jpg').exists()
    assert (root/'receipts'/('b'*32)).exists()
    from eeye_storage import verify_archive
    verified=verify_archive(io.BytesIO(archive),transfer['manifest_sha256'])
    assert verified['participant_code']=='TEST-STORAGE-001'


def test_retrying_prepare_reuses_unchanged_transfer(transfer_app):
    app,_=transfer_app; client=client_for(app)
    first=start(client); second=start(client)
    assert first['id']==second['id']
    with store.get_connection() as db:
        assert db.execute('SELECT count(*) FROM storage_transfers').fetchone()[0]==1


def test_explicit_release_preserves_records_and_is_idempotent(transfer_app):
    app,root=transfer_app; client=client_for(app); transfer=start(client); payload,_=proof(client,transfer)
    endpoint='/api/transfers/'+transfer['id']
    assert client.post(endpoint+'/release',json=payload).status_code==409
    assert client.post(endpoint+'/ack',json=payload).status_code==200
    assert client.post(endpoint+'/release',json=payload).status_code==200
    assert not (root/'captures'/('a'*32)/'0000.jpg').exists()
    assert not (root/'receipts'/('b'*32)).exists()
    session=store.get_session('test-session')
    assert session['eyes']['OD']['external_storage']['device_label']=='Test laptop'
    assert session['eyes']['OD']['capture_id']=='a'*32
    assert client.post(endpoint+'/release',json=payload).status_code==200
    assert client.post(endpoint+'/ack',json=payload).status_code==200
    assert client.get(transfer['download_url']).status_code==410
    with store.get_connection() as db:
        assert db.execute('SELECT count(*) FROM receipts').fetchone()[0]==1


@pytest.mark.parametrize('field,value',[('ack_token','wrong'),('device_id','other'),('manifest_sha256','0'*64),('verified',False)])
def test_bad_proof_cannot_release(transfer_app,field,value):
    app,root=transfer_app; client=client_for(app); transfer=start(client); payload,_=proof(client,transfer)
    payload[field]=value
    assert client.post('/api/transfers/'+transfer['id']+'/ack',json=payload).status_code in (400,403,409)
    assert (root/'captures'/('a'*32)/'0000.jpg').exists()


def test_changed_reference_or_file_prevents_release(transfer_app):
    app,root=transfer_app; client=client_for(app); transfer=start(client); payload,_=proof(client,transfer)
    client.post('/api/transfers/'+transfer['id']+'/ack',json=payload)
    store.update_session('test-session',site='changed after snapshot')
    assert client.post('/api/transfers/'+transfer['id']+'/release',json=payload).status_code==409
    assert (root/'captures'/('a'*32)/'0000.jpg').exists()


def test_active_capture_and_symlink_rejected(transfer_app):
    app,root=transfer_app; client=client_for(app)
    app.extensions['capture_pipeline'].lock.acquire()
    assert client.post('/api/sessions/test-session/transfers',json={'device_id':'d','device_label':'D'}).status_code==409
    app.extensions['capture_pipeline'].lock.release()
    (root/'captures'/('a'*32)/'capture.json').unlink()
    try:
        (root/'captures'/('a'*32)/'capture.json').symlink_to(root/'state.db')
    except OSError:
        pytest.skip('Creating symlinks requires developer mode on Windows')
    assert client.post('/api/sessions/test-session/transfers',json={'device_id':'d','device_label':'D'}).status_code==409


def test_corrupt_archive_never_verifies(transfer_app):
    app,_=transfer_app; client=client_for(app); transfer=start(client); _,archive=proof(client,transfer)
    from eeye_storage import verify_archive
    altered=io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(archive)) as source,zipfile.ZipFile(altered,'w') as target:
        for name in source.namelist():
            target.writestr(name,b'changed' if name.endswith('0000.jpg') else source.read(name))
    altered.seek(0)
    with pytest.raises(ValueError): verify_archive(altered,transfer['manifest_sha256'])


@pytest.mark.parametrize('mutation',['extra','duplicate','traversal'])
def test_archive_verifier_rejects_unsafe_or_unlisted_entries(transfer_app,mutation):
    app,_=transfer_app; client=client_for(app); transfer=start(client); _,archive=proof(client,transfer)
    from eeye_storage import verify_archive
    from eeye_storage.archive import canonical_json
    import warnings
    altered=io.BytesIO(); expected=transfer['manifest_sha256']
    with zipfile.ZipFile(io.BytesIO(archive)) as source,zipfile.ZipFile(altered,'w') as target:
        raw=source.read('transfer-manifest.json'); manifest=json.loads(raw)
        if mutation=='traversal':
            old=manifest['files'][0]['path']; manifest['files'][0]['path']='../escape.txt'
            raw=canonical_json(manifest); expected=hashlib.sha256(raw).hexdigest()
        target.writestr('transfer-manifest.json',raw)
        for name in source.namelist()[1:]:
            target.writestr('../escape.txt' if mutation=='traversal' and name==old else name,source.read(name))
        if mutation=='extra': target.writestr('unexpected.txt','not listed')
        if mutation=='duplicate':
            with warnings.catch_warnings():
                warnings.simplefilter('ignore',UserWarning)
                target.writestr(source.namelist()[1],source.read(source.namelist()[1]))
    altered.seek(0)
    with pytest.raises(ValueError): verify_archive(altered,expected)


def test_source_bytes_changed_after_ack_are_retained(transfer_app):
    app,root=transfer_app; client=client_for(app); transfer=start(client); payload,_=proof(client,transfer)
    client.post('/api/transfers/'+transfer['id']+'/ack',json=payload)
    source=root/'captures'/('a'*32)/'0000.jpg'; source.write_bytes(b'new-content')
    assert client.post('/api/transfers/'+transfer['id']+'/release',json=payload).status_code==409
    assert source.read_bytes()==b'new-content'


def test_interrupted_release_restores_sources_on_startup(transfer_app,monkeypatch):
    app,root=transfer_app; client=client_for(app); transfer=start(client); payload,_=proof(client,transfer)
    client.post('/api/transfers/'+transfer['id']+'/ack',json=payload)
    from app import transfers
    replace=transfers.os.replace
    def simulate_power_loss(source,target):
        replace(source,target)
        raise SystemExit('simulated process termination after atomic move')
    monkeypatch.setattr(transfers.os,'replace',simulate_power_loss)
    with pytest.raises(SystemExit): client.post('/api/transfers/'+transfer['id']+'/release',json=payload)
    assert not (root/'captures'/('a'*32)/'0000.jpg').exists()
    monkeypatch.setattr(transfers.os,'replace',replace)
    transfers.init_transfers_db()
    assert (root/'captures'/('a'*32)/'0000.jpg').read_bytes()==b'synthetic-frame-bytes'
    assert (root/'receipts'/('b'*32)).exists()
    assert client.post('/api/transfers/'+transfer['id']+'/release',json=payload).status_code==200


def test_tampered_persisted_paths_never_delete_unrelated_file(transfer_app):
    app,root=transfer_app; client=client_for(app); transfer=start(client); payload,_=proof(client,transfer)
    client.post('/api/transfers/'+transfer['id']+'/ack',json=payload)
    unrelated=root/'unrelated.txt'; unrelated.write_bytes(b'synthetic-frame-bytes')
    with store.get_connection() as db:
        db.execute("UPDATE storage_transfer_files SET source_path=? WHERE archive_path LIKE '%0000.jpg'",(str(unrelated),))
    assert client.post('/api/transfers/'+transfer['id']+'/release',json=payload).status_code==409
    assert unrelated.read_bytes()==b'synthetic-frame-bytes'


def test_low_pi_space_cannot_prepare_or_remove_files(transfer_app,monkeypatch):
    app,root=transfer_app; client=client_for(app)
    from app import transfers
    monkeypatch.setattr(transfers.shutil,'disk_usage',lambda path:type('Usage',(),{'free':1})())
    response=client.post('/api/sessions/test-session/transfers',json={'device_id':'d','device_label':'D'})
    assert response.status_code==409
    assert (root/'captures'/('a'*32)/'0000.jpg').exists()


def test_deleted_session_transfer_records_are_cleaned_atomically(transfer_app):
    app,root=transfer_app; client=client_for(app); transfer=start(client)
    from app.transfers import delete_transfer_rows,cleanup_paths
    with store.get_connection() as db:
        db.execute('BEGIN IMMEDIATE')
        paths=delete_transfer_rows(db,'test-session')
        db.execute('DELETE FROM sessions WHERE id=?',('test-session',))
    cleanup_paths(paths)
    assert client.get(transfer['download_url']).status_code==404
    assert not (root/'data'/'transfers'/(transfer['id']+'.zip')).exists()


def test_receiver_reads_back_and_releases_only_when_explicit(transfer_app,tmp_path):
    app,root=transfer_app; client_for(app)
    from werkzeug.serving import make_server
    from eeye_storage.receiver import receive_session
    server=make_server('127.0.0.1',0,app,threaded=True)
    worker=threading.Thread(target=server.serve_forever,daemon=True); worker.start()
    try:
        result=receive_session('http://127.0.0.1:'+str(server.server_port),'test-session',root/'laptop','Test laptop',True)
        assert Path(result['path']).is_file()
        assert result['manifest']['participant_code']=='TEST-STORAGE-001'
        assert not (root/'captures'/('a'*32)/'0000.jpg').exists()
    finally:
        server.shutdown(); server.server_close(); worker.join(timeout=2)


def test_incomplete_download_never_acknowledges_and_can_resume(transfer_app):
    app,root=transfer_app; client_for(app)
    from flask import Response
    from werkzeug.serving import make_server
    from eeye_storage.receiver import receive_session
    original=app.view_functions['transfers.transfer_archive']
    def truncated(transfer_id):
        response=original(transfer_id)
        response.direct_passthrough=False
        body=response.get_data()
        return Response(body[:len(body)//2],mimetype='application/zip',headers={
            'X-EEye-Manifest-SHA256':response.headers['X-EEye-Manifest-SHA256']})
    app.view_functions['transfers.transfer_archive']=truncated
    server=make_server('127.0.0.1',0,app,threaded=True)
    worker=threading.Thread(target=server.serve_forever,daemon=True); worker.start()
    url='http://127.0.0.1:'+str(server.server_port)
    try:
        with pytest.raises(ValueError): receive_session(url,'test-session',root/'laptop','Test laptop')
        assert (root/'captures'/('a'*32)/'0000.jpg').exists()
        with store.get_connection() as db:
            assert db.execute('SELECT state FROM storage_transfers').fetchone()[0]=='ready'
            assert db.execute('SELECT count(*) FROM storage_transfers').fetchone()[0]==1
        app.view_functions['transfers.transfer_archive']=original
        result=receive_session(url,'test-session',root/'laptop','Test laptop')
        assert Path(result['path']).is_file()
        assert result['pi_files_released'] is False
        assert (root/'captures'/('a'*32)/'0000.jpg').exists()
        with store.get_connection() as db:
            assert db.execute('SELECT count(*) FROM storage_transfers').fetchone()[0]==1
    finally:
        server.shutdown(); server.server_close(); worker.join(timeout=2)
