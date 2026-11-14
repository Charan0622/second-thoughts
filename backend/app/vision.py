"""Vision tag reader: a Qwen VL model on DeepInfra reads product name + price straight off a camera frame.

Independent of Nace (NDI/Drex), so perception still gets a price when the console is unreachable.
It must never invent a price: if none is legible it returns price=None.
"""

from __future__ import annotations

import json
import os
import re
import time

import httpx

from . import ledger
from .config import DEEPINFRA_API_KEY

URL = "https://api.deepinfra.com/v1/openai/chat/completions"
VISION_MODEL = os.environ.get("VISION_MODEL", "Qwen/Qwen3-VL-30B-A3B-Instruct")
TIMEOUT_S = 7.0

PROMPT = (
    "You read retail price tags, shelf labels, packaging and on-screen prices. Look at the image and reply with ONLY "
    "a JSON object, no prose, with exactly these keys:\n"
    '{"product_name": string|null, "brand": string|null, "product_type": string|null, "price": number|null, '
    '"currency": string|null, "was_price": number|null, "price_text": string|null, "confidence": number}\n'
    "Rules:\n"
    "- product_name: the product/model as printed (without the brand); brand: the brand; product_type: a few words, "
    "e.g. 'biscuits', 'water bottle', 'running shoes'.\n"
    "- price: the CURRENT selling price for ONE unit exactly as printed on a tag/label/screen in the image "
    "(the sale/'now' price if two are shown). Do NOT use unit prices (per oz / per kg / per 100 g), sizes, weights, "
    "quantities, barcodes, item numbers or dates as the price.\n"
    "- If no price is clearly legible in the image, price MUST be null. Never estimate or guess a price from what "
    "the product usually costs.\n"
    "- currency: ISO code (USD, EUR, GBP, ...) from the symbol on the tag; null if price is null. "
    "was_price: crossed-out/'was'/regular price if shown, else null. price_text: the price string exactly as printed.\n"
    "- confidence: 0-1, how sure you are that the price (or its absence) is read correctly."
)


def _parse(text: str) -> dict:
    text = re.sub(r"<think>.*?</think>", "", text or "", flags=re.S)
    m = re.search(r"\{.*\}", text, flags=re.S)
    if not m:
        raise ValueError("no JSON object in vision reply")
    return json.loads(m.group(0))


def _num(v) -> float | None:
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v) if v > 0 else None
    s = re.sub(r"[^\d.,]", "", str(v))
    if not s:
        return None
    if "," in s and "." not in s and re.fullmatch(r"\d+,\d{2}", s):  # European decimal comma: 89,95
        s = s.replace(",", ".")
    s = s.replace(",", "")
    try:
        f = float(s)
    except ValueError:
        return None
    return f if f > 0 else None


def _str(v) -> str | None:
    s = str(v).strip() if v is not None else ""
    return s if s and s.lower() not in ("null", "none", "n/a", "unknown") else None


def normalize(d: dict) -> dict:
    """Coerce a model reply into the documented shape (pure; unit-testable)."""
    price = _num(d.get("price"))
    cur = _str(d.get("currency"))
    cur = cur.upper()[:3] if cur else None
    if cur in ("$", "US$"):
        cur = "USD"
    try:
        conf = float(d.get("confidence"))
    except (TypeError, ValueError):
        conf = 0.5
    return {"product_name": _str(d.get("product_name")), "brand": _str(d.get("brand")),
            "product_type": _str(d.get("product_type")), "price": price,
            "currency": (cur or "USD") if price is not None else None,
            "was_price": _num(d.get("was_price")), "price_text": _str(d.get("price_text")),
            "confidence": min(max(conf, 0.0), 1.0)}


def display_name(v: dict) -> str:
    """brand + product_name, without doubling the brand."""
    brand, name = (v.get("brand") or "").strip(), (v.get("product_name") or "").strip()
    if brand and name and not name.lower().startswith(brand.lower()):
        return f"{brand} {name}"
    return name or brand


async def read_tag(jpeg_data_url: str) -> dict:
    """Return the normalized tag read, or {} on any failure (never raises)."""
    if not DEEPINFRA_API_KEY:
        return {}
    t = time.perf_counter()
    ok, tokens = False, 0
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT_S) as c:
            r = await c.post(URL, headers={"Authorization": f"Bearer {DEEPINFRA_API_KEY}"}, json={
                "model": VISION_MODEL, "temperature": 0, "max_tokens": 200,
                "messages": [{"role": "user", "content": [
                    {"type": "image_url", "image_url": {"url": jpeg_data_url}},
                    {"type": "text", "text": PROMPT}]}]})
        r.raise_for_status()
        body = r.json()
        tokens = (body.get("usage") or {}).get("total_tokens", 0)
        out = normalize(_parse(body["choices"][0]["message"]["content"]))
        ok = True
        return out
    except Exception:  # noqa: BLE001
        return {}
    finally:
        ledger.record("deepinfra", (time.perf_counter() - t) * 1000, ok, tokens, note="vision tag read")
