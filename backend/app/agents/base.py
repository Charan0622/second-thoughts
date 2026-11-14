"""Shared agent machinery: every self asks Drex one batched call (regret, stake, decisive-fact citation, extras)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .. import drex
from ..config import TODAY
from ..facts import Fact


@dataclass
class Item:
    name: str
    category: str          # running_gear | headphones | computer | gadget | clothing | other
    price: float

    @property
    def is_gadget(self) -> bool:
        return self.category in ("headphones", "computer", "gadget")


@dataclass
class Vote:
    agent: str
    label: str
    p_regret: float
    stake: float
    headline: str
    citation: dict
    cite_p: float
    model: str
    ms: float
    extra: dict = field(default_factory=dict)
    state: str = ""

    @property
    def stance(self) -> str:
        return "buy" if self.p_regret < 0.5 else "wait"

    def event(self) -> dict:
        return {"type": "vote", "agent": self.agent, "label": self.label, "p_regret": round(self.p_regret, 4),
                "stake": round(self.stake, 2), "stance": self.stance, "headline": self.headline,
                "citation": self.citation, "cite_p": round(self.cite_p, 3), "model": self.model, "ms": round(self.ms)}


REGRET_Q = "Will Maya regret this purchase, or will it cause her a problem, within the next 30 days — judged only from your perspective?"


def build_state(role: str, mandate: str, facts: list[Fact], computed: list[str], item: Item) -> str:
    lines = [f"You are {role}, one of Maya's future selves on her spending council. Today is {TODAY}.",
             f"Your mandate: {mandate}", "", "Facts from Maya's own documents:"]
    lines += [f"[{f.id}] {f.text}" for f in facts]
    if computed:
        lines += ["", "Computed by the app (exact):"] + [f"- {c}" for c in computed]
    lines += ["", f"Proposed purchase now: {item.name} (category: {item.category.replace('_', ' ')}) for ${item.price:,.2f}."]
    return "\n".join(lines)


async def ask_council_member(*, agent: str, label: str, state: str, facts: list[Fact], regret_true: str, regret_false: str,
                             extra_q: dict[str, dict] | None = None) -> tuple[dict[str, Any], dict]:
    qs: dict[str, dict] = {
        "regret": drex.noul(REGRET_Q, regret_true, regret_false),
        "stake": drex.score("How much does this purchase matter from your perspective?", drex.STAKE_LEVELS),
    }
    if facts:
        qs["decisive_fact"] = drex.choice("Which single fact from Maya's documents most decides your answer?",
                                          {f.id: f.text for f in facts})
    qs.update(extra_q or {})
    res = await drex.ask(state, qs, note=agent)
    return res["answers"], res


def pick_citation(answers: dict, facts: list[Fact]) -> tuple[dict, float]:
    if not facts:
        return {}, 0.0
    a = answers.get("decisive_fact") or {}
    fid = a.get("choice")
    f = next((x for x in facts if x.id == fid), facts[0])
    return f.citation(), float((a.get("probabilities") or {}).get(f.id, a.get("confidence", 0)))
