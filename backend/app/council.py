"""The council: perceive → round one (parallel) → veto → pool → negotiate → bands → verdict. Streams events."""

from __future__ import annotations

import asyncio
import base64
import io
import math
import time
from typing import Any, AsyncIterator

from PIL import Image

from . import drex, facts as F, ledger, ndi, tradeoffs, voice
from .agents import budget, deal, goals, owned
from .agents.base import REGRET_Q, Item, Vote
from .config import BAND_HIGH, BAND_LOW, FRAMES, VETO_THRESHOLD

DEMO_ITEMS = {
    "shoes": {"name": "ASICS Gel-Nimbus 27 Running Shoes", "category": "running_gear", "price": 109.95, "frame": "price_tag_shoes.jpg"},
    "headphones": {"name": "Sony WH-1000XM6 Headphones", "category": "headphones", "price": 349.0, "frame": "price_tag_headphones.jpg"},
    "macmini": {"name": "Apple Mac mini (M5, 16GB)", "category": "computer", "price": 599.0, "frame": "price_tag_macmini.jpg"},
}
CATEGORIES = {"running_gear": "Running shoes or running apparel", "headphones": "Headphones or earbuds",
              "computer": "Desktop or laptop computer", "gadget": "Other consumer electronics (phone, watch, tablet, camera)",
              "clothing": "Everyday clothing or shoes not for running", "other": None}
BUCKETS = {"under_100": "Less than $100", "100_199": "$100 to $199.99", "200_399": "$200 to $399.99",
           "400_799": "$400 to $799.99", "800_plus": "$800 or more", "none": "No price visible"}
BUCKET_MID = {"under_100": 60.0, "100_199": 150.0, "200_399": 300.0, "400_799": 600.0, "800_plus": 1000.0}
PRICE_SCHEMA = {"type": "object", "properties": {"product_name": {"type": "string", "description": "Product name on the tag or packaging"},
                                                  "price": {"type": "number", "description": "Price in USD"}}, "required": ["price"]}
AGENTS = ["budget", "goals", "owned", "deal"]


# ---------------------------------------------------------------- math
def logit(p: float) -> float:
    p = min(max(p, 1e-4), 1 - 1e-4)
    return math.log(p / (1 - p))


def pool(ps: dict[str, float], weights: dict[str, float]) -> float:
    num = sum(weights[a] * logit(p) for a, p in ps.items())
    den = sum(weights[a] for a in ps) or 1.0
    return 1 / (1 + math.exp(-num / den))


def band(p: float) -> str:
    return "buy" if p < BAND_LOW else ("wait" if p > BAND_HIGH else "buy_with_condition")


TITLES = {"buy": "Buy it", "buy_with_condition": "Buy — with a condition", "wait": "Wait"}


def price_terms(item: Item) -> dict:
    p = F.persona
    return {"hours_of_work": round(item.price / p.hourly, 1), "japan_slip_days": goals.slip_days(item.price),
            "pct_free_cash": round(item.price / p.free_cash * 100) if p.free_cash > 0 else None}


# ---------------------------------------------------------------- perceive
def _jpeg_data_url(raw: bytes, max_side: int = 1024) -> tuple[str, bytes]:
    im = Image.open(io.BytesIO(raw)).convert("RGB")
    im.thumbnail((max_side, max_side))
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=85)
    b = buf.getvalue()
    return "data:image/jpeg;base64," + base64.b64encode(b).decode(), b


async def perceive(req: dict) -> dict:
    t = time.perf_counter()
    demo = DEMO_ITEMS.get(req.get("demo_item") or "")
    if demo:
        raw = (FRAMES / demo["frame"]).read_bytes()
    elif req.get("frame"):
        raw = base64.b64decode(req["frame"].split(",", 1)[-1])
    else:
        raise ValueError("send demo_item or frame")
    data_url, jpeg = _jpeg_data_url(raw)

    async def look():
        res = await drex.ask("Image 1 shows something Maya is about to buy.", {
            "category": drex.choice("What kind of item is shown in Image 1?", CATEGORIES),
            "price_bucket": drex.choice("What price is shown for the item in Image 1?", BUCKETS)},
            images=[data_url], note="perceive")
        return res["answers"]

    async def read_price():
        try:
            r = await ndi.extract(None, PRICE_SCHEMA, data=jpeg, name="frame.jpg")
            return r.get("data") or {}
        except Exception:  # noqa: BLE001
            return {}

    need_ndi = req.get("price") is None
    look_a, price_d = await asyncio.gather(look(), read_price() if need_ndi else asyncio.sleep(0, {}))
    cat = look_a["category"]["choice"]
    bucket = look_a["price_bucket"]["choice"]
    if req.get("price") is not None:
        price, src = float(req["price"]), "manual"
    elif price_d.get("price"):
        price, src = float(price_d["price"]), "ndi"
    elif demo:
        price, src = demo["price"], "cache"
    else:
        price, src = BUCKET_MID.get(bucket, 100.0), "bucket"
    name = req.get("item_name") or price_d.get("product_name") or (demo or {}).get("name") or cat.replace("_", " ").title()
    return {"type": "perceive", "item_name": name, "category": cat, "category_p": round(look_a["category"]["confidence"], 3),
            "price_bucket": bucket, "price": price, "price_source": src, "ms": round((time.perf_counter() - t) * 1000)}


