"""Synthetic browser download plus actual closed-file verification and release."""
import io
import json
import os
from pathlib import Path
import tempfile
import threading
from PIL import Image
from playwright.sync_api import sync_playwright
from werkzeug.serving import make_server
os.environ['EEYE_MOCK'] = '1'
from app import store, config
from app.app import create_app
from app.capture import init_capture_db
from eeye_storage import verify_archive
from eeye_storage.receiver import receive_session


with tempfile.TemporaryDirectory() as temporary:
    root=Path(temporary)
    store.DATABASE_PATH=str(root/'state.db')
    os.environ['EEYE_DATA']=str(root/'data')
    os.environ['EEYE_RECEIPTS']=str(root/'receipts')
    config.CAPTURE_FOLDER=str(root/'captures')
    app=create_app(); init_capture_db(); store.set_setting('research_mode','1')
    capture_id='c'*32
    folder=root/'captures'/capture_id; folder.mkdir(parents=True)
    Image.new('RGB',(32,32),'white').save(folder/'0000.jpg')
    (folder/'capture.json').write_text(json.dumps({'synthetic_test':True}))
    store.create_session(dict(id='save-ui',participant_code='TEST-DEVICE-SAVE',consent_age=True,
        consent_signed=True,eyes={'OD':{'status':'captured','capture_id':capture_id,'frames_total':1,
        'frames_used':0,'quality_status':'unavailable'},'OS':{'status':'not_recorded'}}))
    server=make_server('127.0.0.1',0,app,threaded=True)
    threading.Thread(target=server.serve_forever,daemon=True).start()
    base=f'http://127.0.0.1:{server.server_port}'
    output=Path('.impeccable/review'); output.mkdir(parents=True,exist_ok=True)
    try:
        with sync_playwright() as p:
            browser=p.chromium.launch()
            page=browser.new_page(accept_downloads=True)
            errors=[]; page.on('pageerror',lambda error:errors.append(str(error)))
            page.goto(base+'/screen/save-ui/OD')
            page.evaluate("window.evtSource.close(); window.renderDistance({valid:true,cm:12.5,estimated:true,stable:false})")
            assert page.locator('#distance-val').inner_text() == '12.50'
            assert 'Estimated' in page.locator('#distance-badge').inner_text()
            assert page.locator('#btn-record').is_enabled()
            assert 'not measured' in page.locator('#stability-text').inner_text()
            for width,height,name in ((1280,900,'desktop'),(390,844,'mobile')):
                page.set_viewport_size(dict(width=width,height=height))
                assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
                page.screenshot(path=str(output/(name+'-estimated-distance.png')),full_page=True)
            page.evaluate("window.renderDistance({valid:true,cm:20,estimated:false,stable:false})")
            assert page.locator('#btn-record').is_disabled()
            page.evaluate("window.renderDistance({valid:false})")
            assert page.locator('#btn-record').is_disabled()
            page.goto(base+'/screen/save-ui/result')
            page.locator('#storage-device-label').fill('TEST research laptop')
            page.locator('#storage-prepare').click()
            page.locator('#storage-download').wait_for(state='visible')
            with page.expect_download() as download:
                page.locator('#storage-download').click()
            saved=root/'browser-saved.zip'; download.value.save_as(saved)
            transfers=page.request.get(base+'/api/sessions/save-ui/transfers').json()['transfers']
            assert transfers[0]['state']=='ready'
            with saved.open('rb') as handle:
                verify_archive(handle,transfers[0]['manifest_sha256'],
                    expected_archive_sha256=transfers[0]['archive_sha256'],
                    expected_archive_bytes=transfers[0]['archive_bytes'])
            assert (folder/'0000.jpg').is_file(), 'Browser download must retain Pi originals'
            for name,width in [('desktop',1440),('mobile',390)]:
                page.set_viewport_size({'width':width,'height':900})
                page.locator('#storage-transfer').scroll_into_view_if_needed()
                page.screenshot(path=str(output/(name+'-storage.png')))
                assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
            result=receive_session(base,'save-ui',root/'verified-laptop',device_label='TEST verified laptop',release=True)
            assert result['pi_files_released'] is True
            assert Path(result['path']).is_file()
            assert not (folder/'0000.jpg').exists()
            page.reload()
            page.locator('#storage-locations').get_by_text('TEST verified laptop',exact=False).wait_for()
            assert 'TEST verified laptop' in page.locator('.eye-card').first.inner_text()
            assert not errors,errors
            browser.close()
    finally:
        server.shutdown(); server.server_close()
    print('PASS: browser download retained source; local readback verified; explicit release freed only exported files; saved location and desktop/mobile UI verified')
