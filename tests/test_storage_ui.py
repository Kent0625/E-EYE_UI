from pathlib import Path
from flask import Flask
from app import store
from app.receipts import init_receipts_db


def test_result_explains_verified_transfer_and_keeps_browser_copy(tmp_path, monkeypatch):
    monkeypatch.setattr(store,'DATABASE_PATH',str(tmp_path/'test.db'))
    store.init_db()
    init_receipts_db()
    session = store.create_session(dict(id='storage-ui',participant_code='TEST-STORAGE',
        eyes={'OD':{'status':'captured','frames_total':12,'frames_used':0,'quality_status':'unavailable'},
              'OS':{'status':'not_recorded'}}))
    app = Flask(__name__,template_folder=str(Path(__file__).resolve().parents[1]/'app/templates'))
    with app.test_request_context():
        text=app.jinja_env.get_template('result.html').render(session=session,research_mode=False,
            mock_mode=False,t=lambda key,**kw:key,current_lang='en',active_nav='screen')
    assert 'id="storage-transfer"' in text
    assert 'Prepare session archive' in text
    assert 'Browser downloads keep the Pi copy' in text
    assert 'storage-transfer.js' in text


def test_offloaded_capture_displays_device_location_without_empty_download(tmp_path, monkeypatch):
    monkeypatch.setattr(store,'DATABASE_PATH',str(tmp_path/'test.db'))
    store.init_db()
    session=store.create_session(dict(id='storage-ui',participant_code='TEST-STORAGE',eyes={
        'OD':{'status':'captured','capture_id':'a'*32,'frames_total':12,'frames_used':0,
              'quality_status':'unavailable','external_storage':{'device_label':'Research phone'}},
        'OS':{'status':'not_recorded'}}))
    app=Flask(__name__,template_folder=str(Path(__file__).resolve().parents[1]/'app/templates'))
    with app.test_request_context():
        text=app.jinja_env.get_template('result.html').render(session=session,research_mode=False,
            mock_mode=False,t=lambda key,**kw:key,current_lang='en',active_nav='screen')
    assert 'Research phone' in text
    assert '/captures/'+'a'*32+'/download' not in text
