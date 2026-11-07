"""Verify actual offline OCR and confirmed pairing using synthetic research data."""
import hashlib
import os
from pathlib import Path
import tempfile
import threading
from urllib.parse import urlsplit

from PIL import Image, ImageDraw, ImageFont
from playwright.sync_api import sync_playwright
from werkzeug.serving import make_server

from app import store
from app.app import create_app


with tempfile.TemporaryDirectory() as temporary:
    store.DATABASE_PATH = str(Path(temporary) / 'test.db')
    os.environ['EEYE_RECEIPTS'] = str(Path(temporary) / 'receipts')
    app = create_app()
    store.set_setting('research_mode', '1')
    store.create_session(dict(id='ui-test', participant_code='TEST-RECEIPT-001',
        consent_age=True, consent_signed=True, eyes={
            'OD': {'status': 'captured', 'frames_total': 12, 'frames_used': 0, 'quality_status': 'unavailable'},
            'OS': {'status': 'not_recorded'},
        }))
    server = make_server('127.0.0.1', 0, app, threaded=True)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    origin = f'http://127.0.0.1:{server.server_port}'
    output = Path('.impeccable/review')
    output.mkdir(parents=True, exist_ok=True)
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            context = browser.new_context()
            page = context.new_page()
            errors, external_requests = [], []
            page.on('pageerror', lambda error: errors.append(str(error)))

            def local_requests_only(route):
                if urlsplit(route.request.url).netloc != urlsplit(origin).netloc:
                    external_requests.append(route.request.url)
                    route.abort()
                else:
                    route.continue_()

            context.route('http://**/*', local_requests_only)
            context.route('https://**/*', local_requests_only)
            page.goto(origin + '/screen/ui-test/result')
            page.locator('#reference-method').select_option('manual')
            page.locator('#gt-od-sphere').fill('-1.25')
            page.locator('#gt-od-cylinder').fill('-0.50')
            page.locator('#gt-confirmed').check()
            page.locator('#btn-save-ground-truth').click()
            page.locator('#gt-save-feedback').filter(has_text='Confirmed ground truth saved').wait_for()
            for name, width in [('desktop', 1440), ('mobile', 390)]:
                page.set_viewport_size({'width': width, 'height': 900})
                page.evaluate('scrollTo(0, 0)')
                page.screenshot(path=str(output / (name + '.png')), full_page=True)
                assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), name + ' overflows'
            page.reload()
            assert page.locator('#gt-od-sphere').input_value() == '-1.25'

            photo = Path(temporary) / 'synthetic-receipt.png'
            image = Image.new('RGB', (1200, 650), 'white')
            draw = ImageDraw.Draw(image)
            font = ImageFont.truetype('C:/Windows/Fonts/consola.ttf', 42)
            draw.multiline_text((40, 40),
                'SYNTHETIC TEST RECEIPT\nREFRACTION\nRIGHT EYE (OD) SPH CYL AX\n'
                'AVG -1.25 -0.50 90\nLEFT EYE (OS) SPH CYL AX\nAVG +0.25 -0.25 90',
                font=font, fill='black', spacing=22)
            image.save(photo)
            page.locator('#receipt-file-input').set_input_files(str(photo))
            page.locator('#receipt-preview').wait_for(state='visible')
            page.locator('#receipt-read-button').click()
            page.wait_for_function("!document.querySelector('#receipt-read-button').disabled", timeout=120000)
            # inner_text() is empty while the transcription's <details> is collapsed.
            transcription = page.locator('#receipt-ocr-text').text_content()
            assert 'SYNTHETIC TEST RECEIPT' in transcription, repr(transcription)
            assert '-1.25' in transcription and '+0.25' in transcription, repr(transcription)
            assert page.locator('#gt-od-sphere').input_value() == '-1.25'
            assert page.locator('#gt-od-cylinder').input_value() == '-0.5'
            assert page.locator('#gt-os-sphere').input_value() == '0.25'
            assert page.locator('#gt-os-cylinder').input_value() == '-0.25'
            assert page.locator('#reference-method').input_value() == 'printed_average'
            assert not page.locator('#gt-confirmed').is_checked()
            assert page.locator('#btn-save-ground-truth').is_disabled()
            before_confirmation = store.get_session('ui-test')
            assert before_confirmation['eyes']['OD']['ground_truth']['reference_method'] == 'manual'
            assert 'ground_truth' not in before_confirmation['eyes']['OS']

            for name, width in [('desktop', 1440), ('mobile', 390)]:
                page.set_viewport_size({'width': width, 'height': 900})
                page.locator('#ground-truth-section').scroll_into_view_if_needed()
                page.screenshot(path=str(output / (name + '-receipt.png')))
                assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')

            page.locator('#gt-confirmed').check()
            page.locator('#btn-save-ground-truth').click()
            page.locator('#gt-save-feedback').filter(has_text='Confirmed ground truth saved').wait_for()
            session = store.get_session('ui-test')
            right = session['eyes']['OD']['ground_truth']
            left = session['eyes']['OS']['ground_truth']
            assert right['sphere_D'] == -1.25 and right['cylinder_D'] == -0.5
            assert left['sphere_D'] == 0.25 and left['cylinder_D'] == -0.25
            assert right['receipt_id'] == left['receipt_id']
            assert right['reference_method'] == left['reference_method'] == 'printed_average'
            assert session['eyes']['OD']['status'] == 'captured'
            with store.get_connection() as db:
                receipt = db.execute('SELECT * FROM receipts WHERE id = ?', (right['receipt_id'],)).fetchone()
                audits = db.execute('SELECT * FROM ground_truth_audit WHERE receipt_id = ?', (right['receipt_id'],)).fetchall()
            assert receipt['sha256'] == hashlib.sha256(photo.read_bytes()).hexdigest()
            assert len(audits) == 2
            assert all('-1.25' in entry['ocr_text'] and '+0.25' in entry['ocr_text'] for entry in audits)
            assert (Path(os.environ['EEYE_RECEIPTS']) / receipt['id']).read_bytes() == photo.read_bytes()
            page.reload()
            page.locator('#receipt-preview').wait_for(state='visible')
            assert page.locator('#gt-os-sphere').input_value() == '0.25'
            assert page.locator('#reference-method option[value="three_readings"]').count() == 0
            assert not errors, errors
            assert not external_requests, external_requests
            browser.close()
    finally:
        server.shutdown()
        server.server_close()
    print('PASS: actual local OCR for both eyes, explicit confirmation, original receipt linkage, '
          'audit, reload persistence, capture preserved, desktop/mobile layout, no external requests or JS errors')
