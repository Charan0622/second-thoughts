"""Connect your phone: the phone takes a photo, the laptop runs the council on it.

Mobile browsers only allow getUserMedia on HTTPS/localhost, so the phone page uses a plain
<input type="file" accept="image/*" capture="environment">, which works over http on the LAN.
The latest frame is held in memory; the laptop UI polls /api/phone/latest.
"""

from __future__ import annotations

import re
import socket
import time

import qrcode
import qrcode.image.svg
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse

router = APIRouter()

MAX_BYTES = 4 * 1024 * 1024
_latest: dict = {"id": 0, "frame": None, "price": None, "ts": None}


def _lan_ip() -> str:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))  # no packet is sent; this just picks the outbound interface
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


def _qr_svg(data: str) -> str:
    img = qrcode.make(data, image_factory=qrcode.image.svg.SvgPathImage, border=2)
    svg = img.to_string(encoding="unicode")
    svg = re.sub(r'\swidth="[^"]*"\s+height="[^"]*"', ' width="100%" height="100%" shape-rendering="crispEdges"', svg, count=1)
    return re.sub(r"(<svg[^>]*>)", r'\1<rect width="100%" height="100%" fill="#fff"/>', svg, count=1)


@router.get("/api/phone/info")
async def phone_info(request: Request):
    port = request.url.port or 8000
    from .config import PRIVATE
    pub = PRIVATE / "public_url.txt"   # written by scripts/phone_tunnel.sh while an HTTPS tunnel is running
    public = pub.read_text().strip() if pub.exists() else ""
    url = f"{public.rstrip('/')}/phone" if public.startswith("https://") else f"http://{_lan_ip()}:{port}/phone"
    return {"url": url, "qr_svg": _qr_svg(url), "via": "tunnel" if public else "lan"}


@router.post("/api/phone/frame")
async def phone_frame(req: dict):
    frame = req.get("frame")
    if not isinstance(frame, str) or not frame.startswith("data:image/") or "," not in frame:
        raise HTTPException(422, "frame must be a data:image/... URL")
    if len(frame) > MAX_BYTES:
        raise HTTPException(413, "frame too large (max 4 MB)")
    price = req.get("price")
    try:
        price = float(price) if price not in (None, "") else None
    except (TypeError, ValueError):
        price = None
    if price is not None and price <= 0:
        price = None
    _latest.update(id=_latest["id"] + 1, frame=frame, price=price, ts=time.time())
    return {"ok": True, "id": _latest["id"]}


@router.get("/api/phone/latest")
async def phone_latest(after: int = 0):
    if _latest["frame"] and _latest["id"] > after:
        return dict(_latest)
    return {"id": _latest["id"], "frame": None}


@router.get("/phone", response_class=HTMLResponse)
async def phone_page():
    return HTMLResponse(PAGE, headers={"Cache-Control": "no-store"})


PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="theme-color" content="#16140F">
<title>Second Thoughts — phone</title>
<style>
  :root { --bg: #16140F; --bg2: #23201A; --ink: #F1ECE3; --ink2: #B9B0A2; --hair: rgba(241,236,227,.18);
          --ok: #8FCBA6; --err: #F0927F; }
  * { box-sizing: border-box; }
  html, body { margin: 0; background: var(--bg); color: var(--ink);
    font: 400 18px/1.45 ui-sans-serif, system-ui, -apple-system, "Segoe UI", sans-serif; -webkit-font-smoothing: antialiased; }
  main { max-width: 520px; margin: 0 auto; padding: 24px 16px calc(32px + env(safe-area-inset-bottom)); display: flex; flex-direction: column; gap: 18px; min-height: 100svh; }
  h1 { margin: 0; font: 400 30px/1.1 "Iowan Old Style", Georgia, serif; letter-spacing: -.01em; }
  p { margin: 0; color: var(--ink2); }
  .big { display: flex; align-items: center; justify-content: center; gap: 10px; width: 100%; min-height: 72px; border: 0; border-radius: 14px;
    background: var(--ink); color: var(--bg); font-family: inherit; font-weight: 600; font-size: 22px; line-height: 1; cursor: pointer; }
  .big:active { transform: scale(.985); }
  .big:disabled { opacity: .55; }
  .ghost { background: transparent; color: var(--ink); border: 1.5px solid var(--hair); }
  input[type=file] { position: absolute; width: 1px; height: 1px; opacity: 0; pointer-events: none; }
  label.price { display: flex; align-items: center; gap: 10px; padding: 12px 16px; border: 1.5px solid var(--hair); border-radius: 14px; background: var(--bg2); }
  label.price span { color: var(--ink2); white-space: nowrap; }
  label.price input { flex: 1; min-width: 0; background: transparent; border: 0; color: var(--ink); font-family: inherit; font-weight: 600; font-size: 24px; line-height: 1.2; outline: none; }
  .shot { width: 100%; max-height: 52svh; object-fit: contain; border-radius: 14px; background: var(--bg2); display: none; }
  .status { min-height: 1.5em; font-weight: 600; }
  .status.ok { color: var(--ok); font-size: 24px; }
  .status.err { color: var(--err); }
  .hidden { display: none !important; }
</style>
</head>
<body>
<main>
  <div>
    <h1>Second Thoughts</h1>
    <p>Photograph the thing you want (price tag in view). Your selves weigh in on the laptop.</p>
  </div>

  <img id="shot" class="shot" alt="Your photo">

  <div id="capture">
    <input id="file" type="file" accept="image/*" capture="environment">
    <button id="take" class="big" type="button">📷 Take photo</button>
  </div>

  <label class="price"><span>Price $</span><input id="price" inputmode="decimal" placeholder="optional" autocomplete="off"></label>

  <div id="status" class="status" role="status" aria-live="polite"></div>
  <button id="again" class="big ghost hidden" type="button">Take another</button>
</main>
<script>
(function () {
  var file = document.getElementById('file'), take = document.getElementById('take'), again = document.getElementById('again');
  var shot = document.getElementById('shot'), status = document.getElementById('status'), priceEl = document.getElementById('price');
  var MAX = 1280;

  function say(text, cls) { status.textContent = text; status.className = 'status' + (cls ? ' ' + cls : ''); }
  function pick() { file.value = ''; file.click(); }
  take.addEventListener('click', pick);
  again.addEventListener('click', function () { again.classList.add('hidden'); take.classList.remove('hidden'); say(''); pick(); });

  function downscale(f) {
    return new Promise(function (resolve, reject) {
      var url = URL.createObjectURL(f), img = new Image();
      img.onload = function () {
        var s = Math.min(1, MAX / Math.max(img.naturalWidth, img.naturalHeight));
        var c = document.createElement('canvas');
        c.width = Math.round(img.naturalWidth * s); c.height = Math.round(img.naturalHeight * s);
        c.getContext('2d').drawImage(img, 0, 0, c.width, c.height);
        URL.revokeObjectURL(url);
        resolve(c.toDataURL('image/jpeg', 0.85));
      };
      img.onerror = function () { URL.revokeObjectURL(url); reject(new Error('Could not read that image')); };
      img.src = url;
    });
  }

  file.addEventListener('change', function () {
    var f = file.files && file.files[0];
    if (!f) return;
    take.disabled = true;
    say('Sending…');
    downscale(f).then(function (dataUrl) {
      shot.src = dataUrl; shot.style.display = 'block';
      var n = parseFloat((priceEl.value || '').replace(/[$,\\s]/g, ''));
      return fetch('/api/phone/frame', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ frame: dataUrl, price: isFinite(n) && n > 0 ? n : null })
      });
    }).then(function (res) {
      if (!res.ok) return res.text().then(function (t) { throw new Error('Upload failed (' + res.status + ') ' + t.slice(0, 120)); });
      say('Sent ✓ — look at the laptop', 'ok');
      take.classList.add('hidden'); again.classList.remove('hidden');
    }).catch(function (e) {
      say((e && e.message) || 'Upload failed', 'err');
    }).then(function () { take.disabled = false; });
  });
})();
</script>
</body>
</html>
"""
