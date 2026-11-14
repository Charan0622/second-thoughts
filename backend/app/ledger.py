"""Per-tool usage ledger: call counts, latency, tokens, cost. In-memory + JSONL on disk."""

from __future__ import annotations

import json
import statistics
import time
from collections import defaultdict
from contextlib import asynccontextmanager
from pathlib import Path

from .config import PRIVATE

TOOLS = ("drex", "ndi", "intern", "keenable", "deepinfra", "adobe")
# Drex bills input tokens only.
DREX_USD_PER_TOKEN = 0.12 / 1_000_000  # Drex Max, per Nace pricing docs

_calls: dict[str, list[dict]] = defaultdict(list)
_verdicts = 0
_LOG = PRIVATE / "ledger.jsonl"


def record(tool: str, ms: float, ok: bool = True, tokens: int = 0, cost_usd: float = 0.0, note: str = "") -> None:
    entry = {"tool": tool, "ms": round(ms, 1), "ok": ok, "tokens": tokens, "cost_usd": cost_usd, "note": note, "t": time.time()}
    _calls[tool].append(entry)
    try:
        with _LOG.open("a") as f:
            f.write(json.dumps(entry) + "\n")
    except OSError:
        pass


@asynccontextmanager
async def timed(tool: str, note: str = ""):
    """Usage: async with timed("keenable") as rec: ...; rec["tokens"] = n"""
    rec: dict = {"tokens": 0, "cost_usd": 0.0, "ok": True}
    t = time.perf_counter()
    try:
        yield rec
    except Exception:
        rec["ok"] = False
        raise
    finally:
        record(tool, (time.perf_counter() - t) * 1000, rec["ok"], rec["tokens"], rec["cost_usd"], note)


def count_verdict() -> None:
    global _verdicts
    _verdicts += 1


def load_history() -> None:
    """Restore ledger counts from previous runs (setup-time Intern/NDI calls count too)."""
    if not _LOG.exists():
        return
    for line in _LOG.read_text().splitlines():
        try:
            e = json.loads(line)
            _calls[e["tool"]].append(e)
        except Exception:  # noqa: BLE001
            continue


def snapshot() -> dict:
    tools = {}
    cost = 0.0
    for tool in TOOLS:
        es = _calls.get(tool, [])
        ok = [e for e in es if e["ok"]]
        c = sum(e.get("cost_usd", 0) for e in es)
        if tool == "drex":
            c = sum(e.get("tokens", 0) for e in es) * DREX_USD_PER_TOKEN
        cost += c
        tools[tool] = {
            "calls": len(es),
            "errors": len(es) - len(ok),
            "ms_median": round(statistics.median([e["ms"] for e in ok])) if ok else None,
            "input_tokens": sum(e.get("tokens", 0) for e in es) or None,
            "cost_usd": round(c, 4),
        }
    tools["adobe"]["note"] = "Firefly avatars + Express slides (made offline)"
    return {"tools": tools, "verdicts": _verdicts, "cost_usd_est": round(cost, 4)}
