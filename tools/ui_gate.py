"""Rendered finish gate for the PlantDoctor UI (headless Chrome over CDP).

Drives every content state at each target viewport, saves screenshots to
design/evidence/, and runs automated checks: horizontal overflow, text contrast
(WCAG 1.4.3), target size (2.5.8, >= 24 px), visible focus (2.4.7/2.4.11),
accessible names, and keyboard order.

Usage:  .venv/bin/python tools/ui_gate.py      (server must be running on :8000)
"""
import asyncio
import base64
import json
import shutil
import subprocess
import tempfile
import time
import urllib.request
from pathlib import Path

import websockets

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "design" / "evidence"
URL = "http://127.0.0.1:8000/"
PORT = 9333
SAMPLE = ROOT / "app" / "static" / "samples" / "field-tomato-late-blight.jpg"
VIEWPORTS = {"390x844": (390, 844, 2, True), "1440x900": (1440, 900, 1, False)}

AUDIT_JS = r"""
(() => {
  const lum = (c) => { const m = c.match(/[\d.]+/g).map(Number); const [r,g,b] = m.slice(0,3).map(v => { v/=255; return v<=.03928? v/12.92 : ((v+.055)/1.055)**2.4; }); return [.2126*r+.7152*g+.0722*b, m[3] ?? 1]; };
  const bgOf = (el) => { for (let e = el; e; e = e.parentElement) { const c = getComputedStyle(e).backgroundColor; const a = (c.match(/[\d.]+/g)||[])[3]; if (c !== 'rgba(0, 0, 0, 0)' && (a === undefined || +a > .9)) return c; } return getComputedStyle(document.body).backgroundColor; };
  const visible = (el) => { const r = el.getBoundingClientRect(); const s = getComputedStyle(el); return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.opacity !== '0' && !el.closest('[hidden]') && !el.closest('.sr-only'); };
  const contrast = [];
  document.querySelectorAll('body *').forEach((el) => {
    if (!visible(el) || el.closest('.sample, .frame, svg')) return;
    const own = [...el.childNodes].some(n => n.nodeType === 3 && n.textContent.trim());
    if (!own) return;
    const s = getComputedStyle(el);
    const [lf] = lum(s.color), [lb] = lum(bgOf(el));
    const ratio = (Math.max(lf, lb) + .05) / (Math.min(lf, lb) + .05);
    const size = parseFloat(s.fontSize), bold = +s.fontWeight >= 700;
    const need = (size >= 24 || (size >= 18.66 && bold)) ? 3 : 4.5;
    if (ratio < need) contrast.push({ text: el.textContent.trim().slice(0, 40), ratio: +ratio.toFixed(2), need });
  });
  const targets = [], unnamed = [];
  document.querySelectorAll('a[href], button, input:not([type=file]), [role=button], [tabindex="0"]').forEach((el) => {
    if (!visible(el)) return;
    const r = el.getBoundingClientRect();
    const inline = el.tagName === 'A' && getComputedStyle(el).display === 'inline';
    if (!inline && (r.width < 24 || r.height < 24)) targets.push({ el: el.id || el.className || el.tagName, w: Math.round(r.width), h: Math.round(r.height) });
    const name = (el.getAttribute('aria-label') || el.textContent || el.getAttribute('title') || '').trim();
    if (!name && el.type !== 'range') unnamed.push(el.outerHTML.slice(0, 80));
    if (el.type === 'range' && !el.closest('label')) unnamed.push('range without label');
  });
  const imgsNoAlt = [...document.images].filter(i => !i.hasAttribute('alt')).map(i => i.src.slice(-40));
  return { vw: innerWidth, overflowX: document.documentElement.scrollWidth > innerWidth + 1,
           contrastFails: contrast, smallTargets: targets, unnamed, imgsNoAlt };
})()
"""

