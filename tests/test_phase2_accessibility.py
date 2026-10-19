import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import time
import socket
import threading
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright
from werkzeug.serving import make_server
from app.app import create_app

VIEWPORTS = [
    {"name": "320px", "width": 320, "height": 568},
    {"name": "390px", "width": 390, "height": 844},
    {"name": "768px", "width": 768, "height": 1024},
    {"name": "1024px", "width": 1024, "height": 768},
    {"name": "1440px", "width": 1440, "height": 900}
]

def find_free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]

class ServerThread(threading.Thread):
    def __init__(self, app, port):
        super().__init__()
        self.server = make_server('127.0.0.1', port, app, threaded=True)
        self.daemon = True

    def run(self):
        self.server.serve_forever()

    def shutdown(self):
        self.server.shutdown()

COMPUTED_CONTRAST_JS = """
() => {
  function getEffectiveBackgroundColor(el) {
    let cur = el;
    while (cur && cur !== document.documentElement) {
      const bg = window.getComputedStyle(cur).backgroundColor;
      const match = bg.match(/rgba?\\((\\d+),\\s*(\\d+),\\s*(\\d+)(?:,\\s*([\\d.]+))?\\)/);
      if (match) {
        const a = match[4] !== undefined ? parseFloat(match[4]) : 1;
        if (a > 0.05) {
          return [parseInt(match[1]), parseInt(match[2]), parseInt(match[3])];
        }
      }
      cur = cur.parentElement;
    }
    return [255, 255, 255];
  }

  function getLuminance(r, g, b) {
    const a = [r, g, b].map(v => {
      v /= 255;
      return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4);
    });
    return a[0] * 0.2126 + a[1] * 0.7152 + a[2] * 0.0722;
  }

  function getContrast(rgb1, rgb2) {
    const l1 = getLuminance(rgb1[0], rgb1[1], rgb1[2]);
    const l2 = getLuminance(rgb2[0], rgb2[1], rgb2[2]);
    const lighter = Math.max(l1, l2);
    const darker = Math.min(l1, l2);
    return (lighter + 0.05) / (darker + 0.05);
  }

  function parseRgb(str) {
    const m = str.match(/rgba?\\((\\d+),\\s*(\\d+),\\s*(\\d+)/);
    return m ? [parseInt(m[1]), parseInt(m[2]), parseInt(m[3])] : [0, 0, 0];
  }

  const allLeafNodes = [];
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_ELEMENT);
  let n;
  while ((n = walker.nextNode())) {
    if (n.children.length === 0 && n.textContent.trim().length > 0) {
      const rect = n.getBoundingClientRect();
      if (rect.width > 0 && rect.height > 0) {
        const style = window.getComputedStyle(n);
        if (style.display !== "none" && style.visibility !== "hidden") {
          const fg = parseRgb(style.color);
          const bg = getEffectiveBackgroundColor(n);
          const ratio = Math.round(getContrast(fg, bg) * 100) / 100;
          const fontSize = parseFloat(style.fontSize);
          const fontWeight = parseInt(style.fontWeight) || 400;
          const isLarge = fontSize >= 24 || (fontSize >= 18.66 && fontWeight >= 700);
          const minReq = isLarge ? 3.0 : 4.5;
          allLeafNodes.push({
            text: n.textContent.trim().slice(0, 30),
            tag: n.tagName.toLowerCase(),
            ratio: ratio,
            minReq: minReq,
            pass: ratio >= minReq,
            fg: `rgb(${fg.join(",")})`,
            bg: `rgb(${bg.join(",")})`
          });
        }
      }
    }
  }

  const failing = allLeafNodes.filter(x => !x.pass);
  return { total: allLeafNodes.length, passing: allLeafNodes.length - failing.length, failing: failing };
}
"""

def test_phase2_screens_accessibility():
    """Verifies touch targets, computed contrast, and 0 overflow across Phase 2 screens."""
    app = create_app()
    port = find_free_port()
    server = ServerThread(app, port)
    server.start()
    base_url = f"http://127.0.0.1:{port}"
    time.sleep(1.0)

    screens = [
        {"name": "New Screening", "path": "/screen/new", "selector": "#btn-continue"},
        {"name": "Align and Record OD", "path": "/screen/s_mock_refer/OD", "selector": "#btn-record"},
        {"name": "Processing Screen", "path": "/screen/s_mock_refer/processing?eye=OD", "selector": "#step-extracting"}
    ]

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)

            for scr in screens:
                for vp in VIEWPORTS:
                    w = vp["width"]
                    h = vp["height"]
                    ctx = browser.new_context(viewport={"width": w, "height": h})
                    page = ctx.new_page()

                    page.goto(f"{base_url}{scr['path']}", wait_until="domcontentloaded")
                    page.wait_for_selector(scr["selector"], timeout=10000)
                    time.sleep(0.3)

                    # Check overflow
                    overflow = page.evaluate("() => Math.max(0, document.documentElement.scrollWidth - window.innerWidth)")
                    assert overflow == 0, f"[{scr['name']} @ {w}px] Overflow of {overflow}px detected"

                    # Check touch targets (interactive controls) per WCAG 2.5.8
                    touch_res = page.evaluate("""
                    () => {
                        const targets = Array.from(document.querySelectorAll('button, a, input, select, textarea, .nav-item, .nav-rail-item, .lang-btn, label:has(input[type="checkbox"])'));
                        const visible = targets.filter(el => {
                            // If it's a checkbox/radio wrapped by a label, the label defines the unified hit target
                            if ((el.type === 'checkbox' || el.type === 'radio') && el.closest('label')) {
                                return false;
                            }
                            const r = el.getBoundingClientRect();
                            return r.width > 0 && r.height > 0 && window.getComputedStyle(el).display !== 'none';
                        });
                        const failing = visible.filter(el => {
                            const r = el.getBoundingClientRect();
                            return !(r.width >= 47.9 && r.height >= 47.9);
                        }).map(el => ({
                            tag: el.tagName,
                            cls: el.className,
                            w: el.getBoundingClientRect().width,
                            h: el.getBoundingClientRect().height,
                            text: el.textContent.trim().slice(0, 20)
                        }));
                        return { total: visible.length, passing: visible.length - failing.length, failing: failing };
                    }
                    """)
                    assert len(touch_res["failing"]) == 0, f"[{scr['name']} @ {w}px] Touch target failures: {touch_res['failing']}"

                    # Check contrast
                    contrast_res = page.evaluate(COMPUTED_CONTRAST_JS)
                    assert len(contrast_res["failing"]) == 0, f"[{scr['name']} @ {w}px] Contrast failures: {contrast_res['failing']}"

                    ctx.close()

            browser.close()
    finally:
        server.shutdown()

    print("\nPhase 2 Screens Accessibility Audit (New Screening, Align & Record, Processing): ALL PASSED across all 5 viewports.")

if __name__ == "__main__":
    test_phase2_screens_accessibility()
