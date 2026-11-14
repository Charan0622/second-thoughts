from __future__ import annotations

from .. import drex, facts as F
from .base import Item, Vote, ask_council_member, build_state, pick_citation

LABEL = "Budget You"


def computed(item: Item, extra: str | None = None) -> list[str]:
    p = F.persona
    left = round(p.free_cash - item.price, 2)
    out = [f"Free cash before next payday after all scheduled bills = ${p.balance:,.2f} − "
           f"${sum(s['amount'] for s in p.scheduled):,.2f} = ${p.free_cash:,.2f}.",
           f"Next payday: {p.next_payday} (net pay about ${p.net_pay:,.0f})."]
    if left >= 0:
        out.append(f"After this purchase, ${left:,.2f} of free cash remains before payday. Every scheduled bill stays covered.")
    else:
        out.append(f"This purchase EXCEEDS free cash by ${-left:,.2f}. Paying it today leaves the "
                   f"{p.rent['payee']} payment of ${p.rent['amount']:,.2f} on {p.rent['date']} short by ${-left:,.2f}.")
    if extra:
        out.append(extra)
    return out


async def vote(item: Item, extra: str | None = None) -> Vote:
    p = F.persona
    fs = F.facts["budget"]
    state = build_state(LABEL, "protect scheduled bills and keep Maya solvent until payday. You hold a veto.",
                        fs, computed(item, extra), item)
    answers, res = await ask_council_member(
        agent="budget", label=LABEL, state=state, facts=fs,
        regret_true="The purchase leaves too little cash for scheduled bills or essentials before payday",
        regret_false="The purchase fits within free cash and every scheduled bill stays covered",
        extra_q={"bill_unpayable": drex.noul(
            "If Maya makes this purchase today, will a scheduled bill become unpayable before her next payday?",
            "The price is greater than free cash before payday, so a scheduled bill cannot be paid",
            "The price is at most the free cash before payday, so every scheduled bill can be paid")})
    cit, cp = pick_citation(answers, fs)
    left = p.free_cash - item.price
    headline = (f"Fits: ${p.free_cash:,.0f} free → ${left:,.0f} left before payday" if left >= 0
                else f"Over by ${-left:,.0f} — {p.rent['payee'].split('—')[-1].strip()} due {p.rent['date'][5:]}")
    return Vote("budget", LABEL, answers["regret"]["noul"], answers["stake"]["score"], headline, cit, cp,
                res["model"], res["ms"], extra={"p_unpayable": answers["bill_unpayable"]["noul"]}, state=state)
