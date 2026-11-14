from __future__ import annotations

from .. import drex, facts as F
from .base import Item, Vote, ask_council_member, build_state, pick_citation

LABEL = "Goals You"
RULE_LIMIT = 200.0


def slip_days(price: float) -> int:
    p = F.persona
    return round(price / max(p.japan_monthly, 1) * 30.4)


def computed(item: Item, extra: str | None = None) -> list[str]:
    p = F.persona
    remaining = p.japan_target - p.japan_saved
    out = [f"Japan fund: ${p.japan_saved:,.0f} of ${p.japan_target:,.0f}; ${remaining:,.0f} to go at ${p.japan_monthly:,.0f}/month "
           f"= {remaining / p.japan_monthly:.1f} months.",
           f"If this ${item.price:,.0f} came out of the Japan plan, the trip would slip about {slip_days(item.price)} days."]
    if not p.rules:
        out.append("Rule check: Maya has recorded no personal spending rules.")
    elif item.category == "running_gear":
        out.append("Rule check: this is running gear, which Maya's rule explicitly exempts.")
    elif item.is_gadget and item.price > RULE_LIMIT:
        out.append(f"Rule check: this is a gadget over ${RULE_LIMIT:.0f} (${item.price:,.0f}) — it BREAKS Maya's own rule.")
    elif item.is_gadget:
        out.append(f"Rule check: gadget under ${RULE_LIMIT:.0f} — allowed by the rule.")
    else:
        out.append("Rule check: no personal rule covers this category.")
    if extra:
        out.append(extra)
    return out


async def vote(item: Item, extra: str | None = None) -> Vote:
    fs = F.facts["goals"]
    state = build_state(LABEL, "protect the Japan trip and hold Maya to the rules she set for herself.", fs,
                        computed(item, extra), item)
    answers, res = await ask_council_member(
        agent="goals", label=LABEL, state=state, facts=fs,
        regret_true="The purchase breaks one of Maya's own rules or meaningfully delays her Japan goal",
        regret_false="The purchase is allowed by Maya's rules and barely affects her Japan goal",
        extra_q={"breaks_rule": drex.noul("Does this purchase break one of Maya's own spending rules?")})
    cit, cp = pick_citation(answers, fs)
    d = slip_days(item.price)
    breaks = answers["breaks_rule"]["noul"] >= 0.5
    if not F.persona.rules:
        headline = f"No rules on file · Japan slips {d} days"
    elif item.category == "running_gear":
        headline = f"Running gear is exempt · Japan +{d} days if unplanned"
    elif breaks:
        headline = f"Breaks your ${RULE_LIMIT:.0f} gadget rule · Japan slips {d} days"
    else:
        headline = f"Within your rules · Japan slips {d} days"
    return Vote("goals", LABEL, answers["regret"]["noul"], answers["stake"]["score"], headline, cit, cp,
                res["model"], res["ms"], extra={"p_breaks_rule": answers["breaks_rule"]["noul"]}, state=state)
