from __future__ import annotations

from .. import drex, facts as F
from .base import Item, Vote, ask_council_member, build_state, pick_citation

LABEL = "The Minimalist"


async def vote(item: Item, extra: str | None = None) -> Vote:
    p = F.persona
    fs = F.facts["owned"]
    if p.owned:
        computed = [f"Receipts on file: " + "; ".join(f"{o['item']} (${o['price']:,.0f}{', ' + o['date'] if o['date'] else ''})"
                                                       for o in p.owned) + "."]
        if p.owned_item:
            computed.append(f"Estimated resale value of {p.owned_item.split('(')[0].strip()} today: about ${round(p.owned_price * 0.5):.0f}.")
    else:
        computed = ["The buyer's receipts show nothing similar to the proposed purchase."]
    if extra:
        computed.append(extra)
    state = build_state(LABEL, "stop the buyer from buying something they already own or that duplicates what she has.", fs,
                        computed, item)
    answers, res = await ask_council_member(
        agent="owned", label=LABEL, state=state, facts=fs,
        regret_true="The buyer already owns something that does the same job, so this purchase is largely redundant",
        regret_false="Nothing the buyer owns does the same job, so this purchase is not redundant",
        extra_q={"duplicate": drex.noul("Does the buyer already own an item that serves the same purpose as the proposed purchase?",
                                        "An owned item serves the same main purpose",
                                        "No owned item serves the same main purpose")})
    cit, cp = pick_citation(answers, fs)
    dup = answers["duplicate"]["noul"]
    # which owned item did Drex point at? (decisive_fact → "Already own: <item>, bought …")
    fid = (answers.get("decisive_fact") or {}).get("choice")
    hit = next((o for i, o in enumerate(p.owned) if f"owned_{i}" == fid), None)
    if hit is None and fid == "owned_item" and p.owned_item:
        hit = {"item": p.owned_item, "price": p.owned_price}
    dup_item = (hit or {}).get("item") or p.owned_item
    dup_price = (hit or {}).get("price") or p.owned_price
    headline = (f"You already own: {dup_item.split('(')[0].strip()} (${dup_price:.0f})" if dup >= 0.5 and dup_item
                else "Nothing like this in your receipts")
    return Vote("owned", LABEL, answers["regret"]["noul"], answers["stake"]["score"], headline, cit, cp,
                res["model"], res["ms"], extra={"p_duplicate": dup, "dup_item": dup_item, "dup_price": dup_price}, state=state)
