"""Benchmark: Drex council vs single Drex call vs frontier LLM (single) vs frontier-LLM council.

All methods see the SAME facts and the SAME code-computed numbers; only the decider changes.
Run: uv run python bench/run_bench.py [--limit N] [--methods council,drex1,llm1,llmcouncil]
Writes bench/results.jsonl and bench/RESULTS.md
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import statistics
import sys
import time
from dataclasses import replace
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import council, drex, facts as F  # noqa: E402
from app.agents import budget, deal, goals  # noqa: E402
from app.agents.base import REGRET_Q, Item, build_state  # noqa: E402
from app.config import DEEPINFRA_API_KEY, VETO_THRESHOLD  # noqa: E402

HERE = Path(__file__).parent
CARDS = HERE / "cards.jsonl"
FRONTIER = "Qwen/Qwen3.8-Max"
DREX_USD_TOK = 0.12 / 1e6
# DeepInfra list price for the frontier model, USD per token (input, output) — estimate for the table.
LLM_USD_IN, LLM_USD_OUT = 1.2 / 1e6, 6.0 / 1e6
BANDS = {"buy": "Buy it now", "buy_with_condition": "Buy only with a specific condition or trade-off",
         "wait": "Do not buy now; wait"}


def apply_card(card: dict) -> None:
    base = F.BASE
    F.use_persona(replace(base, balance=card["balance"], rules=base.rules if card["rules"] else [],
                          owned_item=base.owned_item if card["owns_earbuds"] else "", owned_price=base.owned_price))


def item_of(card: dict) -> Item:
    return Item(card["item"], card["category"], card["price"])


def owned_lines() -> list[str]:
    p = F.persona
    return ([f"Receipts on file: {p.owned_item} (${p.owned_price:.0f}, {p.owned_date}). The return window has closed."]
            if p.owned_item else ["Maya's receipts show nothing similar to the proposed purchase."])


def agent_states(item: Item, snaps: list[dict]) -> dict[str, str]:
    dfacts, dcomp = deal.web_facts(item, snaps)
    return {
        "budget": build_state("Budget You", "protect scheduled bills and keep Maya solvent until payday.",
                              F.facts["budget"], budget.computed(item), item),
        "goals": build_state("Goals You", "protect the Japan trip and hold Maya to the rules she set for herself.",
                             F.facts["goals"], goals.computed(item), item),
        "owned": build_state("Already-Own-It You", "stop Maya from buying something she already owns.",
                             F.facts["owned"], owned_lines(), item),
        "deal": build_state("Deal You", "make sure Maya pays a good price.", dfacts, dcomp, item),
    }


def combined_state(item: Item, snaps: list[dict]) -> str:
    dfacts, dcomp = deal.web_facts(item, snaps)
    fs = F.facts["budget"] + F.facts["goals"] + F.facts["owned"] + dfacts
    comp = budget.computed(item) + goals.computed(item) + owned_lines() + dcomp
    return build_state("Maya's spending advisor", "decide whether Maya should buy this now.", fs, comp, item)


# ---------------------------------------------------------------- methods
async def m_council(card, item, snaps):
    t = time.perf_counter()
    v = None
    toks0 = _drex_tokens()
    async for ev in council.deliberate(item, snaps, speak=False):
        if ev["type"] == "verdict":
            v = ev
    return {"pred": v["band"], "ms": (time.perf_counter() - t) * 1000, "cost": (_drex_tokens() - toks0) * DREX_USD_TOK,
            "detail": {"p": v["p"], "p1": v["p_round_one"], "veto": v["veto"], "condition": v["condition"]}}


async def m_drex1(card, item, snaps):
    t = time.perf_counter()
    toks0 = _drex_tokens()
    res = await drex.ask(combined_state(item, snaps), {"verdict": drex.choice("What should Maya do about this purchase?", BANDS)},
                         note="bench:single")
    a = res["answers"]["verdict"]
    return {"pred": a["choice"], "ms": (time.perf_counter() - t) * 1000, "cost": (_drex_tokens() - toks0) * DREX_USD_TOK,
            "detail": {"probs": a.get("probabilities")}}


_sem = asyncio.Semaphore(8)


async def llm(prompt: str) -> tuple[str, int, int, float]:
    async with _sem:
        t = time.perf_counter()
        async with httpx.AsyncClient(timeout=60) as c:
            r = await c.post("https://api.deepinfra.com/v1/openai/chat/completions",
                             headers={"Authorization": f"Bearer {DEEPINFRA_API_KEY}"},
                             json={"model": FRONTIER, "messages": [{"role": "user", "content": prompt}],
                                   "max_tokens": 300, "temperature": 0, "chat_template_kwargs": {"enable_thinking": False}})
        r.raise_for_status()
        j = r.json()
        u = j.get("usage", {})
        txt = re.sub(r"<think>.*?</think>", "", j["choices"][0]["message"]["content"] or "", flags=re.S)
        return txt, u.get("prompt_tokens", 0), u.get("completion_tokens", 0), (time.perf_counter() - t) * 1000


def _json(txt: str) -> dict:
    m = re.search(r"\{.*\}", txt, re.S)
    try:
        return json.loads(m.group(0)) if m else {}
    except Exception:  # noqa: BLE001
        return {}


async def m_llm1(card, item, snaps):
    prompt = (combined_state(item, snaps) + "\n\nOptions:\n" + "\n".join(f"- {k}: {v}" for k, v in BANDS.items())
              + '\n\nReply with JSON only: {"verdict": "buy" | "buy_with_condition" | "wait"}')
    txt, ti, to, ms = await llm(prompt)
    pred = _json(txt).get("verdict", "?")
    return {"pred": pred, "ms": ms, "cost": ti * LLM_USD_IN + to * LLM_USD_OUT, "detail": {}}


async def m_llmcouncil(card, item, snaps):
    states = agent_states(item, snaps)
    t = time.perf_counter()

    async def one(a, s):
        extra = ', "p_bill_unpayable": <0..1>' if a == "budget" else ""
        prompt = (s + f"\n\nQuestion: {REGRET_Q}\nReply with JSON only: "
                      '{"p_regret": <probability 0..1>, "stake": <0..10 how much this matters to you>' + extra + "}")
        txt, ti, to, _ = await llm(prompt)
        j = _json(txt)
        return a, j, ti * LLM_USD_IN + to * LLM_USD_OUT

    outs = await asyncio.gather(*(one(a, s) for a, s in states.items()))
    ps, ws, cost, veto = {}, {}, 0.0, False
    for a, j, c in outs:
        cost += c
        try:
            ps[a] = float(j.get("p_regret", 0.5))
            ws[a] = max(float(j.get("stake", 5)), 0.5)
        except (TypeError, ValueError):
            ps[a], ws[a] = 0.5, 5.0
        if a == "budget":
            try:
                veto = float(j.get("p_bill_unpayable", 0)) >= VETO_THRESHOLD
            except (TypeError, ValueError):
                pass
    p = council.pool(ps, ws)
    pred = "wait" if veto else council.band(p)
    return {"pred": pred, "ms": (time.perf_counter() - t) * 1000, "cost": cost, "detail": {"p": round(p, 3), "veto": veto}}


def _drex_tokens() -> int:
    from app import ledger
    return sum(e.get("tokens", 0) for e in ledger._calls.get("drex", []))


METHODS = {"council": m_council, "drex1": m_drex1, "llm1": m_llm1, "llmcouncil": m_llmcouncil}
NAMES = {"council": "Drex council (ours, 4 selves + veto + negotiation)", "drex1": "Single Drex call, all docs",
         "llm1": f"Single frontier LLM call ({FRONTIER})", "llmcouncil": f"Frontier-LLM council (4× {FRONTIER}, same pooling)"}


async def main(limit: int | None, methods: list[str]):
    await F.load()
    cards = [json.loads(line) for line in CARDS.read_text().splitlines()][:limit]
    # warm Keenable for each distinct item (Deal You uses cached web facts)
    items = {c["item"]: item_of(c) for c in cards}
    snaps_by = dict(zip(items, await asyncio.gather(*(deal.gather(i) for i in items.values()))))
    rows = []
    for card in cards:  # persona is global → cards run sequentially; methods for a card run concurrently
        apply_card(card)
        item, snaps = item_of(card), snaps_by[card["item"]]
        res = await asyncio.gather(*(METHODS[m](card, item, snaps) for m in methods), return_exceptions=True)
        row = {"id": card["id"], "label": card["label"], "item": card["item"], "variant": card["variant"]}
        for m, r in zip(methods, res):
            row[m] = r if isinstance(r, dict) else {"pred": "error", "ms": None, "cost": 0, "detail": {"err": str(r)[:200]}}
        rows.append(row)
        print(f"{card['id']:11} label={card['label']:18} " + " ".join(f"{m}={row[m]['pred']}" for m in methods), flush=True)
    F.use_persona(F.BASE)
    (HERE / "results.jsonl").write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    report(rows, methods)


def report(rows: list[dict], methods: list[str]) -> None:
    lines = ["| Method | Agreement with labels | Critical errors (said BUY when label = WAIT) | Median latency | Cost / verdict |",
             "|---|---|---|---|---|"]
    for m in methods:
        ok = sum(r[m]["pred"] == r["label"] for r in rows)
        crit = sum(r[m]["pred"] == "buy" and r["label"] == "wait" for r in rows)
        lat = [r[m]["ms"] for r in rows if r[m]["ms"]]
        cost = [r[m]["cost"] for r in rows]
        lines.append(f"| {NAMES[m]} | {ok}/{len(rows)} ({ok / len(rows):.0%}) | {crit} | "
                     f"{statistics.median(lat) / 1000:.2f} s | ${statistics.mean(cost):.5f} |")
    out = "\n".join(lines)
    print("\n" + out)
    (HERE / "RESULTS.md").write_text(f"# Benchmark results\n\n{len(rows)} labelled scenario cards (`bench/cards.jsonl`).\n\n{out}\n")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int)
    ap.add_argument("--methods", default="council,drex1,llm1,llmcouncil")
    a = ap.parse_args()
    asyncio.run(main(a.limit, a.methods.split(",")))
