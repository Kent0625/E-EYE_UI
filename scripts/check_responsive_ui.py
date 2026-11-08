"""Exercise the existing operator interface without Pi hardware or live records."""
import os
from pathlib import Path
import sys
import tempfile
import threading
from playwright.sync_api import sync_playwright
from werkzeug.serving import make_server
from app import store
from app.app import create_app


def run():
    baseline = '--baseline' in sys.argv
    output = Path('output/responsive-review'); output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as temporary:
        store.DATABASE_PATH = str(Path(temporary)/'demo.db')
        os.environ['EEYE_RECEIPTS'] = str(Path(temporary)/'receipts')
        os.environ['EEYE_DATA'] = str(Path(temporary)/'data')
        app = create_app(); store.set_setting('research_mode', '1')
        server = make_server('127.0.0.1', 0, app, threaded=True)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        origin = 'http://127.0.0.1:' + str(server.server_port)
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch()
                page = browser.new_page()
                failures = []
                errors = []
                external = []
                page.on('pageerror', lambda error: errors.append(str(error)))
                page.on('request', lambda request: external.append(request.url) if request.url.startswith(('http:','https:')) and not request.url.startswith(origin+'/') else None)
                for width,height in ((320,568),(390,844),(768,1024),(1024,768),(1440,900),(844,390)):
                    page.set_viewport_size(dict(width=width,height=height))
                    for route,name in (('/','home'),('/screen/new','new'),('/screen/s_mock_refer/OD','record'),('/screen/s_mock_refer/result','result'),('/history','history'),('/settings','settings')):
                        page.goto(origin+route, wait_until='domcontentloaded')
                        page.locator('#main-content').wait_for()
                        page.evaluate('document.fonts.ready')
                        overflow = page.evaluate('document.documentElement.scrollWidth > innerWidth')
                        if overflow: failures.append(f'{name} overflows at {width}x{height}')
                        if width in (320,1440) and name in ('record','result','home'):
                            page.screenshot(path=str(output/(('before-' if baseline else '')+f'{name}-{width}.png')),full_page=True)
                        if name == 'record':
                            page.evaluate('window.evtSource.close(); window.renderDistance({valid:false})')
                            reason = page.locator('#record-disabled-reason')
                            if not reason.is_visible(): failures.append(f'Disabled reason hidden at {width}x{height}')
                            if not page.locator('.brand-tag').is_visible(): failures.append(f'Demo label hidden at {width}x{height}')
                    print(f'Checked {width}x{height}', flush=True)
                if not baseline:
                    page.set_viewport_size(dict(width=390,height=844))
                    page.goto(origin+'/screen/new')
                    page.locator('#input-code').fill('TEST-RESPONSIVE-001')
                    assert page.locator('#btn-continue').is_disabled()
                    page.locator('#chk-age').check(); page.locator('#chk-consent').check()
                    page.locator('#btn-continue').click()
                    page.wait_for_url('**/OD')
                    print('PASS: consent gating and new demo session', flush=True)
                    page.add_init_script('''
                        window.__sources=[];
                        window.EventSource=class {
                          constructor(url){ this.url=url; window.__sources.push(this); }
                          close(){ this.closed=true; }
                        };
                    ''')
                    page.goto(origin+'/screen/s_mock_refer/processing?eye=OD')
                    page.wait_for_function('window.__sources.length === 1')
                    emit = "data => window.__sources.at(-1).onmessage({data:JSON.stringify(data)})"
                    phases=dict(saving='complete',quality='running',prediction='unavailable')
                    page.evaluate(emit,dict(done=False,processing_elapsed_s=2,phases=phases,label='Checking recorded frames.'))
                    assert page.locator('#phase-prediction').get_attribute('data-state') == 'unavailable'
                    assert page.locator('#phase-quality').get_attribute('data-state') == 'running'
                    assert page.locator('#processing-elapsed').inner_text().startswith('2.')
                    for width,height in ((390,844),(1440,900)):
                        page.set_viewport_size(dict(width=width,height=height))
                        page.screenshot(path=str(output/f'processing-{width}.png'),full_page=True)
                    page.evaluate('window.__sources.at(-1).onerror()')
                    assert page.locator('#processing-recovery').is_visible()
                    assert page.locator('#processing-record-link').is_visible()
                    assert page.locator('.processing-spinner-wrapper').is_hidden()
                    page.locator('#processing-retry').click()
                    assert page.evaluate('window.__sources.length') == 2
                    page.evaluate("window.dispatchEvent(new PageTransitionEvent('pagehide', {persisted:true})); window.dispatchEvent(new PageTransitionEvent('pageshow', {persisted:true}))")
                    assert page.evaluate('window.__sources.length') == 3
                    page.evaluate(emit,dict(done=True,status='retake_needed',processing_elapsed_s=2.25,
                        phases=dict(saving='complete',quality='failed',prediction='unavailable'),label='Camera stopped during capture.'))
                    assert page.locator('#retake-view').is_visible()
                    assert page.locator('#retake-message').inner_text() == 'Camera stopped during capture.'
                    assert page.locator('#btn-retake').get_attribute('href').endswith('/OD')
                    page.goto(origin+'/screen/s_mock_refer/processing?eye=OD')
                    page.wait_for_function('window.__sources.length === 1')
                    page.evaluate(emit,dict(done=True,status='captured',processing_elapsed_s=1,phases=phases,label='Capture saved.'))
                    page.wait_for_url('**/OS')
                    page.goto(origin+'/screen/s_mock_refer/processing?eye=OS')
                    page.wait_for_function('window.__sources.length === 1')
                    page.evaluate(emit,dict(done=True,status='captured',processing_elapsed_s=1,phases=phases,label='Capture saved.'))
                    page.wait_for_url('**/result')
                    page.set_viewport_size(dict(width=390,height=300))
                    page.goto(origin+'/screen/new')
                    page.locator('#input-code').focus()
                    assert page.locator('.sticky-action-bar').evaluate("el => getComputedStyle(el).position") == 'static'
                    page.set_viewport_size(dict(width=640,height=450))
                    page.goto(origin+'/screen/s_mock_refer/result')
                    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), page.evaluate("[...document.querySelectorAll('body *')].filter(e=>e.getBoundingClientRect().right>innerWidth+1).slice(0,8).map(e=>({tag:e.tagName,cl:e.className,right:e.getBoundingClientRect().right}))")
                    page.emulate_media(reduced_motion='reduce')
                    page.goto(origin+'/screen/s_mock_refer/processing')
                    assert page.locator('.spinner-icon').evaluate("el => getComputedStyle(el).animationName") == 'none'
                    assert not errors, errors
                    assert not external, external
                    print('PASS: actual stage rendering, timer, disconnect/retry, retake, both-eye routing, keyboard viewport, zoom-sized layout, reduced motion, no JS errors or external requests',flush=True)
                browser.close()
                if baseline: print('BASELINE:', failures)
                else: assert not failures, '\n'.join(failures)
        finally: server.shutdown()


if __name__ == '__main__': run()
