"""Check the running disconnected operator interface without creating records."""
from pathlib import Path
from playwright.sync_api import sync_playwright

origin = 'http://127.0.0.1:5080'
output = Path('output/operator-review'); output.mkdir(parents=True, exist_ok=True)
with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page()
    errors = []
    page.on('pageerror', lambda error: errors.append(str(error)))
    for width,height in ((320,568),(390,844),(768,1024),(1440,900)):
        page.set_viewport_size(dict(width=width,height=height))
        for route in ('/', '/history', '/settings'):
            page.goto(origin+route, wait_until='domcontentloaded')
            page.evaluate('document.fonts.ready')
            assert 'MOCK DATA' not in page.locator('body').inner_text()
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
            if route == '/':
                assert page.get_by_role('heading', name='Connect the Raspberry Pi').is_visible()
                assert page.locator('#btn-start-screening').get_attribute('aria-disabled') == 'true'
                assert page.locator('#btn-start-screening').evaluate('el => el.tagName') == 'BUTTON'
                assert page.locator('#btn-start-screening').is_disabled()
                assert page.locator('#status-grid').count() == 0
                page.locator('.operator-guide summary').click()
                assert 'no averaging is needed' in page.locator('.operator-guide').inner_text()
                if width in (390,1440): page.screenshot(path=str(output/f'home-{width}.png'),full_page=True)
        print(f'PASS: clean operator screens at {width}px', flush=True)
    assert page.request.get(origin+'/api/sessions').json() == []
    assert not errors, errors
    browser.close()
print('PASS: no sample participants, no simulated status or JS errors; connection and operator guidance available.')
