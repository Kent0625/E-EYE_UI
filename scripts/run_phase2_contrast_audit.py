import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import time
import socket
import threading
import json
import shutil
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
  function getCssSelector(el) {
    if (el.id) return '#' + el.id;
    let path = [];
    let cur = el;
    while (cur && cur.nodeType === Node.ELEMENT_NODE && cur !== document.body && cur !== document.documentElement) {
      let selector = cur.tagName.toLowerCase();
      if (cur.id) {
        selector = '#' + cur.id;
        path.unshift(selector);
        break;
      } else {
        let sib = cur, nth = 1;
        while ((sib = sib.previousElementSibling)) {
          if (sib.tagName.toLowerCase() === selector) nth++;
        }
        if (nth > 1) selector += `:nth-of-type(${nth})`;
      }
      path.unshift(selector);
      cur = cur.parentElement;
    }
    return path.join(' > ');
  }

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
        if (style.display !== "none" && style.visibility !== "hidden" && style.opacity !== "0") {
          const fg = parseRgb(style.color);
          const bg = getEffectiveBackgroundColor(n);
          const ratio = Math.round(getContrast(fg, bg) * 100) / 100;
          const fontSize = parseFloat(style.fontSize);
          const fontWeight = parseInt(style.fontWeight) || 400;
          const isLarge = fontSize >= 24 || (fontSize >= 18.66 && fontWeight >= 700);
          const minReq = isLarge ? 3.0 : 4.5;
          allLeafNodes.push({
            selector: getCssSelector(n),
            tag: n.tagName.toLowerCase(),
            text: n.textContent.trim().replace(/\\s+/g, ' ').slice(0, 30),
            fg: `rgb(${fg.join(",")})`,
            bg: `rgb(${bg.join(",")})`,
            ratio: ratio,
            minReq: minReq,
            pass: ratio >= minReq,
            fontSize: `${fontSize}px`,
            fontWeight: fontWeight
          });
        }
      }
    }
  }

  const failing = allLeafNodes.filter(x => !x.pass);
  return {
    elements: allLeafNodes,
    total: allLeafNodes.length,
    passing: allLeafNodes.length - failing.length,
    failing: failing
  };
}
"""

def run_comprehensive_audit():
    app = create_app()
    port = find_free_port()
    server = ServerThread(app, port)
    server.start()
    base_url = f"http://127.0.0.1:{port}"
    time.sleep(0.5)

    states = [
        # (screen_name, state_name, path, action)
        ("Align & Record", "Too Close (8.5 cm)", "/screen/s_mock_refer/OD", lambda p: (
            p.evaluate("if(window.evtSource) window.evtSource.close()"),
            p.evaluate("renderDistance({ cm: 8.5, valid: true })")
        )),
        ("Align & Record", "Distance OK (12.5 cm)", "/screen/s_mock_refer/OD", lambda p: (
            p.evaluate("if(window.evtSource) window.evtSource.close()"),
            p.evaluate("renderDistance({ cm: 12.5, valid: true })"),
            time.sleep(1.1),
            p.evaluate("renderDistance({ cm: 12.5, valid: true })")
        )),
        ("Align & Record", "Too Far (18.0 cm)", "/screen/s_mock_refer/OD", lambda p: (
            p.evaluate("if(window.evtSource) window.evtSource.close()"),
            p.evaluate("renderDistance({ cm: 18.0, valid: true })")
        )),
        ("Align & Record", "No Reading (0.0 cm / invalid)", "/screen/s_mock_refer/OD", lambda p: (
            p.evaluate("if(window.evtSource) window.evtSource.close()"),
            p.evaluate("renderDistance({ cm: 0.0, valid: false })")
        )),
        ("Align & Record", "Record Disabled Initial", "/screen/s_mock_refer/OD", lambda p: (
            p.evaluate("if(window.evtSource) window.evtSource.close()"),
            p.evaluate("renderDistance({ cm: 12.5, valid: true })")
        )),
        ("Align & Record", "Countdown Running", "/screen/s_mock_refer/OD", lambda p: (
            p.evaluate("if(window.evtSource) window.evtSource.close()"),
            p.evaluate("renderDistance({ cm: 12.5, valid: true })"),
            time.sleep(1.1),
            p.evaluate("renderDistance({ cm: 12.5, valid: true })"),
            p.click("#btn-record"),
            p.wait_for_selector("#recording-overlay", state="visible")
        )),
        ("Align & Record", "Preview Unavailable", "/screen/s_mock_refer/OD", lambda p: (
            p.evaluate("if(window.evtSource) window.evtSource.close()"),
            p.evaluate("document.getElementById('stream-fallback').style.display = 'flex'")
        )),
        ("New Screening", "Empty Form", "/screen/new", lambda p: None),
        ("New Screening", "Consent Checked", "/screen/new", lambda p: (p.check("#chk-age"), p.check("#chk-consent"))),
        ("Processing", "Running Steps", "/screen/s_mock_refer/processing?eye=OD", lambda p: time.sleep(0.5)),
        ("Processing", "Retake Fixture", "/screen/s_mock_retake/processing?eye=OS", lambda p: p.wait_for_selector("#retake-view", state="visible", timeout=6000)),
        ("Home", "Status & Readiness", "/", lambda p: None),
        ("History", "Session Log", "/history", lambda p: None),
        ("Settings", "Configuration", "/settings", lambda p: None)
    ]

    all_raw_elements = []
    summary_by_state = {}
    grand_total = 0
    grand_passing = 0
    grand_failing = 0

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            for scr_name, state_name, path, action in states:
                state_key = f"{scr_name} - {state_name}"
                summary_by_state[state_key] = {}

                for vp in VIEWPORTS:
                    w = vp["width"]
                    h = vp["height"]
                    ctx = browser.new_context(viewport={"width": w, "height": h})
                    page = ctx.new_page()
                    page.goto(f"{base_url}{path}", wait_until="networkidle")
                    time.sleep(0.25)
                    action(page)
                    time.sleep(0.2)

                    res = page.evaluate(COMPUTED_CONTRAST_JS)
                    for item in res["elements"]:
                        item["screen"] = scr_name
                        item["state"] = state_name
                        item["viewport"] = vp["name"]
                        item["viewport_width"] = w
                        all_raw_elements.append(item)

                    grand_total += res["total"]
                    grand_passing += res["passing"]
                    grand_failing += len(res["failing"])
                    summary_by_state[state_key][vp["name"]] = {
                        "total": res["total"],
                        "passing": res["passing"],
                        "failing_count": len(res["failing"]),
                        "failing_details": res["failing"]
                    }
                    ctx.close()
            browser.close()
    finally:
        server.shutdown()

    # Save raw audit output to docs/contrast_audit_raw.json and artifact dir
    docs_output = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "docs", "contrast_audit_raw.json"))
    brain_dir = os.environ.get("AGY_BRAIN_DIR")
    
    os.makedirs(os.path.dirname(docs_output), exist_ok=True)
    if brain_dir:
        os.makedirs(brain_dir, exist_ok=True)

    audit_payload = {
        "metadata": {
            "date": "2026-10-19",
            "standard": "WCAG 2.1 AA",
            "grand_total_checked": grand_total,
            "grand_passing": grand_passing,
            "grand_failing": grand_failing,
            "total_audit_records": len(all_raw_elements)
        },
        "summary_by_state": summary_by_state,
        "raw_elements": all_raw_elements
    }

    with open(docs_output, "w", encoding="utf-8") as f:
        json.dump(audit_payload, f, indent=2)
    if brain_dir:
        shutil.copy2(docs_output, os.path.join(brain_dir, "contrast_audit_raw.json"))

    print("\n================== FULL CONTRAST AUDIT ACROSS ALL STATES ==================")
    print(f"Grand Total Elements Checked: {grand_total}")
    print(f"Passing: {grand_passing} | Failing: {grand_failing}")
    print(f"Raw audit output successfully written to:")
    print(f"  {docs_output}")
    print(f"  {brain_output}")

    if grand_failing > 0:
        print("\nFAILING ELEMENTS DETECTED:")
        for el in all_raw_elements:
            if not el["pass"]:
                print(f"  [{el['screen']} | {el['state']} | {el['viewport']}] {el['selector']} -> fg:{el['fg']} on bg:{el['bg']}, ratio:{el['ratio']} (req:{el['minReq']}) text: '{el['text']}'")
    else:
        print("\nAll text elements across ALL states and viewports PASS WCAG AA minimum contrast!")

if __name__ == "__main__":
    run_comprehensive_audit()
