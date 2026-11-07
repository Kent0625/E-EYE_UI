"""Local browser verification with explicitly synthetic research data."""
import tempfile
from pathlib import Path
import threading
from werkzeug.serving import make_server
from playwright.sync_api import sync_playwright
from PIL import Image, ImageDraw, ImageFont
from app import store
from app.app import create_app

with tempfile.TemporaryDirectory() as temporary:
    store.DATABASE_PATH = str(Path(temporary)/'test.db')
    app = create_app()
    store.set_setting('research_mode','1')
    store.create_session(dict(id='ui-test', participant_code='TEST-RECEIPT-001',
        consent_age=True, consent_signed=True, eyes={'OD':{'status':'captured','frames_total':12,
        'frames_used':0,'quality_status':'unavailable'},'OS':{'status':'not_recorded'}}))
    server = make_server('127.0.0.1',0,app,threaded=True)
    threading.Thread(target=server.serve_forever,daemon=True).start()
    output = Path('.impeccable/review'); output.mkdir(parents=True,exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        errors=[]
        page.on('pageerror',lambda error: errors.append(str(error)))
        page.goto(f'http://127.0.0.1:{server.server_port}/screen/ui-test/result')
        page.locator('#reference-method').select_option('manual')
        page.locator('#gt-od-sphere').fill('-1.25')
        page.locator('#gt-od-cylinder').fill('-0.50')
        page.locator('#gt-confirmed').check()
        page.locator('#btn-save-ground-truth').click()
        page.locator('#gt-save-feedback').filter(has_text='Confirmed ground truth saved').wait_for()
        for name,width in [('desktop',1440),('mobile',390)]:
            page.set_viewport_size({'width':width,'height':900})
            page.evaluate('scrollTo(0,0)')
            page.wait_for_timeout(200)
            page.screenshot(path=str(output/(name+'.png')),full_page=True)
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), name+' overflows'
        page.reload()
        assert page.locator('#gt-od-sphere').input_value() == '-1.25'
        photo = Path(temporary)/'synthetic-receipt.png'
        image = Image.new('RGB',(1200,650),'white')
        draw = ImageDraw.Draw(image)
        font = ImageFont.truetype('C:/Windows/Fonts/consola.ttf',42)
        draw.multiline_text((40,40),'SYNTHETIC TEST RECEIPT\nREFRACTION\nOD SPH CYL AX\nAVG -1.25 -0.50 90\nOS SPH CYL AX\nAVG +0.25 -0.25 90',font=font,fill='black',spacing=22)
        image.save(photo)
        page.locator('#receipt-file-input').set_input_files(str(photo))
        page.locator('#receipt-preview').wait_for(state='visible')
        page.locator('#receipt-read-button').click()
        page.wait_for_function("!document.querySelector('#receipt-read-button').disabled",timeout=120000)
        transcription = page.locator('#receipt-ocr-text').inner_text()
        print('OCR transcription:',repr(transcription))
        if page.locator('#gt-od-sphere').input_value():
            assert page.locator('#gt-od-sphere').input_value() == '-1.25'
        else:
            assert 'ambiguous' in page.locator('#receipt-status').inner_text()
        assert not page.locator('#gt-confirmed').is_checked()
        for name,width in [('desktop',1440),('mobile',390)]:
            page.set_viewport_size({'width':width,'height':900})
            page.locator('#ground-truth-section').scroll_into_view_if_needed()
            page.wait_for_timeout(200)
            page.screenshot(path=str(output/(name+'-receipt.png')))
        page.locator('#reference-method').select_option('three_readings')
        page.screenshot(path=str(output/'mobile-three-readings.png'))
        assert store.get_session('ui-test')['eyes']['OD']['status']=='captured'
        assert not errors, errors
        browser.close()
    server.shutdown()
    server.server_close()
    print('PASS: confirmation, reload persistence, capture preserved, local OCR completion/fallback, desktop/mobile layout and no JS errors')
