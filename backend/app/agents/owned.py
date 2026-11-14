from __future__ import annotations

from .. import drex, facts as F
from .base import Item, Vote, ask_council_member, build_state, pick_citation

LABEL = "Already-Own-It You"


async def vote(item: Item, extra: str | None = None) -> Vote:
    p = F.persona
    fs = F.facts["owned"]
    computed = [f"Receipts on file: {p.owned_item} (${p.owned_price:.0f}, {p.owned_date}). The return window has closed.",
                f"Estimated resale value of those earbuds today: about ${round(p.owned_price * 0.5):.0f}."]
    if extra:
        computed.append(extra)
    state = build_state(LABEL, "stop Maya from buying something she already owns or that duplicates what she has.", fs,
                        computed, item)
    answers, res = await ask_council_member(
        agent="owned", label=LABEL, state=state, facts=fs,
        regret_true="Maya already owns something that does the same job, so this purchase is largely redundant",
        regret_false="Nothing Maya owns does the same job, so this purchase is not redundant",
        extra_q={"duplicate": drex.noul("Does Maya already own an item that serves the same purpose as the proposed purchase?",
                                        "An owned item serves the same main purpose",
                                        "No owned item serves the same main purpose")})
    cit, cp = pick_citation(answers, fs)
    dup = answers["duplicate"]["noul"]
    headline = (f"You already own ${p.owned_price:.0f} noise-cancelling earbuds" if dup >= 0.5
                else "Nothing like this in your receipts")
    return Vote("owned", LABEL, answers["regret"]["noul"], answers["stake"]["score"], headline, cit, cp,
                res["model"], res["ms"], extra={"p_duplicate": dup}, state=state)
