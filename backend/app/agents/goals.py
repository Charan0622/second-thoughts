from __future__ import annotations

import re

from .. import drex, facts as F
from .base import Item, Vote, ask_council_member, build_state, pick_citation

LABEL = "The Planner"
RULE_LIMIT = 200.0  # demo default; real limits are parsed from the rule text
GADGET_WORDS = ("gadget", "electronic", "tech", "device")
SCOPES = {"gadget": ("headphones", "computer", "gadget"), "clothing": ("clothing",), "running": ("running_gear",)}


def parse_rules(rules: list[str]) -> list[dict]:
    """Pull simple structure out of free-text rules: a $ limit, what it covers, and exemptions. Drex still judges."""
    out = []
    for r in rules:
        low = r.lower()
        m = re.search(r"\$\s?(\d[\d,]*(?:\.\d+)?)", r)
        scope = None
        if any(w in low for w in GADGET_WORDS):
            scope = "gadget"
        elif any(w in low for w in ("cloth", "apparel", "fashion")):
            scope = "clothing"
        exempt = None
        if "exempt" in low or "except" in low:
            if "running" in low:
                exempt = "running"
            elif any(w in low for w in GADGET_WORDS):
                exempt = "gadget"
        out.append({"text": r, "limit": float(m.group(1).replace(",", "")) if m else None, "scope": scope, "exempt": exempt})
    return out


def slip_days(price: float) -> int:
    p = F.persona
    if not p.has_goal:
        return 0
    return round(price / max(p.japan_monthly, 1) * 30.4)


def rule_lines(item: Item) -> list[str]:
    p = F.persona
    if not p.rules:
        return ["Rule check: the buyer has recorded no personal spending rules."]
    parsed = parse_rules(p.rules)
    out = []
    exempt = any((r["exempt"] == "running" and item.category == "running_gear") or
                 (r["exempt"] == "gadget" and item.is_gadget) for r in parsed)
    for r in parsed:
        applies = (r["scope"] is None) or (item.category in SCOPES.get(r["scope"], ()))
        if r["limit"] is not None and applies and not exempt:
            rel = "OVER" if item.price > r["limit"] else "within"
            out.append(f"Rule check: \"{r['text']}\" sets a ${r['limit']:,.0f} limit; this item costs ${item.price:,.2f} — {rel} the limit.")
        elif r["exempt"] and exempt:
            out.append(f"Rule check: \"{r['text']}\" — this item falls under that exemption.")
    if not out:
        out.append("Rule check: judge whether the purchase breaks any of the buyer's own rules listed above.")
    return out


def broken_rule(item: Item) -> dict | None:
    for r in parse_rules(F.persona.rules):
        applies = (r["scope"] is None) or (item.category in SCOPES.get(r["scope"], ()))
        if r["limit"] is not None and applies and item.price > r["limit"]:
            return r
    return None


def computed(item: Item, extra: str | None = None) -> list[str]:
    p = F.persona
    remaining = p.japan_target - p.japan_saved
    g = p.goal_short
    if not p.has_goal:
        return ["The buyer has no savings goal on file, so no goal can slip."] + rule_lines(item) + ([extra] if extra else [])
    out = [f"{p.goal_name}: ${p.japan_saved:,.0f} of ${p.japan_target:,.0f}; ${remaining:,.0f} to go at ${p.japan_monthly:,.0f}/month "
           f"= {remaining / p.japan_monthly:.1f} months.",
           f"If this ${item.price:,.0f} came out of the {g} savings plan, the goal would slip about {slip_days(item.price)} days."]
    out += rule_lines(item)
    if extra:
        out.append(extra)
    return out


async def vote(item: Item, extra: str | None = None) -> Vote:
    fs = F.facts["goals"]
    state = build_state(LABEL, f"protect the {F.persona.goal_name} and hold the buyer to the rules they set for themselves.", fs,
                        computed(item, extra), item)
    answers, res = await ask_council_member(
        agent="goals", label=LABEL, state=state, facts=fs,
        regret_true="The purchase breaks one of the buyer's own rules or meaningfully delays their savings goal",
        regret_false="The purchase is allowed by the buyer's rules and barely affects their savings goal",
        extra_q={"breaks_rule": drex.noul("Does this purchase break one of the buyer's own spending rules?")})
    cit, cp = pick_citation(answers, fs)
    fits = item.price <= F.persona.free_cash
    d = slip_days(item.price - max(F.persona.free_cash, 0)) if not fits else 0
    tail = f" · {F.persona.goal_short} slips {d} days" if d else ""
    breaks = answers["breaks_rule"]["noul"] >= 0.5
    g = F.persona.goal_short
    parsed = parse_rules(F.persona.rules)
    br = broken_rule(item)
    if not F.persona.rules:
        headline = f"No rules on file{tail or f' · {g} on track'}"
    elif any(r["exempt"] == "running" for r in parsed) and item.category == "running_gear":
        headline = f"Running gear is exempt{tail}"
    elif breaks and br and br["scope"] == "gadget":
        headline = f"Breaks your ${br['limit']:,.0f} gadget rule{tail}"
    elif breaks:
        rule = (br or {"text": F.persona.rules[0]})["text"]
        headline = f"Breaks your rule “{rule[:40]}{'…' if len(rule) > 40 else ''}”{tail}"
    else:
        headline = f"Within your rules{tail or f' · {g} on track'}"
    return Vote("goals", LABEL, answers["regret"]["noul"], answers["stake"]["score"], headline, cit, cp,
                res["model"], res["ms"], extra={"p_breaks_rule": answers["breaks_rule"]["noul"]}, state=state)
