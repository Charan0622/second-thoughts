"""The council: perceive → round one (parallel) → veto → pool → negotiate → bands → verdict. Streams events."""

from __future__ import annotations

import asyncio
import base64
import io
import math
import time
from typing import Any, AsyncIterator

from PIL import Image

from . import drex, facts as F, keenable_client, ledger, ndi, tradeoffs, vision, voice
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
              "clothing": "Everyday clothing or shoes not for running", "kitchen_drinkware": "Water bottle, mug, cup or kitchenware",
              "bag": "Backpack, bag or luggage", "book": "Book or magazine", "food": "Food, drink or groceries",
              "home": "Furniture or home goods", "other": None}
BUCKETS = {"under_5": "Less than $5", "5_24": "$5 to $24.99", "25_49": "$25 to $49.99", "50_99": "$50 to $99.99", "100_199": "$100 to $199.99",
           "200_399": "$200 to $399.99", "400_799": "$400 to $799.99", "800_plus": "$800 or more",
           "non_usd": "A price in a currency other than US dollars", "none": "No price visible"}
PRICE_SCHEMA = {"type": "object", "properties": {
    "product_name": {"type": "string", "description": "Brand and model of the product on the tag or packaging"},
    "price": {"type": "number", "description": "The current selling price as a number (the 'now'/sale price if two are shown)"},
    "currency": {"type": "string", "description": "ISO currency code of that price, e.g. USD, EUR, GBP"},
    "was_price": {"type": "number", "description": "The original/'was' price if a crossed-out or 'was' price is shown"}},
    "required": ["price"]}
FX_TO_USD = {"USD": 1.0, "EUR": 1.08, "GBP": 1.27, "CAD": 0.72, "AUD": 0.65, "INR": 0.012, "JPY": 0.0066, "MXN": 0.055}
# USD range [lo, hi) per Drex price bucket; "non_usd"/"none" carry no range. under_25 kept for old cached answers.
BUCKET_RANGE = {"under_5": (0.0, 5.0), "5_24": (5.0, 25.0), "under_25": (0.0, 25.0), "25_49": (25.0, 50.0),
                "50_99": (50.0, 100.0), "100_199": (100.0, 200.0), "200_399": (200.0, 400.0),
                "400_799": (400.0, 800.0), "800_plus": (800.0, math.inf)}
BUCKET_SLACK = 2.0  # "clearly outside" = more than 2x beyond the bucket edge (Drex buckets are coarse)


class NeedsInput(Exception):
    """Perception couldn't establish something we refuse to guess (price, or that there is an item at all)."""
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
    fits = item.price <= p.free_cash
    return {"hours_of_work": round(item.price / p.net_hourly, 1),            # take-home pay, not gross
            "japan_slip_days": 0 if fits else goals.slip_days(item.price - max(p.free_cash, 0)),
            "japan_slip_if_from_savings": goals.slip_days(item.price),
            "goal_name": p.goal_short,
            "pct_free_cash": round(item.price / p.free_cash * 100) if p.free_cash > 0 else None}


# ---------------------------------------------------------------- perceive
try:  # iPhone / macOS photos and screenshots are often HEIC
    from pillow_heif import register_heif_opener
    register_heif_opener()
except Exception:  # noqa: BLE001
    pass


class ConfirmPrice(Exception):
    """No price visible, but we identified the product and found its price online: ask the user to confirm."""
    def __init__(self, payload: dict):
        super().__init__("confirm price")
        self.payload = payload