FOCUS_JS = r"""
(() => {
  const el = document.activeElement;
  if (!el || el === document.body) return null;
  const s = getComputedStyle(el);
  const ring = (s.boxShadow && s.boxShadow !== 'none') || (s.outlineStyle !== 'none' && parseFloat(s.outlineWidth) > 0);
  return { name: (el.getAttribute('aria-label') || el.textContent || el.tagName).trim().replace(/\s+/g, ' ').slice(0, 40), ring };
})()
"""


class Page:
    def __init__(self, ws):
        self.ws, self.i, self.events = ws, 0, []

    async def send(self, method, **params):
        self.i += 1; mid = self.i
        await self.ws.send(json.dumps({"id": mid, "method": method, "params": params}))
        while True:
            msg = json.loads(await self.ws.recv())
            if msg.get("id") == mid:
                if "error" in msg:
                    raise RuntimeError(f"{method}: {msg['error']}")
                return msg.get("result", {})
            self.events.append(msg)

    async def js(self, expr):
        r = await self.send("Runtime.evaluate", expression=expr, awaitPromise=True, returnByValue=True)
        if "exceptionDetails" in r:
            raise RuntimeError(r["exceptionDetails"])
        return r["result"].get("value")

    async def wait_for(self, expr, timeout=10):
        t0 = time.time()
        while time.time() - t0 < timeout:
            if await self.js(expr):
                return True
            await asyncio.sleep(0.1)
        raise TimeoutError(expr)

    async def shot(self, name, full=False):
        await asyncio.sleep(0.45)  # let enter transitions settle
        r = await self.send("Page.captureScreenshot", format="png", captureBeyondViewport=full)
        p = OUT / f"{name}.png"
        p.write_bytes(base64.b64decode(r["data"]))
        return p.name

    async def goto(self, url=URL):
        await self.send("Page.navigate", url=url)
        await self.wait_for("document.readyState === 'complete' && !document.getElementById('model-status').textContent.includes('Connecting')", 20)
        await asyncio.sleep(0.4)

    async def upload(self, path):
        doc = await self.send("DOM.getDocument")
        node = await self.send("DOM.querySelector", nodeId=doc["root"]["nodeId"], selector="#file")
        await self.send("DOM.setFileInputFiles", files=[str(path)], nodeId=node["nodeId"])


