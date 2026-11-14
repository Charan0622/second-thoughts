"""Benchmark v3: Drex council vs fair single-call baselines vs a plain-Python rules floor.

All methods see the SAME persona facts and the SAME code-computed numbers; only the decider changes.
Methods run SEQUENTIALLY per card, so per-method Drex token cost is a clean diff of the ledger.

Run:
  uv run python bench/run_bench.py --cards cards.jsonl --out results_v3.jsonl
  uv run python bench/run_bench.py --cards holdout_cards.jsonl --out results_holdout.jsonl
  uv run python bench/run_bench.py --report results_holdout.jsonl            # metrics only, no API calls
Flags: --limit N, --methods council,drex1,llm1,llmcouncil,rules, --neutral (numeric phrasing ablation),
       --merge (keep other methods' results already in --out and only (re)run the listed methods).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import random
import re
import statistics
import sys
import time
from collections import Counter
from dataclasses import replace
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import council, drex, facts as F, ledger  # noqa: E402
from app.agents import budget, deal, goals  # noqa: E402
from app.agents.base import REGRET_Q, Item, build_state  # noqa: E402
from app.config import DEEPINFRA_API_KEY, VETO_THRESHOLD  # noqa: E402

HERE = Path(__file__).parent
FRONTIER = "Qwen/Qwen3.8-Max"
DREX_USD_TOK = 0.12 / 1e6                 # Drex bills input tokens only
LLM_USD_IN, LLM_USD_OUT = 1.2 / 1e6, 6.0 / 1e6   # DeepInfra list price estimate for the frontier model
LABELS = ["buy", "buy_with_condition", "wait"]
SHORT = {"buy": "buy", "buy_with_condition": "cond", "wait": "wait"}
# Plain-English band definitions given to BOTH single-call baselines (the council encodes the same ideas in its selves).
BANDS = {"buy": "Buy it now: it is affordable, within the person's own rules, and not a duplicate of something they own",
         "buy_with_condition": "Buy only with a specific trade-off or commitment: buyable, but only if a concrete condition is met",
         "wait": "Do not buy now: the person should not make this purchase at this time"}


# ---------------------------------------------------------------- persona / shared facts
def apply_card(card: dict) -> None:
    base = F.BASE
    keep_owned = card["owns_earbuds"]
    F.use_persona(replace(base, balance=card["balance"], rules=list(base.rules) if card["rules"] else [],
                          owned_item=base.owned_item if keep_owned else "",
                          owned=list(base.owned) if keep_owned else []))


def item_of(card: dict) -> Item:
    return Item(card["item"], card["category"], card["price"])


def owned_lines() -> list[str]:
    """Same computed lines Already-Own-It You sees (mirrors agents/owned.py)."""
    p = F.persona
    if p.owned:
        out = ["Receipts on file: " + "; ".join(f"{o['item']} (${o['price']:,.0f}{', ' + o['date'] if o['date'] else ''})"
                                                for o in p.owned) + "."]
        if p.owned_item:
            out.append(f"Estimated resale value of {p.owned_item.split('(')[0].strip()} today: about ${round(p.owned_price * 0.5):.0f}.")
        return out
    return ["The buyer's receipts show nothing similar to the proposed purchase."]


def agent_states(item: Item, snaps: list[dict]) -> dict[str, str | None]:
    """Per-self states with the same mandates and computed lines the council uses. Deal abstains like the council."""
    prices, _ = deal.on_topic_prices(item, snaps)
    dfacts, dcomp = deal.web_facts(item, snaps)
    return {
        "budget": build_state("Budget You", "protect scheduled bills and keep the buyer solvent until payday. You hold a veto.",
                              F.facts["budget"], budget.computed(item), item),
        "goals": build_state("Goals You", f"protect the {F.persona.goal_name} and hold the buyer to the rules they set for themselves.",
                             F.facts["goals"], goals.computed(item), item),
        "owned": build_state("Already-Own-It You", "stop the buyer from buying something they already own or that duplicates what she has.",
                             F.facts["owned"], owned_lines(), item),
        "deal": (build_state("Deal You", "make sure the buyer pays a good price, and say when waiting for a better deal would win.",
                             dfacts, dcomp, item) if len(prices) >= 3 else None),
    }


def combined_state(item: Item, snaps: list[dict]) -> str:
    dfacts, dcomp = deal.web_facts(item, snaps)
    fs = F.facts["budget"] + F.facts["goals"] + F.facts["owned"] + dfacts
    comp = budget.computed(item) + goals.computed(item) + owned_lines() + dcomp
    return build_state(f"{F.persona.first_name}'s spending advisor", "decide whether the buyer should buy this now.", fs, comp, item)


# ---------------------------------------------------------------- neutral-phrasing ablation
def _neutralize(line: str) -> str:
    line = re.sub(r" — (OVER|within) the limit\.", ".", line)
    m = re.match(r"This purchase EXCEEDS free cash by \$([\d,\.]+)\..*", line)
    if m:
        return f"Free cash minus price = -${m.group(1)}."
    return line.replace(" Every scheduled bill stays covered.", "")


def enable_neutral() -> None:
    ob, og = budget.computed, goals.computed
    budget.computed = lambda item, extra=None: [_neutralize(x) for x in ob(item, extra)]
    goals.computed = lambda item, extra=None: [_neutralize(x) for x in og(item, extra)]


# ---------------------------------------------------------------- Drex cost (sequential → ledger diff is per-method)
def _drex_mark() -> int:
    return len(ledger._calls.get("drex", []))


def _drex_since(mark: int) -> tuple[int, int]:
    es = ledger._calls.get("drex", [])[mark:]
    return sum(e.get("tokens", 0) for e in es), len(es)


# ---------------------------------------------------------------- methods
async def m_council(card, item, snaps):
    t, mark = time.perf_counter(), _drex_mark()
    v, err = None, None
    async for ev in council.deliberate(item, snaps, speak=False):
        if ev["type"] == "verdict":
            v = ev
        elif ev["type"] == "error":
            err = ev["message"]
    toks, calls = _drex_since(mark)
    if v is None:
        raise RuntimeError(err or "no verdict")
    return {"pred": v["band"], "ms": (time.perf_counter() - t) * 1000, "cost": toks * DREX_USD_TOK, "tokens": toks, "calls": calls,
            "detail": {"p": v["p"], "p1": v["p_round_one"], "veto": v["veto"], "condition": v["condition"],
                       "tally": v["tally"], "votes": v.get("_votes")}}


async def m_drex1(card, item, snaps):
    t, mark = time.perf_counter(), _drex_mark()
    res = await drex.ask(combined_state(item, snaps), {"verdict": drex.choice("What should the buyer do about this purchase?", BANDS)},
                         note="bench:single")
    a = res["answers"]["verdict"]
    toks, calls = _drex_since(mark)
    return {"pred": a["choice"], "ms": (time.perf_counter() - t) * 1000, "cost": toks * DREX_USD_TOK, "tokens": toks, "calls": calls,
            "detail": {"probs": a.get("probabilities")}}


_http: httpx.AsyncClient | None = None


def http() -> httpx.AsyncClient:
    global _http
    if _http is None:
        _http = httpx.AsyncClient(timeout=60, headers={"Authorization": f"Bearer {DEEPINFRA_API_KEY}"})
    return _http


async def llm(prompt: str) -> tuple[str, int, int]:
    last = None
    for attempt in range(3):
        try:
            r = await http().post("https://api.deepinfra.com/v1/openai/chat/completions",
                                  json={"model": FRONTIER, "messages": [{"role": "user", "content": prompt}],
                                        "max_tokens": 300, "temperature": 0, "chat_template_kwargs": {"enable_thinking": False}})
            if r.status_code in (429, 500, 502, 503, 504):
                last = RuntimeError(f"DeepInfra HTTP {r.status_code}")
                await asyncio.sleep(1 + attempt)
                continue
            r.raise_for_status()
            j = r.json()
            u = j.get("usage", {})
            txt = re.sub(r"<think>.*?</think>", "", j["choices"][0]["message"]["content"] or "", flags=re.S)
            return txt, u.get("prompt_tokens", 0), u.get("completion_tokens", 0)
        except httpx.HTTPError as e:
            last = e
            await asyncio.sleep(1 + attempt)
    raise RuntimeError(str(last))


def _json(txt: str) -> dict:
    m = re.search(r"\{.*\}", txt, re.S)
    try:
        return json.loads(m.group(0)) if m else {}
    except Exception:  # noqa: BLE001
        return {}


async def m_llm1(card, item, snaps):
    t = time.perf_counter()
    prompt = (combined_state(item, snaps) + "\n\nWhat should the buyer do? Options:\n" + "\n".join(f"- {k}: {v}" for k, v in BANDS.items())
              + '\n\nReply with JSON only: {"verdict": "buy" | "buy_with_condition" | "wait"}')
    txt, ti, to = await llm(prompt)
    pred = _json(txt).get("verdict", "?")
    return {"pred": pred if pred in LABELS else "?", "ms": (time.perf_counter() - t) * 1000,
            "cost": ti * LLM_USD_IN + to * LLM_USD_OUT, "tokens": ti + to, "calls": 1, "detail": {"raw": txt[:120]}}


async def m_llmcouncil(card, item, snaps):
    """Same selves, same states, same pooling (stake cap 5, Deal abstains, veto). No negotiation round."""
    states = agent_states(item, snaps)
    t = time.perf_counter()

    async def one(a, s):
        extra = ', "p_bill_unpayable": <0..1>' if a == "budget" else ""
        prompt = (s + f"\n\nQuestion: {REGRET_Q}\nReply with JSON only: "
                      '{"p_regret": <probability 0..1>, "stake": <0..10 how much this matters to you>' + extra + "}")
        txt, ti, to = await llm(prompt)
        return a, _json(txt), ti * LLM_USD_IN + to * LLM_USD_OUT, ti + to

    outs = await asyncio.gather(*(one(a, s) for a, s in states.items() if s))
    ps, ws, cost, toks, veto = {}, {}, 0.0, 0, False
    for a, j, c, tk in outs:
        cost += c
        toks += tk
        try:
            ps[a] = float(j.get("p_regret", 0.5))
            ws[a] = min(max(float(j.get("stake", 5)), 0.5), 5.0)
        except (TypeError, ValueError):
            ps[a], ws[a] = 0.5, 5.0
        if a == "budget":
            try:
                veto = float(j.get("p_bill_unpayable", 0)) >= VETO_THRESHOLD
            except (TypeError, ValueError):
                pass
    p = council.pool(ps, ws)
    pred = "wait" if veto else council.band(p)
    return {"pred": pred, "ms": (time.perf_counter() - t) * 1000, "cost": cost, "tokens": toks, "calls": len(outs),
            "detail": {"p": round(p, 3), "veto": veto, "ps": ps}}


async def m_rules(card, item, snaps):
    """Rules floor: three lines of Python over the shared computed facts. No model."""
    p = F.persona
    dup = bool(p.owned_item) and item.category == "headphones"
    if item.price > p.free_cash:
        pred = "wait"
    elif goals.broken_rule(item) or dup:
        pred = "buy_with_condition"
    else:
        pred = "buy"
    return {"pred": pred, "ms": 0.0, "cost": 0.0, "tokens": 0, "calls": 0, "detail": {}}


METHODS = {"council": m_council, "drex1": m_drex1, "llm1": m_llm1, "llmcouncil": m_llmcouncil, "rules": m_rules}
NAMES = {"council": "Drex council (4 selves + veto + negotiation)", "drex1": "Single Drex call, all facts + band definitions",
         "llm1": f"Single frontier LLM call ({FRONTIER}) + band definitions",
         "llmcouncil": f"Frontier-LLM council (4x {FRONTIER}, same pooling, no negotiation)",
         "rules": "Rules floor (plain Python: over free cash -> wait; rule/duplicate -> condition; else buy)"}


async def main(a):
    if a.neutral:
        enable_neutral()
    await F.load()
    cards_path = HERE / a.cards
    cards = [json.loads(line) for line in cards_path.read_text().splitlines() if line.strip()][:a.limit]
    methods = a.methods.split(",")
    out = HERE / a.out
    prev = {}
    if a.merge and out.exists():
        prev = {r["id"]: r for r in (json.loads(x) for x in out.read_text().splitlines() if x.strip())}
    items = {c["item"]: item_of(c) for c in cards}
    snaps_by = dict(zip(items, await asyncio.gather(*(deal.gather(i, live=False) for i in items.values()))))
    rows = []
    for card in cards:  # persona is global → cards AND methods run sequentially
        apply_card(card)
        item, snaps = item_of(card), snaps_by[card["item"]]
        row = prev.get(card["id"], {})
        row.update({"id": card["id"], "label": card["label"], "item": card["item"], "variant": card["variant"],
                    "price": card["price"], "free_cash": F.persona.free_cash, "neutral": bool(a.neutral)})
        for m in methods:
            try:
                row[m] = await METHODS[m](card, item, snaps)
            except Exception as e:  # noqa: BLE001
                row[m] = {"pred": "error", "ms": None, "cost": 0, "tokens": 0, "calls": 0, "detail": {"err": str(e)[:200]}}
        rows.append(row)
        print(f"{card['id']:16} label={SHORT[card['label']]:4} " + " ".join(f"{m}={SHORT.get(row[m]['pred'], row[m]['pred'])}"
                                                                          for m in methods), flush=True)
    F.use_persona(F.BASE)
    out.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    print(report(rows, [m for m in METHODS if all(m in r for r in rows)]))
    if _http:
        await _http.aclose()


# ---------------------------------------------------------------- metrics
def _acc(rows, m):
    return sum(r[m]["pred"] == r["label"] for r in rows) / len(rows) if rows else float("nan")


def boot_ci(rows, fn, n=4000, seed=7):
    rng = random.Random(seed)
    vals = sorted(fn([rows[rng.randrange(len(rows))] for _ in rows]) for _ in range(n))
    return vals[int(0.025 * n)], vals[int(0.975 * n) - 1]


def macro_f1(rows, m):
    f1s = []
    for c in LABELS:
        tp = sum(r[m]["pred"] == c and r["label"] == c for r in rows)
        fp = sum(r[m]["pred"] == c and r["label"] != c for r in rows)
        fn = sum(r[m]["pred"] != c and r["label"] == c for r in rows)
        f1s.append(2 * tp / (2 * tp + fp + fn) if (2 * tp + fp + fn) else 0.0)
    return sum(f1s) / len(f1s)


def report(rows: list[dict], methods: list[dict]) -> str:
    nv = [r for r in rows if r["price"] <= r["free_cash"]]
    nbuy = sum(r["label"] == "buy" for r in rows)
    L = [f"{len(rows)} cards; labels {dict(Counter(r['label'] for r in rows))}; non-veto subset (price <= free cash): {len(nv)} cards.", "",
         "| Method | Accuracy (95% bootstrap CI) | Non-veto accuracy (CI) | Macro-F1 | False alarms (wait when label=buy) | "
         "Said buy when label=wait | Errors | Median latency | Drex/LLM tokens per verdict | Cost per verdict |",
         "|---|---|---|---|---|---|---|---|---|---|"]
    for m in methods:
        acc = _acc(rows, m)
        lo, hi = boot_ci(rows, lambda rs: _acc(rs, m))
        nacc = _acc(nv, m)
        nlo, nhi = boot_ci(nv, lambda rs: _acc(rs, m)) if nv else (float("nan"),) * 2
        fa = sum(r[m]["pred"] == "wait" and r["label"] == "buy" for r in rows)
        crit = sum(r[m]["pred"] == "buy" and r["label"] == "wait" for r in rows)
        errs = sum(r[m]["pred"] not in LABELS for r in rows)
        lat = [r[m]["ms"] for r in rows if r[m].get("ms")]
        toks = statistics.mean(r[m].get("tokens", 0) for r in rows)
        cost = statistics.mean(r[m]["cost"] for r in rows)
        L.append(f"| {NAMES[m]} | {acc:.0%} ({lo:.0%}–{hi:.0%}) | {nacc:.0%} ({nlo:.0%}–{nhi:.0%}) | {macro_f1(rows, m):.2f} | "
                 f"{fa}/{nbuy} | {crit} | {errs} | {(statistics.median(lat) / 1000) if lat else 0:.2f} s | {toks:,.0f} | ${cost:.5f} |")
    # paired differences vs the floor and vs each baseline
    if "council" in methods:
        L += ["", "Paired bootstrap difference in accuracy (council minus other; 95% CI over cards):", ""]
        for o in methods:
            if o == "council":
                continue
            d = _acc(rows, "council") - _acc(rows, o)
            lo, hi = boot_ci(rows, lambda rs: _acc(rs, "council") - _acc(rs, o))
            L.append(f"- vs {o}: {d:+.0%} ({lo:+.0%} to {hi:+.0%})")
    L += ["", "Confusion matrices (rows = label, columns = prediction: buy / cond / wait / error):", ""]
    for m in methods:
        L.append(f"**{m}**\n")
        L.append("| label \\ pred | buy | cond | wait | err |")
        L.append("|---|---|---|---|---|")
        for lab in LABELS:
            cs = [sum(r["label"] == lab and r[m]["pred"] == p for r in rows) for p in LABELS]
            cs.append(sum(r["label"] == lab and r[m]["pred"] not in LABELS for r in rows))
            L.append(f"| {SHORT[lab]} | " + " | ".join(map(str, cs)) + " |")
        L.append("")
    variants = sorted({r["variant"] for r in rows})
    L += ["Per-variant accuracy:", "", "| Method | " + " | ".join(f"{v} (n={sum(r['variant'] == v for r in rows)})" for v in variants) + " |",
          "|---|" + "---|" * len(variants)]
    for m in methods:
        L.append(f"| {m} | " + " | ".join(f"{sum(r[m]['pred'] == r['label'] for r in rows if r['variant'] == v)}/"
                                         f"{sum(r['variant'] == v for r in rows)}" for v in variants) + " |")
    L += ["", "Per-card predictions:", "", "| Card | Label | " + " | ".join(methods) + " |", "|---|---|" + "---|" * len(methods)]
    for r in rows:
        L.append(f"| {r['id']} {r['item'][:38]} ${r['price']:,.2f} | {SHORT[r['label']]} | "
                 + " | ".join(("**" if r[m]["pred"] != r["label"] else "") + SHORT.get(r[m]["pred"], r[m]["pred"])
                              + ("**" if r[m]["pred"] != r["label"] else "") for m in methods) + " |")
    return "\n".join(L)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--cards", default="cards.jsonl")
    ap.add_argument("--out", default="results_v3.jsonl")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--methods", default="council,drex1,llm1,llmcouncil,rules")
    ap.add_argument("--neutral", action="store_true")
    ap.add_argument("--merge", action="store_true")
    ap.add_argument("--report", help="print metrics for an existing results file and exit")
    a = ap.parse_args()
    if a.report:
        rs = [json.loads(x) for x in (HERE / a.report).read_text().splitlines() if x.strip()]
        print(report(rs, [m for m in METHODS if all(m in r for r in rs)]))
    else:
        asyncio.run(main(a))
