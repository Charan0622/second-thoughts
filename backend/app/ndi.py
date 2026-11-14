"""NDI (Nace Document Intelligence) via the console route with nace-sdk. Extract results are cached by file hash."""

from __future__ import annotations

import hashlib
import json
import re
import time
from pathlib import Path
from typing import Any

from nace_sdk import AsyncNaceClient

from . import ledger
from .config import NACE_API_KEY, PRIVATE

CACHE = PRIVATE / "ndi_cache"
CACHE.mkdir(exist_ok=True)


def _key(data: bytes, schema: dict) -> str:
    return hashlib.sha256(data + json.dumps(schema, sort_keys=True).encode()).hexdigest()[:24]


async def extract(path: Path | None, schema: dict, *, data: bytes | None = None, name: str | None = None,
                  instructions: str | None = None, use_cache: bool = True) -> dict[str, Any]:
    """Return NDI extract result {data, fields, ...}. `data`+`name` lets callers send in-memory bytes (camera frames)."""
    raw = data if data is not None else path.read_bytes()
    k = _key(raw, schema)
    cp = CACHE / f"{k}.json"
    if use_cache and cp.exists():
        return json.loads(cp.read_text())
    t = time.perf_counter()
    rec_ok, cost = False, 0.0
    try:
        async with AsyncNaceClient(api_key=NACE_API_KEY) as c:
            up = await c.documents.upload(raw if data is not None else path, file_name=name or (path.name if path else "upload.jpg"),
                                          path=f"second-thoughts/{k}-{name or path.name}", on_conflict="new_version")
            opts: dict[str, Any] = {"schema": schema, "citations": {"enabled": True, "include_source_text": True}, "wait_seconds": 60}
            if instructions:
                opts["instructions"] = instructions
            job = await c.documents.extract(up.as_source(), **opts)
            if job.status not in ("succeeded", "failed", "canceled", "cancelled"):
                job = await c.jobs.wait(job.job_id, timeout=180)
            dump = job.model_dump(mode="json") if hasattr(job, "model_dump") else dict(job.__dict__)
            try:
                cost = float((dump.get("cost") or {}).get("total_usd") or 0)
            except (TypeError, ValueError):
                cost = 0.0
            if job.status != "succeeded":
                raise RuntimeError(f"NDI job {job.status}: {dump.get('error')}")
            result = dump["result"]
            rec_ok = True
    finally:
        ledger.record("ndi", (time.perf_counter() - t) * 1000, rec_ok, cost_usd=cost,
                      note=f"extract {name or (path.name if path else '')}")
    cp.write_text(json.dumps(result))
    return result


_TAG = re.compile(r"<[^>]+>")


def clean_quote(s: str | None) -> str:
    if not s:
        return ""
    s = re.sub(r"</t[dh]>\s*<t[dh][^>]*>", " · ", s)
    s = _TAG.sub(" ", s)
    return re.sub(r"\s+", " ", s).strip(" ·")


def field(result: dict, path: str) -> dict | None:
    for f in result.get("fields") or []:
        if f.get("path") == path:
            return f
    return None


def citation_of(result: dict, path: str) -> dict:
    """{page, quote, bbox} for a field path; bbox = normalized [x0,y0,x1,y1] or None."""
    f = field(result, path)
    if not f or not f.get("citations"):
        return {"page": None, "quote": "", "bbox": None, "status": (f or {}).get("status", "not_found")}
    c = f["citations"][0]
    loc = c.get("location") or {}
    bbox = None
    polys = loc.get("polygons") or []
    pts = [p for poly in polys for p in poly]
    if pts:
        xs, ys = [p[0] for p in pts], [p[1] for p in pts]
        bbox = [min(xs), min(ys), max(xs), max(ys)]
    return {"page": loc.get("page"), "quote": clean_quote(c.get("source_text")), "bbox": bbox, "status": f.get("status")}