# ---------------------------------------------------------------- negotiation
async def _agent_offer_scan(agent: str, v: Vote, offers: list[tradeoffs.Offer]) -> dict:
    """ONE Drex call per agent: regret under each offer (batched nouls) + which offer it prefers."""
    qs: dict[str, dict] = {f"if_{o.id}": drex.noul(f"Suppose: {o.commitment} {REGRET_Q}") for o in offers}
    qs["preferred"] = drex.choice("Which single commitment would most reduce your concern about this purchase?",
                                  {**{o.id: o.label for o in offers}, "none": "None of these would change my view"})
    res = await drex.ask(v.state, qs, note=f"negotiate:{agent}")
    a = res["answers"]
    return {"agent": agent, "p": {o.id: a[f"if_{o.id}"]["noul"] for o in offers}, "preferred": a["preferred"]["choice"]}


async def negotiate(item: Item, votes: dict[str, Vote], weights: dict[str, float]) -> dict:
    t = time.perf_counter()
    offs = tradeoffs.offers(item)
    scans = await asyncio.gather(*(_agent_offer_scan(a, v, offs) for a, v in votes.items()), return_exceptions=True)
    scans = [s for s in scans if isinstance(s, dict)]
    by_agent = {s["agent"]: s for s in scans}
    pooled = {}
    for o in offs:  # fixed order; ties keep the earlier offer
        ps = {a: by_agent[a]["p"][o.id] if a in by_agent else votes[a].p_regret for a in votes}
        pooled[o.id] = pool(ps, weights)
    best = min(offs, key=lambda o: pooled[o.id])
    dissenters = [a for a, v in votes.items() if v.stance == "wait"]
    picks = [{"agent": a, "offer_id": by_agent[a]["preferred"], "p_before": round(votes[a].p_regret, 4),
              "p_after": round(by_agent[a]["p"].get(best.id, votes[a].p_regret), 4)} for a in dissenters if a in by_agent]
    return {"type": "negotiation", "offers": [o.event() for o in offs], "picks": picks,
            "chosen": {**best.event(), "p_after": round(pooled[best.id], 4)},
            "pooled_by_offer": {k: round(v, 4) for k, v in pooled.items()},
            "ms": round((time.perf_counter() - t) * 1000)}


# ---------------------------------------------------------------- main stream
async def run(req: dict) -> AsyncIterator[dict]:
    t0 = time.perf_counter()
    yield {"type": "perceive_start"}
    per = await perceive(req)
    yield per
    item = Item(per["item_name"], per["category"], per["price"])

    # Deal You needs web facts; use cache when warm, otherwise a bounded live search.
    snaps = await deal.gather(item)
    async for ev in deliberate(item, snaps, t0):
        yield ev


async def deliberate(item: Item, snaps: list[dict], t0: float | None = None, speak: bool = True) -> AsyncIterator[dict]:
    """Round one → veto → pool → negotiate → verdict (→ sentence). Used by the live stream and the benchmark."""
    t0 = t0 or time.perf_counter()
    t_council = time.perf_counter()
    yield {"type": "council_start", "agents": AGENTS}
    tasks = {
        asyncio.create_task(budget.vote(item)): "budget",
        asyncio.create_task(goals.vote(item)): "goals",
        asyncio.create_task(owned.vote(item)): "owned",
        asyncio.create_task(deal.vote(item, snaps)): "deal",
    }
    votes: dict[str, Vote] = {}
    for fut in asyncio.as_completed(list(tasks), timeout=12):
        try:
            v = await fut
            votes[v.agent] = v
            yield v.event()
        except Exception as e:  # noqa: BLE001  — a failed self drops out of the pool, never crashes the council
            yield {"type": "agent_error", "message": f"{type(e).__name__}: {str(e)[:160]}"}
    if not votes:
        yield {"type": "error", "message": "No agent could vote (Drex unreachable?)"}
        return

    weights = {a: max(v.stake, 0.5) for a, v in votes.items()}
    ps = {a: v.p_regret for a, v in votes.items()}
    p = pool(ps, weights)
    condition = None
    veto_fired = False
    if "budget" in votes:
        pu = votes["budget"].extra["p_unpayable"]
        veto_fired = pu >= VETO_THRESHOLD
        rent = F.persona.rent
        yield {"type": "veto", "agent": "budget", "p": round(pu, 4), "threshold": VETO_THRESHOLD, "fired": veto_fired,
               "reason": f"{rent['payee']} ${rent['amount']:,.0f} on {rent['date']} becomes unpayable" if veto_fired else None}
    b = band(p)
    yield {"type": "pool", "p": round(p, 4), "band": b, "weights": {a: round(w, 2) for a, w in weights.items()}}

    final_p = p
    if veto_fired:
        b, condition = "wait", f"Wait until payday ({F.persona.next_payday[5:].replace('-', '/')})"
    elif b != "buy":
        # Any split or "wait" without a veto: ask every self what would change its mind (all Drex calls).
        neg = await negotiate(item, votes, weights)
        yield neg
        final_p = neg["chosen"]["p_after"]
        condition = neg["chosen"]["label"]
        b = "buy_with_condition" if final_p < BAND_HIGH else "wait"
        if b == "wait":
            condition = f"Best option: {condition}"
    tally = {"buy": sum(v.stance == "buy" for v in votes.values()), "wait": sum(v.stance == "wait" for v in votes.values())}
    verdict = {"type": "verdict", "band": b, "title": TITLES[b], "p": round(final_p, 4), "p_round_one": round(p, 4),
               "condition": condition, "veto": veto_fired, "tally": tally, "price_terms": price_terms(item),
               "item": {"name": item.name, "price": item.price, "category": item.category},
               "total_ms": round((time.perf_counter() - t0) * 1000),
               "council_ms": round((time.perf_counter() - t_council) * 1000)}
    ledger.count_verdict()
    verdict["_votes"] = {a: {"p": v.p_regret, "stake": v.stake} for a, v in votes.items()}
    yield verdict
    if speak:
        yield await voice.sentence(verdict, votes)
    yield {"type": "done"}