async def web_price(name: str) -> dict | None:
    """Look the product up on the live web (Keenable) → typical price + sources. Never invents: None if unclear."""
    from .agents import deal as _deal
    try:
        r = await asyncio.wait_for(keenable_client.search(f"{name} price buy", None, timeout=4.0), 5.0)
    except Exception:  # noqa: BLE001
        return None
    if not r:
        return None
    toks = _deal._tokens(name)
    need = 1 if len(toks) <= 1 else 2
    found = []
    finance = ("robinhood", "marketbeat", "nasdaq", "nyse", "stock", "finance", "investing", "seekingalpha", "fool.com", "macrotrends")
    for res in r.get("results") or []:
        if any(f in (res.get("host") or "").lower() or f in res["title"].lower() for f in finance):
            continue  # a brand name alone pulls in share prices — never a product price
        if len(toks & _deal._tokens(res["title"])) < need:
            continue
        for p in keenable_client.prices_near(res["title"] + " " + res["snippet"], None):
            if 1 <= p <= 20000:
                found.append((p, res.get("host") or "web"))
    if not found:
        return None
    ps = sorted(p for p, _ in found)
    med = ps[len(ps) // 2]
    keep = [(p, h) for p, h in found if 0.6 * med <= p <= 1.6 * med]
    if not keep:
        return None
    kp = sorted(p for p, _ in keep)
    typical = kp[len(kp) // 2]
    seen_hosts, sources = set(), []
    for p, h in sorted(keep, key=lambda x: abs(x[0] - typical)):
        if h not in seen_hosts:
            seen_hosts.add(h)
            sources.append({"host": h, "price": p})
    return {"suggested_price": round(typical, 2), "sources": sources[:4], "n": len(kp), "query": f"{name} price"}


def _jpeg_data_url(raw: bytes, max_side: int = 1024) -> tuple[str, bytes]:
    im = Image.open(io.BytesIO(raw)).convert("RGB")
    im.thumbnail((max_side, max_side))
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=85)
    b = buf.getvalue()
    return "data:image/jpeg;base64," + base64.b64encode(b).decode(), b


VISION_MIN_CONF = 0.35  # below this the VL model's price read is ignored


def to_usd(amt: float, cur: str | None) -> tuple[float, str | None]:
    """(usd, note). Unknown currency → NeedsInput (we never guess an exchange rate)."""
    cur = str(cur or "USD").upper().strip()[:3]
    if cur not in FX_TO_USD:
        raise NeedsInput(f"The tag shows a price in {cur}; type the price in US dollars")
    if cur == "USD":
        return float(amt), None
    return round(float(amt) * FX_TO_USD[cur], 2), f"converted from {float(amt):,.2f} {cur}"


def bucket_agrees(price: float, bucket: str | None) -> bool | None:
    """None when the bucket carries no range; else whether price is not *clearly* outside it."""
    rng = BUCKET_RANGE.get(bucket or "")
    if rng is None:
        return None
    lo, hi = rng
    return lo / BUCKET_SLACK <= price <= hi * BUCKET_SLACK


def resolve_price(manual: float | None, ndi_read: dict | None, vision_read: dict | None, bucket: str | None,
                  cache: float | None = None) -> tuple[float, str, str | None]:
    """Pure price resolution → (usd_price, source, note). Order: manual > NDI > vision > cache, then a sanity
    check against Drex's price bucket: a read clearly outside the bucket loses to one that agrees; if none
    agrees, ask the user. Manual prices are never second-guessed."""
    if manual is not None:
        return float(manual), "manual", None
    cands: list[tuple[float, str, str | None]] = []
    cur_err: NeedsInput | None = None
    for src, r in (("ndi", ndi_read), ("vision", vision_read)):
        if not r or not r.get("price"):
            continue
        if src == "vision" and float(r.get("confidence") or 0) < VISION_MIN_CONF:
            continue
        try:
            amt = float(r["price"])
        except (TypeError, ValueError):
            continue
        if amt <= 0:
            continue
        try:
            usd, note = to_usd(amt, r.get("currency"))
        except NeedsInput as e:
            cur_err = cur_err or e
            continue
        cands.append((usd, src, note))
    if cache is not None:
        cands.append((float(cache), "cache", None))
    if not cands:
        raise cur_err or NeedsInput("I couldn't read a price — type it in the Price box and ask again")
    if all(bucket_agrees(c[0], bucket) is None for c in cands):
        return cands[0]
    for c in cands:
        if bucket_agrees(c[0], bucket):
            return c
    if cache is not None:  # demo frames: the known price beats a coarse bucket
        return cands[-1]
    raise NeedsInput(f"I read ${cands[0][0]:,.2f} but the tag looks like {BUCKETS[bucket].lower()} — "
                     "please type the price")


async def perceive(req: dict) -> dict:
    t = time.perf_counter()
    demo = DEMO_ITEMS.get(req.get("demo_item") or "")
    if req.get("demo_item") and not demo:
        raise NeedsInput(f"Unknown demo item '{req.get('demo_item')}'")
    if demo:
        raw = (FRAMES / demo["frame"]).read_bytes()
    elif req.get("frame"):
        try:
            raw = base64.b64decode(req["frame"].split(",", 1)[-1], validate=False)
        except Exception as e:  # noqa: BLE001
            raise NeedsInput("That frame isn't a valid image") from e
    else:
        raise NeedsInput("Send a demo item or a camera frame")
    try:
        data_url, jpeg = _jpeg_data_url(raw)
    except Exception as e:  # noqa: BLE001
        raise NeedsInput("That frame isn't a readable image (JPEG/PNG/WebP)") from e
    manual = req.get("price")
    if manual is not None:
        try:
            manual = float(manual)
        except (TypeError, ValueError):
            raise NeedsInput("Price must be a number") from None
        if manual <= 0:
            raise NeedsInput("Price must be greater than $0")

    async def look():
        try:
            res = await drex.ask("Image 1 shows something the buyer may be about to buy.", {
                "item_present": drex.noul("Does Image 1 show a specific product someone could buy (not an empty scene)?"),
                "tag_visible": drex.noul("Is a price tag, price label or on-screen price visible in Image 1?"),
                "category": drex.choice("What kind of item is shown in Image 1?", CATEGORIES),
                "price_bucket": drex.choice("What price is shown for the item in Image 1?", BUCKETS)},
                images=[data_url], note="perceive")
            return res["answers"]
        except Exception:  # noqa: BLE001  — fall back to manual category rather than crash the stream
            return None

    async def read_tag():  # always run: it gives the product NAME even when the price is typed in
        try:
            r = await asyncio.wait_for(ndi.extract(None, PRICE_SCHEMA, data=jpeg, name="frame.jpg"), 8)
            return r.get("data") or {}
        except Exception:  # noqa: BLE001
            return {}

    async def nothing():
        return {}
    # Demo frames have a known price, so skip the ~4 s vision read; live photos use all three readers in parallel.
    ndi_task = asyncio.create_task(read_tag())
    look_a, seen = await asyncio.gather(look(), nothing() if demo else vision.read_tag(data_url))
    confident = bool(seen and seen.get("price") and float(seen.get("confidence") or 0) >= 0.6 and seen.get("product_name"))
    try:   # NDI is the slowest reader; once vision has a confident read, give it only a moment longer
        tag = await asyncio.wait_for(asyncio.shield(ndi_task), 1.0 if confident or demo else 6.0)
    except asyncio.TimeoutError:
        tag = {}
    if look_a is None:
        cat, cat_p, bucket, present, tag_vis = (demo or {}).get("category", "other"), 0.0, "none", 1.0, 0.0
    else:
        cat, cat_p = look_a["category"]["choice"], look_a["category"]["confidence"]
        bucket = look_a["price_bucket"]["choice"]
        present, tag_vis = look_a["item_present"]["noul"], look_a["tag_visible"]["noul"]
    if not demo and present < 0.5 and manual is None:
        raise NeedsInput("I can't see a product in that photo — point the camera at the item (and its price tag)")

    tag_name = (tag.get("product_name") or "").strip()
    seen_name = vision.display_name(seen) if seen else ""
    try:
        price, src, note = resolve_price(manual, tag, seen, bucket, cache=demo["price"] if demo else None)
    except NeedsInput:
        guess_name = req.get("item_name") or (tag_name if len(tag_name) >= 3 else "") or (seen_name if len(seen_name) >= 3 else "")
        if not guess_name:
            raise NeedsInput("I couldn't identify the product or read a price — type the price (and name) and ask again") from None
        from .agents.deal import _tokens
        if len(_tokens(guess_name)) < 2:   # only a brand is visible: search "<brand> <what it is>"
            kind = (seen or {}).get("product_type") or cat.replace("_", " ")
            guess_name = f"{guess_name.title()} {kind}".strip()
        wp = await web_price(guess_name)
        raise ConfirmPrice({"type": "confirm_price", "item_name": guess_name, "category": cat,
                            "suggested_price": (wp or {}).get("suggested_price"), "sources": (wp or {}).get("sources", []),
                            "message": (f"No price in the photo. Online, {guess_name} is about ${wp['suggested_price']:,.2f}. Is that what you'd pay?"
                                        if wp else f"No price in the photo, and I couldn't find a reliable one online for {guess_name}. What does it cost?")}) from None
    if req.get("item_name"):
        name, name_src = req["item_name"], "manual"
    elif tag_name and len(tag_name) >= 3:
        name, name_src = tag_name, "ndi"
    elif seen_name and len(seen_name) >= 3:
        name, name_src = seen_name, "vision"
    elif demo:
        name, name_src = demo["name"], "cache"
    else:
        name, name_src = cat.replace("_", " ").title(), "category"
    out = {"type": "perceive", "item_name": name, "name_source": name_src, "category": cat, "category_p": round(cat_p, 3),
           "price_bucket": bucket, "price": price, "price_source": src, "tag_visible": round(tag_vis, 3),
           "ms": round((time.perf_counter() - t) * 1000)}
    if note:
        out["price_note"] = note
    was = (seen or {}).get("was_price") if src == "vision" else tag.get("was_price")
    if was:
        out["was_price"] = was
    if seen.get("price_text"):
        out["vision_price_text"] = seen["price_text"]
    return out


# ---------------------------------------------------------------- negotiation
async def _agent_offer_scan(agent: str, v: Vote, offers: list[tradeoffs.Offer]) -> dict:
    """ONE Drex call per agent: regret under each offer (batched nouls) + which offer it prefers."""
    qs: dict[str, dict] = {f"if_{o.id}": drex.noul(f"Suppose: {o.commitment} {REGRET_Q}") for o in offers}
    qs["preferred"] = drex.choice("Which single commitment would most reduce your concern about this purchase?",
                                  {**{o.id: o.label for o in offers}, "none": "None of these would change my view"})
    res = await drex.ask(v.state, qs, note=f"negotiate:{agent}")
    a = res["answers"]
    return {"agent": agent, "p": {o.id: a[f"if_{o.id}"]["noul"] for o in offers}, "preferred": a["preferred"]["choice"]}


async def negotiate(item: Item, votes: dict[str, Vote], weights: dict[str, float], say=None) -> dict:
    """`say` (optional callback) receives one first-person "say" event per self as soon as its scan lands."""
    t = time.perf_counter()
    dup = votes["owned"].extra.get("p_duplicate", 0) >= 0.5 if "owned" in votes else None
    offs = tradeoffs.offers(item, owns_similar=dup)
    scans = []
    for fut in asyncio.as_completed([_agent_offer_scan(a, v, offs) for a, v in votes.items()]):
        try:
            s = await fut
        except Exception:  # noqa: BLE001  — same as before: a failed scan just drops out
            continue
        scans.append(s)
        if say is not None:
            a, before = s["agent"], votes[s["agent"]].p_regret
            o = min(offs, key=lambda o: s["p"][o.id])  # fixed order breaks ties
            after = s["p"][o.id]
            ev = {"type": "say", "agent": a, "phase": "negotiate", "offer_id": o.id,
                  "p_before": round(before, 4), "p_after": round(after, 4)}
            if before < 0.5:
                ev["text"] = f"I was already in. “{o.label}” is fine with me too."
            elif after < 0.5:
                ev["text"] = f"I'd accept: {o.label} ({before:.2f} → {after:.2f})"
            else:
                ev["text"] = "Nothing on the table changes my mind."
            say(ev)
    by_agent = {s["agent"]: s for s in scans}
    pooled = {}
    for o in offs:  # fixed order; ties keep the earlier offer
        ps = {a: by_agent[a]["p"][o.id] if a in by_agent else votes[a].p_regret for a in votes}
        pooled[o.id] = pool(ps, weights)
    dissenters = [a for a, v in votes.items() if v.stance == "wait"]

    def worst_dissent(o):  # highest remaining regret among the selves that objected
        return max((by_agent[a]["p"][o.id] for a in dissenters if a in by_agent), default=0.0)
    resolving = [o for o in offs if worst_dissent(o) < 0.5]
    if resolving:   # among offers that satisfy every dissenter, take the lowest pooled regret (ties keep fixed order)
        best = min(resolving, key=lambda o: pooled[o.id])
    else:           # nothing satisfies them: report the closest, and the verdict stays Wait
        best = min(offs, key=lambda o: (worst_dissent(o), pooled[o.id]))
    picks = [{"agent": a, "offer_id": by_agent[a]["preferred"], "p_before": round(votes[a].p_regret, 4),
              "p_after": round(by_agent[a]["p"].get(best.id, votes[a].p_regret), 4)} for a in dissenters if a in by_agent]
    return {"type": "negotiation", "offers": [o.event() for o in offs], "picks": picks,
            "chosen": {**best.event(), "p_after": round(pooled[best.id], 4), "resolves": bool(resolving),
                       "worst_dissent_after": round(worst_dissent(best), 4)},
            "pooled_by_offer": {k: round(v, 4) for k, v in pooled.items()},
            "ms": round((time.perf_counter() - t) * 1000)}


# ---------------------------------------------------------------- main stream
async def run(req: dict) -> AsyncIterator[dict]:
    t0 = time.perf_counter()
    yield {"type": "perceive_start"}
    try:
        per = await perceive(req)
    except ConfirmPrice as c:
        yield c.payload
        return
    except NeedsInput as e:
        yield {"type": "error", "message": str(e), "needs_input": True}
        return
    yield per
    item = Item(per["item_name"], per["category"], per["price"])
    item.name_source = per.get("name_source", "ndi")  # type: ignore[attr-defined]

    # Deal You needs web facts: cached when warm, otherwise bounded parallel live searches. Unknown product → no search.
    snaps = [] if per.get("name_source") == "category" else await deal.gather(item, live=not req.get("demo_item"))
    async for ev in deliberate(item, snaps, t0):
        yield ev


_SAY_OPEN = {("budget", "buy"): "I'm fine with it", ("budget", "wait"): "I'm worried",
             ("goals", "buy"): "No objection from me", ("goals", "wait"): "I object",
             ("owned", "buy"): "Go ahead", ("owned", "wait"): "Hold on",
             ("deal", "buy"): "I'm in", ("deal", "wait"): "Not at this price"}
_SAY_LOWER = {"Fits", "Tight", "Over", "Breaks", "Running", "No", "Within", "Good", "Matches", "Fair", "Not", "We"}


def _say(agent: str, text: str, phase: str, **kw) -> dict:
    return {"type": "say", "agent": agent, "text": text, "phase": phase, **kw}


def _say_vote(v: Vote) -> dict:
    """One first-person debate line per vote — a template over the vote's own fields (no LLM: zero latency)."""
    quote = (v.citation or {}).get("quote") or None
    cite = {"quote": quote, "doc_label": (v.citation or {}).get("doc_label")} if quote else {}
    if v.stance == "abstain":
        why = ("I can't identify the exact product" if "identify" in v.headline.lower()
               else "I can't find enough reliable prices online")
        return _say(v.agent, f"{why}, so I'm sitting this one out.", "vote", stance="abstain", **cite)
    body = v.headline.strip().rstrip(".")
    for pre in ("Fits: ", "Tight: "):
        body = body.removeprefix(pre)
    body = body.replace("You already own:", "We already own").replace("Your ", "Our ").replace(" your ", " our ")
    body = body.replace(" — ", ", ").replace(" · ", "; ")
    first = body.split(" ", 1)[0]
    if first in _SAY_LOWER:
        body = body[0].lower() + body[1:]
    if v.agent == "goals" and body.startswith("breaks"):
        text = f"This {body}."
    elif v.agent == "budget" and body.startswith("over by"):
        text = f"We can't cover it — {body}."
    else:
        text = f"{_SAY_OPEN.get((v.agent, v.stance), 'My view')} — {body}."
    return _say(v.agent, text, "vote", stance=v.stance, p=round(v.p_regret, 4), **cite)


async def deliberate(item: Item, snaps: list[dict], t0: float | None = None, speak: bool = True) -> AsyncIterator[dict]:
    """Round one → veto → pool → negotiate → verdict (→ sentence). Used by the live stream and the benchmark."""
    t0 = t0 or time.perf_counter()
    t_council = time.perf_counter()
    yield {"type": "council_start", "agents": AGENTS}
    async def tagged(name, coro):
        try:
            return name, await coro, None
        except Exception as e:  # noqa: BLE001  — a failed self drops out of the pool, never crashes the council
            return name, None, e
    tasks = [asyncio.create_task(tagged("budget", budget.vote(item))), asyncio.create_task(tagged("goals", goals.vote(item))),
             asyncio.create_task(tagged("owned", owned.vote(item))), asyncio.create_task(tagged("deal", deal.vote(item, snaps)))]
    votes: dict[str, Vote] = {}
    try:
        for fut in asyncio.as_completed(tasks, timeout=12):
            name, v, err = await fut
            if v is not None:
                votes[v.agent] = v
                yield v.event()
                yield _say_vote(v)
            else:
                yield {"type": "agent_error", "agent": name,
                       "message": f"{name.title()} You couldn't vote ({type(err).__name__}) — left out of the pool"}
    except asyncio.TimeoutError:
        for t in tasks:
            t.cancel()
        for a in AGENTS:
            if a not in votes:
                yield {"type": "agent_error", "agent": a, "message": f"{a.title()} You timed out — left out of the pool"}
    if not votes:
        yield {"type": "error", "message": "No agent could vote (Drex unreachable?)"}
        return

    counted = {a: v for a, v in votes.items() if not v.extra.get("abstain")}
    weights = {a: min(max(v.stake, 0.5), 5.0) for a, v in counted.items()}  # cap: one loud self can't swamp the rest
    ps = {a: v.p_regret for a, v in counted.items()}
    p = pool(ps, weights)
    condition = None
    veto_fired = False
    if "budget" in votes:
        pu = votes["budget"].extra["p_unpayable"]
        veto_fired = pu >= VETO_THRESHOLD
        rent = F.persona.rent
        yield {"type": "veto", "agent": "budget", "p": round(pu, 4), "threshold": VETO_THRESHOLD, "fired": veto_fired,
               "reason": f"{rent['payee']} ${rent['amount']:,.0f} on {rent['date']} becomes unpayable" if veto_fired else None}
        if veto_fired:
            yield _say("budget", f"Veto. Rent of ${rent['amount']:,.0f} on {rent['date'][5:].replace('-', '/')} would bounce.",
                       "veto", p=round(pu, 4))
    b = band(p)
    yield {"type": "pool", "p": round(p, 4), "band": b, "weights": {a: round(w, 2) for a, w in weights.items()}}

    final_p = p
    if veto_fired:
        pp = F.persona
        if item.price <= pp.free_cash + pp.net_pay:
            b, condition = "wait", f"Wait until payday ({pp.next_payday[5:].replace('-', '/')})"  # payday from the pay stub
        else:
            b, condition = "wait", "Not affordable this pay cycle — save up for it first"
    elif b != "buy":
        # Any split or "wait" without a veto: ask every self what would change its mind (all Drex calls).
        # Stream each self's answer as its scan lands ("say" lines), then the unchanged negotiation event.
        said: asyncio.Queue = asyncio.Queue()
        neg_task = asyncio.create_task(negotiate(item, counted, weights, say=said.put_nowait))
        while not neg_task.done():
            getter = asyncio.ensure_future(said.get())
            done, _ = await asyncio.wait({neg_task, getter}, return_when=asyncio.FIRST_COMPLETED)
            if getter in done:
                yield getter.result()
            else:
                getter.cancel()
        while not said.empty():
            yield said.get_nowait()
        neg = neg_task.result()
        yield neg
        final_p = neg["chosen"]["p_after"]
        condition = neg["chosen"]["label"]
        b = "buy_with_condition" if neg["chosen"]["resolves"] and final_p < BAND_HIGH else "wait"
        yield _say("council", f"Agreed: {condition}." if b == "buy_with_condition"
                   else "No compromise satisfies everyone — wait.", "negotiate")
        if b == "wait":
            condition = f"Best option: {condition}"
    if veto_fired:
        yield _say("council", f"Budget's veto stands. {condition}.", "verdict")
    elif b == "buy":
        yield _say("council", "No objections. Buy it.", "verdict")
    tally = {"buy": sum(v.stance == "buy" for v in votes.values()), "wait": sum(v.stance == "wait" for v in votes.values()),
             "abstain": sum(v.stance == "abstain" for v in votes.values())}
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