async def run_viewport(page, vp, results):
    w, h, dpr, mobile = VIEWPORTS[vp]
    await page.send("Emulation.setDeviceMetricsOverride", width=w, height=h, deviceScaleFactor=dpr, mobile=mobile)
    await page.send("Emulation.setEmulatedMedia", features=[{"name": "prefers-color-scheme", "value": "light"}])
    await page.send("Network.setBlockedURLs", urls=[])
    await page.goto()
    await page.js("localStorage.clear(); location.reload()")
    await page.goto()
    R = results[vp] = {"shots": {}, "audits": {}, "states": {}}

    # Empty
    R["shots"]["empty"] = await page.shot(f"{vp}-1-empty")
    R["audits"]["empty"] = await page.js(AUDIT_JS)
    R["states"]["empty"] = await page.js("!document.getElementById('state-empty').hidden")

    # Keyboard order + visible focus (first 12 stops)
    stops = []
    await page.js("document.activeElement.blur(); window.scrollTo(0,0)")
    for _ in range(12):
        await page.send("Input.dispatchKeyEvent", type="keyDown", key="Tab", code="Tab", windowsVirtualKeyCode=9)
        await page.send("Input.dispatchKeyEvent", type="keyUp", key="Tab", code="Tab", windowsVirtualKeyCode=9)
        stops.append(await page.js(FOCUS_JS))
    R["keyboard"] = stops
    await page.js("document.activeElement.blur()")

    # Loading (forced, the real one lasts < 0.5 s)
    await page.js(f"document.getElementById('loading-img').src = '/static/samples/{SAMPLE.name}'; show('loading')")
    R["shots"]["loading"] = await page.shot(f"{vp}-2-loading")
    R["states"]["loading"] = await page.js("document.getElementById('report').getAttribute('aria-busy') === 'true'")
    await page.js("show('empty')")

    # Success
    await page.upload(SAMPLE)
    await page.wait_for("!document.getElementById('state-result').hidden", 15)
    R["states"]["success_announce"] = await page.js("document.getElementById('sr-status').textContent")
    R["shots"]["success"] = await page.shot(f"{vp}-3-success", full=True)
    R["audits"]["success"] = await page.js(AUDIT_JS)
    await page.js("document.getElementById('view-heat').click()")
    R["shots"]["heatmap"] = await page.shot(f"{vp}-4-heatmap")
    R["states"]["heat_pressed"] = await page.js("document.getElementById('view-heat').getAttribute('aria-pressed')")

    # Dark theme success
    await page.send("Emulation.setEmulatedMedia", features=[{"name": "prefers-color-scheme", "value": "dark"}])
    R["shots"]["success_dark"] = await page.shot(f"{vp}-5-success-dark", full=True)
    R["audits"]["success_dark"] = await page.js(AUDIT_JS)
    await page.send("Emulation.setEmulatedMedia", features=[{"name": "prefers-color-scheme", "value": "light"}])

    # Error (server rejects a non-image disguised as .jpg)
    bad = Path(tempfile.gettempdir()) / "plantdoctor-not-an-image.jpg"
    bad.write_text("not an image")
    await page.upload(bad)
    await page.wait_for("!document.getElementById('state-error').hidden", 15)
    R["states"]["error_msg"] = await page.js("document.getElementById('error-msg').textContent")
    R["states"]["error_back_available"] = await page.js("!document.getElementById('btn-back').hidden")
    R["shots"]["error"] = await page.shot(f"{vp}-6-error")
    R["audits"]["error"] = await page.js(AUDIT_JS)

    # Partial (a): reopen from history — original photo not stored
    await page.js("document.querySelector('#history button').click()")
    await page.wait_for("!document.getElementById('state-result').hidden")
    R["states"]["partial_history"] = await page.js(
        "({originalDisabled: document.getElementById('view-photo').disabled, caption: document.getElementById('viewer-cap').textContent})")
    R["shots"]["partial_history"] = await page.shot(f"{vp}-7-partial-history")

    # Partial (b): model server info unavailable
    await page.send("Network.enable")
    await page.send("Network.setBlockedURLs", urls=["*/api/info"])
    await page.send("Page.navigate", url=URL)
    await page.wait_for("document.getElementById('model-status').textContent.includes('Offline')", 15)
    R["states"]["partial_offline"] = await page.js(
        "({pill: document.getElementById('model-status').innerText.trim(), note: !document.getElementById('offline-note').hidden, kpi: document.getElementById('kpi-acc').textContent})")
    R["shots"]["partial_offline"] = await page.shot(f"{vp}-8-partial-offline")
    R["audits"]["partial_offline"] = await page.js(AUDIT_JS)
    await page.send("Network.setBlockedURLs", urls=[])


async def main():
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)
    prof = tempfile.mkdtemp(prefix="pd-chrome-")
    chrome = subprocess.Popen(["google-chrome", "--headless=new", f"--remote-debugging-port={PORT}", f"--user-data-dir={prof}",
                               "--no-first-run", "--hide-scrollbars", "about:blank"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(100):
            try:
                tabs = json.loads(urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json").read()); break
            except Exception:
                time.sleep(0.1)
        ws_url = [t for t in tabs if t["type"] == "page"][0]["webSocketDebuggerUrl"]
        async with websockets.connect(ws_url, max_size=50_000_000) as ws:
            page = Page(ws)
            for d in ("Page", "Runtime", "DOM"):
                await page.send(f"{d}.enable")
            results = {}
            for vp in VIEWPORTS:
                await run_viewport(page, vp, results)
            errors = [e for e in page.events if e.get("method") == "Runtime.exceptionThrown"]
            results["js_exceptions"] = [e["params"]["exceptionDetails"].get("text") for e in errors]
        (OUT / "gate_results.json").write_text(json.dumps(results, indent=1))
        print(json.dumps(results, indent=1))
    finally:
        chrome.terminate()
        shutil.rmtree(prof, ignore_errors=True)


if __name__ == "__main__":
    asyncio.run(main())
