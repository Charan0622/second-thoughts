"""Thin async Drex (Nace System One) client. Every call is recorded in the ledger."""

from __future__ import annotations

import asyncio
import random
import time
from typing import Any

import httpx

from . import ledger
from .config import DREX_MODEL, DREX_URL, NACE_API_KEY

_client: httpx.AsyncClient | None = None


def client() -> httpx.AsyncClient:
    global _client
    if _client is None:
        _client = httpx.AsyncClient(
            timeout=httpx.Timeout(8.0, connect=4.0),
            headers={"Authorization": f"Bearer {NACE_API_KEY}", "X-Nace-Client": "second-thoughts/0.1"},
            limits=httpx.Limits(max_connections=64, max_keepalive_connections=32),
        )
    return _client


class DrexError(RuntimeError):
    pass


_sem = asyncio.Semaphore(8)  # keep bursts under the rate limit


async def ask(state: str, questions: dict[str, dict], *, images: list[str] | None = None,
              model: str | None = None, note: str = "") -> dict[str, Any]:
    """POST /v1/systemone with backoff on 429/5xx. Returns {"answers", "ms", "eval_ms", "model", "request_id"}."""
    body: dict[str, Any] = {"model": model or DREX_MODEL, "state": state, "questions": questions}
    if images:
        body["images"] = images
    last: Exception | None = None
    for attempt in range(3):
        t = time.perf_counter()
        try:
            async with _sem:
                r = await client().post(DREX_URL, json=body)
            ms = (time.perf_counter() - t) * 1000
            if r.status_code == 200:
                data = r.json()
                ledger.record("drex", ms, True, data.get("usage", {}).get("input_tokens", 0), note=note)
                return {"answers": data["answers"], "ms": ms, "eval_ms": data.get("evaluation_time_ms"),
                        "model": data.get("model"), "request_id": data.get("request_id")}
            ledger.record("drex", ms, False, note=f"{note} HTTP {r.status_code}")
            if r.status_code != 429 and r.status_code < 500:
                raise DrexError(f"Drex HTTP {r.status_code}: {r.text[:300]}")
            last = DrexError(f"Drex HTTP {r.status_code}")
            try:
                wait = float(r.headers.get("retry-after", ""))
            except ValueError:
                wait = (0.4, 1.0, 2.0)[attempt] + random.random() * 0.2
            await asyncio.sleep(min(wait, 3.0))
        except httpx.HTTPError as e:
            ledger.record("drex", (time.perf_counter() - t) * 1000, False, note=f"{note} {type(e).__name__}")
            last = e
            await asyncio.sleep(0.3)
    raise DrexError(str(last))


def noul(instructions: str, true: str | None = None, false: str | None = None) -> dict:
    q: dict[str, Any] = {"type": "noul", "instructions": instructions}
    if true or false:
        q["criteria"] = {"true": true, "false": false}
    return q


def choice(instructions: str, options: dict[str, str | None]) -> dict:
    return {"type": "choice", "instructions": instructions, "criteria": options}


def score(instructions: str, levels: list[str]) -> dict:
    return {"type": "score", "instructions": instructions, "criteria": levels}


STAKE_LEVELS = ["0 — irrelevant to me", "1", "2 — minor", "3", "4", "5 — noticeable", "6", "7 — serious",
                "8", "9", "10 — critical"]
