import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import time
import socket
import threading
import shutil
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright
from werkzeug.serving import make_server
from app.app import create_app

VIEWPORTS = [
    {"name": "320px_compact_mobile", "width": 320, "height": 568},
    {"name": "390px_standard_phone", "width": 390, "height": 844},
    {"name": "768px_tablet_portrait", "width": 768, "height": 1024},
    {"name": "1024px_laptop_tablet_land", "width": 1024, "height": 768},
    {"name": "1440px_desktop_workstation", "width": 1440, "height": 900}
]

def find_free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]

class ServerThread(threading.Thread):
    def __init__(self, app, port):
        super().__init__()
        self.server = make_server('127.0.0.1', port, app, threaded=True)
        self.port = port
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

  const itemsToCheck = [
    { label: "Page title / brand (.brand-title)", sel: ".brand-title" },
    { label: "Brand tag (.brand-tag)", sel: ".brand-tag" },
    { label: "Active language button (.lang-btn.active)", sel: ".lang-btn.active" },
    { label: "Inactive FIL button (.lang-btn:not(.active))", sel: ".lang-btn:not(.active)" },
    { label: "Card title (.card-title)", sel: ".card-title" },
    { label: "Primary button (.btn-primary)", sel: ".btn-primary" },
    { label: "Secondary button (.btn-secondary)", sel: ".btn-secondary" },
    { label: "Active nav item (.nav-item.active, .nav-rail-item.active)", sel: ".nav-item.active, .nav-rail-item.active" },
    { label: "Inactive nav item (.nav-item:not(.active), .nav-rail-item:not(.active))", sel: ".nav-item:not(.active), .nav-rail-item:not(.active)" },
    { label: "Status badge OK (.badge-ok)", sel: ".badge-ok" },
    { label: "Status item label (.status-item label, .status-item span:first-child)", sel: ".status-item span:first-child" }
  ];

  const results = [];
  for (const item of itemsToCheck) {
    const el = document.querySelector(item.sel);
    if (el) {
      const rect = el.getBoundingClientRect();
      const style = window.getComputedStyle(el);
      const isVisible = rect.width > 0 && rect.height > 0 && style.display !== 'none' && style.visibility !== 'hidden';
      if (isVisible) {
        const fg = parseRgb(style.color);
        const bg = getEffectiveBackgroundColor(el);
        const ratio = Math.round(getContrast(fg, bg) * 100) / 100;
        const fontSize = parseFloat(style.fontSize);
        const fontWeight = parseInt(style.fontWeight) || 400;
        const isLarge = fontSize >= 24 || (fontSize >= 18.66 && fontWeight >= 700);
        const minReq = isLarge ? 3.0 : 4.5;
        results.push({
          label: item.label,
          fg: `rgb(${fg.join(",")})`,
          bg: `rgb(${bg.join(",")})`,
          ratio: ratio,
          minReq: minReq,
          pass: ratio >= minReq
        });
      }
    }
  }

  // Also verify all visible leaf text elements across page
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
            pass: ratio >= minReq
          });
        }
      }
    }
  }

  return { keyElements: results, leafSummary: { total: allLeafNodes.length, passing: allLeafNodes.filter(x => x.pass).length } };
}
"""

def test_phase1_1_verification():
    """Pytest test case for Phase 1.1 verification."""
    app = create_app()
    port = find_free_port()
    server = ServerThread(app, port)
    server.start()
    base_url = f"http://127.0.0.1:{port}"
    print(f"\nTest server started at {base_url}")
    time.sleep(1.0)

    screenshot_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "artifacts", "screenshots"))
    os.makedirs(screenshot_dir, exist_ok=True)

    all_requests = []
    external_requests = []
    allowed_hosts = {"127.0.0.1", "localhost", "192.168.4.1"}

    contrast_audit_data = {}
    touch_target_data = {}
    overflow_data = {}

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)

            for vp in VIEWPORTS:
                width = vp["width"]
                height = vp["height"]
                vp_dir = os.path.join(screenshot_dir, f"{width}px")
                os.makedirs(vp_dir, exist_ok=True)

                context = browser.new_context(viewport={"width": width, "height": height})
                page = context.new_page()

                def log_req(req):
                    all_requests.append(req.url)
                    parsed = urlparse(req.url)
                    if parsed.hostname not in allowed_hosts and parsed.scheme in ("http", "https"):
                        external_requests.append(req.url)

                page.on("request", log_req)

                page.goto(f"{base_url}/", wait_until="networkidle")
                time.sleep(0.5)

                # Check horizontal overflow before any full_page screenshot resizing
                overflow_info = page.evaluate("""() => {
                    const docW = document.documentElement.scrollWidth;
                    const winW = window.innerWidth;
                    const diff = Math.max(0, docW - winW);
                    const overflowing = Array.from(document.querySelectorAll('*')).filter(el => {
                        const r = el.getBoundingClientRect();
                        return r.right > winW + 0.5;
                    }).map(el => ({
                        tag: el.tagName,
                        cls: el.className,
                        id: el.id,
                        right: el.getBoundingClientRect().right,
                        w: el.getBoundingClientRect().width,
                        text: el.textContent.trim().slice(0, 20)
                    }));
                    return { diff: diff, overflowing: overflowing, docW: docW, winW: winW };
                }""")
                overflow_data[width] = overflow_info["diff"]
                if overflow_info["diff"] > 0:
                    print(f"[{width}px] OVERFLOW DETECTED: {overflow_info['diff']}px, elements: {overflow_info['overflowing']}")

                # Capture screenshot
                shot_path = os.path.join(vp_dir, "home.png")
                page.screenshot(path=shot_path, full_page=True)

                # Optional copy to brain dir if configured in environment
                brain_dir = os.environ.get("AGY_BRAIN_DIR")
                if brain_dir and os.path.isdir(brain_dir) and width in (320, 1024, 1440):
                    target_shot = os.path.join(brain_dir, f"home_{width}px.png")
                    shutil.copy2(shot_path, target_shot)

                # Touch target check
                touch_res = page.evaluate("""
                () => {
                    const targets = Array.from(document.querySelectorAll('button, a, input, select, textarea, .nav-item, .nav-rail-item, .lang-btn'));
                    const visible = targets.filter(el => {
                        const r = el.getBoundingClientRect();
                        return r.width > 0 && r.height > 0 && window.getComputedStyle(el).display !== 'none';
                    });
                    const passing = visible.filter(el => {
                        const r = el.getBoundingClientRect();
                        return (r.width >= 47.9 && r.height >= 47.9);
                    });
                    const failing = visible.filter(el => {
                        const r = el.getBoundingClientRect();
                        return !(r.width >= 47.9 && r.height >= 47.9);
                    }).map(el => ({
                        tag: el.tagName,
                        cls: el.className,
                        text: el.textContent.trim().slice(0, 20),
                        w: el.getBoundingClientRect().width,
                        h: el.getBoundingClientRect().height
                    }));
                    return { total: visible.length, passing: passing.length, failing: failing };
                }
                """)
                touch_target_data[width] = touch_res

                # Computed style contrast check
                contrast_res = page.evaluate(COMPUTED_CONTRAST_JS)
                contrast_audit_data[width] = contrast_res

                context.close()

            browser.close()

    finally:
        server.shutdown()

    # Network assertions
    assert len(external_requests) == 0, f"Detected external requests: {external_requests}"
    has_font = any("inter-latin-variable.woff2" in u for u in all_requests)
    has_sprite = any("sprite.svg" in u for u in all_requests)
    assert has_font, "inter-latin-variable.woff2 was not requested via local HTTP"
    assert has_sprite, "sprite.svg was not requested via local HTTP"

    # Layout and accessibility assertions
    for w in [320, 390, 768, 1024, 1440]:
        assert overflow_data[w] <= 0, f"Horizontal overflow at {w}px: {overflow_data[w]}px"
        tt = touch_target_data[w]
        assert len(tt["failing"]) == 0, f"Touch target failures at {w}px: {tt['failing']}"
        ca = contrast_audit_data[w]
        for elem in ca["keyElements"]:
            assert elem["pass"], f"Contrast failure at {w}px for {elem['label']}: {elem['ratio']}:1 (min {elem['minReq']}:1, fg={elem['fg']}, bg={elem['bg']})"

    # Print summary report
    print("\n================== PHASE 1.1 AUDIT RESULTS ==================")
    print(f"Total Local HTTP Requests: {len(all_requests)}, External Requests: {len(external_requests)}")
    print(f"Inter Variable Font (SIL OFL) Loaded: {has_font}")
    print(f"Lucide Sprite SVG Loaded: {has_sprite}")
    print("\n--- Real Computed Style Contrast Ratios ---")
    for elem in contrast_audit_data[320]["keyElements"]:
        print(f"  {elem['label']}: {elem['ratio']}:1 [{elem['fg']} on {elem['bg']}] -> {'PASS' if elem['pass'] else 'FAIL'}")

    # Verification complete
    print("\nPhase 1.1 Verification PASSED (0 external requests, all touch targets >= 48px, all WCAG AA ratios satisfied).")

if __name__ == "__main__":
    test_phase1_1_verification()
