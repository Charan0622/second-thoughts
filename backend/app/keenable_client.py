"""Keenable live web search, cached per query (searches take ~2 s, so the hot path reads the cache)."""

from __future__ import annotations

import asyncio
import json
import os
import re
import statistics
import time
from datetime import datetime, timezone
from urllib.parse import urlparse

from . import ledger
from .config import PRIVATE

CACHE = PRIVATE / "keenable_cache.json"
try:
    _cache: dict[str, dict] = json.loads(CACHE.read_text()) if CACHE.exists() else {}
except Exception:  # noqa: BLE001
    _cache = {}
def clean(s: str) -> str:
    s = re.sub(r"!?\[([^\]]*)\]\([^)]*\)", r"\1", s or "")      # markdown links/images → text
    s = re.sub(r"https?://\S+", "", s)
    s = re.sub(r"[#*_`>|]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


PRICE = re.compile(r"\$\s?(\d{1,3}(?:,\d{3})*(?:\.\d{2})?)")


def _search_sync(q: str):
    from keenable import Keenable
    return Keenable().search(q)


def _parse(resp, item_price: float | None) -> dict:
    results = []
    for r in list(getattr(resp, "results", None) or [])[:6]:
        title = getattr(r, "title", "") or ""
        url = getattr(r, "url", "") or ""
        snippet = getattr(r, "snippet", None) or getattr(r, "content", None) or getattr(r, "text", "") or ""
        results.append({"title": clean(title)[:140], "url": url, "host": urlparse(url).netloc.replace("www.", ""),
                        "snippet": clean(str(snippet))[:400]})
    if not results:  # fall back to parsing to_context()
        ctx = resp.to_context()
        for block in ctx.split("\n\n[")[:6]:
            m = re.search(r"\((https?://[^)]+)\)", block)
            url = m.group(1) if m else ""
            results.append({"title": block.split("\n")[0][:140].lstrip("[0123456789] "), "url": url,
                            "host": urlparse(url).netloc.replace("www.", ""), "snippet": block[:400]})
    prices = []
    for r in results:
        for m in PRICE.findall(r["title"] + " " + r["snippet"]):
            v = float(m.replace(",", ""))
            if item_price is None or 0.5 * item_price <= v <= 1.5 * item_price:
                prices.append(v)
    return {"results": results, "prices": prices,
            "low": min(prices) if prices else None, "median": statistics.median(prices) if prices else None,
            "black_friday_mentioned": any("black friday" in (r["title"] + r["snippet"]).lower() for r in results)}


JUNK_CTX = re.compile(r"(off|save|saving|discount|increase|gst|vat|/\s?mo|per month|a month|monthly|shipping|coupon|credit)", re.I)


def prices_near(text: str, item_price: float | None) -> list[float]:
    """Dollar amounts in `text` that look like a selling price for this item (not a discount, fee or plan)."""
    out = []
    for m in PRICE.finditer(text):
        ctx = text[max(0, m.start() - 18): m.end() + 18]
        if JUNK_CTX.search(ctx):
            continue
        v = float(m.group(1).replace(",", ""))
        if item_price is None or 0.5 * item_price <= v <= 1.5 * item_price:
            out.append(v)
    return out


async def search(query: str, item_price: float | None = None, *, max_age_s: float = 6 * 3600, timeout: float = 6.0) -> dict | None:
    hit = _cache.get(query)
    if hit and time.time() - hit["ts"] < max_age_s:
        return {**hit, "cached": True}
    t = time.perf_counter()
    try:
        resp = await asyncio.wait_for(asyncio.to_thread(_search_sync, query), timeout)
        parsed = _parse(resp, item_price)
        ledger.record("keenable", (time.perf_counter() - t) * 1000, True, note=query)
    except Exception as e:  # noqa: BLE001
        ledger.record("keenable", (time.perf_counter() - t) * 1000, False, note=f"{query}: {type(e).__name__}")
        return {**hit, "cached": True, "stale": True} if hit else None
    data = {"query": query, "ts": time.time(), "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            **parsed}
    _cache[query] = data
    tmp = CACHE.with_suffix(".tmp")
    tmp.write_text(json.dumps(_cache, indent=1))
    os.replace(tmp, CACHE)
    return {**data, "cached": False}
