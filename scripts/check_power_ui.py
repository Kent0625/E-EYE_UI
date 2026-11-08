"""Check shutdown controls with intercepted responses; never power off a machine."""
import os
from pathlib import Path
import tempfile
import threading
from playwright.sync_api import sync_playwright
from werkzeug.serving import make_server
os.environ['EEYE_MOCK'] = '1'
from app import store
from app.app import create_app

with tempfile.TemporaryDirectory() as temporary:
    store.DATABASE_PATH = str(Path(temporary)/'test.db')
    os.environ['EEYE_DATA'] = str(Path(temporary)/'data')
    os.environ['EEYE_RECEIPTS'] = str(Path(temporary)/'receipts')
    app = create_app()
    server = make_server('127.0.0.1', 0, app, threaded=True)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = 'http://127.0.0.1:'+str(server.server_port)
    output = Path('output/power-review'); output.mkdir(parents=True, exist_ok=True)
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page()
            calls = []; errors = []
            page.on('pageerror', lambda error: errors.append(str(error)))
            page.goto(base+'/settings')
            assert page.locator('#btn-shutdown').is_disabled()
            page.route('**/api/device/power', lambda route: route.fulfill(json={'available':True,'pending':False}))
            page.route('**/api/device/shutdown', lambda route: (calls.append(route.request.post_data_json), route.fulfill(status=202,json={'pending':True})))
            for width,height in ((390,844),(1440,900)):
                page.set_viewport_size(dict(width=width,height=height))
                page.goto(base+'/settings')
                page.wait_for_function("!document.querySelector('#btn-shutdown').disabled")
                page.locator('#btn-shutdown').click()
                assert page.locator('#shutdown-dialog').is_visible()
                assert page.locator('#btn-cancel-shutdown').evaluate('el => el === document.activeElement')
                assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
                page.screenshot(path=str(output/f'confirmation-{width}.png'))
                page.keyboard.press('Escape')
                assert page.locator('#shutdown-dialog').is_hidden()
                assert not calls
                page.locator('#btn-shutdown').click()
                page.locator('#btn-cancel-shutdown').click()
                assert not calls
            page.locator('#btn-shutdown').click()
            page.locator('#btn-confirm-shutdown').click()
            page.wait_for_function("document.querySelector('#btn-shutdown').disabled")
            assert calls == [{'confirmed':True}]
            assert 'Shutdown requested' in page.locator('#shutdown-hint').inner_text()
            assert page.locator('#shutdown-dialog').is_hidden()
            page.unroute('**/api/device/shutdown')
            page.route('**/api/device/shutdown', lambda route: route.fulfill(status=409,json={'error':'The device is busy. Wait for capture to finish.'}))
            page.reload()
            page.wait_for_function("!document.querySelector('#btn-shutdown').disabled")
            page.locator('#btn-shutdown').click()
            page.locator('#btn-confirm-shutdown').click()
            page.wait_for_function("document.querySelector('#shutdown-hint').textContent.includes('device is busy')")
            assert page.locator('#btn-shutdown').is_enabled()
            assert not errors, errors
            browser.close()
        print('PASS: unavailable control, mobile/desktop confirmation, focus, Escape/cancel without requests, one confirmed request, busy-error recovery; no real shutdown called.')
    finally: server.shutdown()
