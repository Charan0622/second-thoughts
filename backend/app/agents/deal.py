from __future__ import annotations

from .. import drex, keenable_client
from ..facts import Fact
from .base import Item, Vote, ask_council_member, build_state, pick_citation

LABEL = "Deal You"
BLACK_FRIDAY = "2026-11-27"


def queries(item: Item) -> list[str]:
    return [f"{item.name} price", f"{item.name} Black Friday 2026 deal"]


async def gather(item: Item, live: bool = True) -> list[dict]:
    out = []
    for q in queries(item):
        r = await keenable_client.search(q, item.price, max_age_s=6 * 3600 if live else 10**9)
        if r:
            out.append(r)
    return out


def typical_low(prices: list[float]) -> float:
    ps = sorted(prices)
    return ps[len(ps) // 4]


def web_facts(item: Item, snaps: list[dict]) -> tuple[list[Fact], list[str]]:
    fs: list[Fact] = []
    prices: list[float] = []
    bf = False
    for si, s in enumerate(snaps):
        prices += s.get("prices") or []
        bf = bf or s.get("black_friday_mentioned", False)
        for ri, r in enumerate((s.get("results") or [])[:3]):
            label = "Live web · Keenable" + (" (cached)" if s.get("cached") else "")
            fs.append(Fact(id=f"deal_{si}_{ri}", agent="deal", text=f"{r['host'] or 'web'}: {r['title']}",
                           doc=r["url"] or r["host"], doc_label=label, quote=(r["snippet"] or r["title"])[:220]))
    computed = [f"Black Friday is {BLACK_FRIDAY} — 13 days away — and is also Maya's next payday.",
                f"Even a generous 20% discount would save only about ${0.2 * item.price:,.0f} on this item."]
    if prices:
        lo = typical_low(prices)
        computed.append(f"Prices seen on the live web: {len(prices)} mentions; typical low (25th percentile) ${lo:,.2f}. "
                        f"The asking price is ${item.price:,.2f}.")
        if item.price <= lo * 1.05:
            computed.append("The asking price is at or below the typical low price on the web — a good price.")
        else:
            computed.append(f"The asking price is {round((item.price / lo - 1) * 100)}% above the typical low price on the web.")
    else:
        computed.append("No comparable prices were found on the live web.")
    if bf:
        computed.append("Search results mention Black Friday deals for this kind of item.")
    return fs[:6], computed


async def vote(item: Item, snaps: list[dict], extra: str | None = None) -> Vote:
    fs, computed = web_facts(item, snaps)
    if extra:
        computed.append(extra)
    state = build_state(LABEL, "make sure Maya pays a good price, and say when waiting for a better deal would win.", fs,
                        computed, item)
    answers, res = await ask_council_member(
        agent="deal", label=LABEL, state=state, facts=fs,
        regret_true="Waiting or shopping elsewhere would likely save at least 15% AND at least $25 on this exact item",
        regret_false="The price is near the typical low, or the possible saving is small in dollars (under $25)",
        extra_q={"wait_wins": drex.noul("Would waiting until Black Friday likely save Maya meaningful money on this item?")})
    cit, cp = pick_citation(answers, fs)
    prices = [p for s in snaps for p in (s.get("prices") or [])]
    lo = typical_low(prices) if prices else None
    if lo and item.price < lo * 0.97:
        headline = f"Good price — typically ${lo:,.0f} elsewhere"
    elif lo and item.price <= lo * 1.05:
        headline = f"Matches the typical low price (${lo:,.0f})"
    elif answers["wait_wins"]["noul"] >= 0.5:
        headline = "Black Friday in 13 days — waiting likely wins"
    else:
        headline = "Fair price — waiting won't save much"
    if not cit:
        cit = {"doc": "keenable", "doc_label": "Live web · Keenable", "page": None, "quote": "No web results", "bbox": None,
               "crop_url": None}
    return Vote("deal", LABEL, answers["regret"]["noul"], answers["stake"]["score"], headline, cit, cp,
                res["model"], res["ms"], extra={"p_wait_wins": answers["wait_wins"]["noul"]}, state=state)
