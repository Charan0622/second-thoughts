from __future__ import annotations

import asyncio
import re

from .. import drex, keenable_client
from ..facts import Fact
from .base import Item, Vote, ask_council_member, build_state, pick_citation

LABEL = "Deal You"
BLACK_FRIDAY = "2026-11-27"


def queries(item: Item) -> list[str]:
    return [f"{item.name} price", f"{item.name} Black Friday 2026 deal"]


async def gather(item: Item, live: bool = True) -> list[dict]:
    """Both searches in parallel, capped at 3.5 s total (cache hits are instant)."""
    async def one(q):
        try:
            return await asyncio.wait_for(keenable_client.search(q, item.price, max_age_s=6 * 3600 if live else 10**9,
                                                                 timeout=3.5), 4.0)
        except Exception:  # noqa: BLE001
            return None
    res = await asyncio.gather(*(one(q) for q in queries(item)))
    return [r for r in res if r]


STOP = {"the", "and", "with", "for", "new", "shoes", "running", "price", "black", "friday", "deal", "inch", "gb", "tb"}


def _tokens(name: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9]+", name.lower()) if len(t) >= 3 and t not in STOP}


def typical_low(prices: list[float]) -> float:
    ps = sorted(prices)
    return ps[len(ps) // 4]


def on_topic_prices(item: Item, snaps: list[dict]) -> tuple[list[float], list[dict]]:
    """Prices only from '<name> price' results whose title shares ≥2 name tokens (or 1 if the name has only 1)."""
    toks = _tokens(item.name)
    need = 1 if len(toks) <= 1 else 2
    prices, hits = [], []
    for s in snaps:
        if "black friday" in s.get("query", "").lower():
            continue
        for r in s.get("results") or []:
            title_toks = _tokens(r["title"])
            if len(toks & title_toks) >= need:
                ps = keenable_client.prices_near(r["title"] + " " + r["snippet"], item.price)
                if ps:
                    prices += ps
                    hits.append(r)
    return prices, hits


def web_facts(item: Item, snaps: list[dict]) -> tuple[list[Fact], list[str]]:
    fs: list[Fact] = []
    prices, hits = on_topic_prices(item, snaps)
    bf = any(s.get("black_friday_mentioned") for s in snaps)
    cached = any(s.get("cached") for s in snaps)
    for ri, r in enumerate((hits or [r for s in snaps for r in (s.get("results") or [])])[:5]):
        label = "Live web · Keenable" + (" (cached)" if cached else "")
        fs.append(Fact(id=f"deal_{ri}", agent="deal", text=f"{r['host'] or 'web'}: {r['title']}",
                       doc=r["url"] or r["host"], doc_label=label, quote=(r["snippet"] or r["title"])[:220]))
    computed = [f"Black Friday is {BLACK_FRIDAY} — {_days_to(BLACK_FRIDAY)} days away.",
                f"Even a generous 20% discount would save only about ${0.2 * item.price:,.0f} on this item."]
    if len(prices) >= 3:
        lo = typical_low(prices)
        computed.append(f"Prices for this exact product on the live web: {len(prices)} mentions; typical low (25th percentile) "
                        f"${lo:,.2f}. The asking price is ${item.price:,.2f}.")
        if item.price <= lo * 1.05:
            computed.append("The asking price is at or below the typical low price on the web — a good price.")
        else:
            computed.append(f"The asking price is {round((item.price / lo - 1) * 100)}% above the typical low price on the web.")
    else:
        computed.append("Not enough reliable prices for this exact product were found on the web.")
    if bf:
        computed.append("Search results mention Black Friday deals for this kind of item.")
    return fs[:6], computed


def _days_to(d: str) -> int:
    from datetime import date
    from .. import facts as F
    try:
        from datetime import datetime
        today = datetime.strptime(F.persona.today, "%A, %B %d, %Y").date()
    except ValueError:
        today = date.today()
    return max(0, (date.fromisoformat(d) - today).days)


def _abstain(item: Item, why: str) -> Vote:
    cit = {"doc": "keenable", "doc_label": "Live web · Keenable", "page": None, "quote": why, "bbox": None, "crop_url": None}
    return Vote("deal", LABEL, 0.5, 0.0, why, cit, 0.0, "—", 0.0, extra={"abstain": True}, state="")


async def vote(item: Item, snaps: list[dict], extra: str | None = None) -> Vote:
    if getattr(item, "name_source", "ndi") == "category":
        return _abstain(item, "Couldn't identify the exact product — no price check (not counted)")
    prices, _ = on_topic_prices(item, snaps)
    if len(prices) < 3:
        return _abstain(item, "Not enough reliable prices online for this product (not counted)")
    fs, computed = web_facts(item, snaps)
    if extra:
        computed.append(extra)
    state = build_state(LABEL, "make sure the buyer pays a good price, and say when waiting for a better deal would win.", fs,
                        computed, item)
    answers, res = await ask_council_member(
        agent="deal", label=LABEL, state=state, facts=fs,
        regret_true="Waiting or shopping elsewhere would likely save at least 15% AND at least $25 on this exact item",
        regret_false="The price is near the typical low, or the possible saving is small in dollars (under $25)",
        extra_q={"wait_wins": drex.noul("Would waiting until Black Friday likely save the buyer meaningful money on this item?")})
    cit, cp = pick_citation(answers, fs)
    lo = typical_low(prices)
    p_reg = answers["regret"]["noul"]
    if p_reg >= 0.5:   # headline follows the vote
        headline = (f"{round((item.price / lo - 1) * 100)}% above the typical ${lo:,.0f} — shop around" if item.price > lo * 1.05
                    else f"Black Friday in {_days_to(BLACK_FRIDAY)} days — waiting likely wins")
    elif item.price < lo * 0.97:
        headline = f"Good price — typically ${lo:,.0f} elsewhere"
    elif item.price <= lo * 1.05:
        headline = f"Matches the typical low price (${lo:,.0f})"
    else:
        headline = "Fair price — waiting won't save much"
    return Vote("deal", LABEL, p_reg, answers["stake"]["score"], headline, cit, cp,
                res["model"], res["ms"], extra={"p_wait_wins": answers["wait_wins"]["noul"]}, state=state)
