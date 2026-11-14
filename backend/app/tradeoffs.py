"""Templated trade-offs in a FIXED order. Every number is computed here, never by a model."""

from __future__ import annotations

from dataclasses import dataclass

from . import facts as F
from .agents.base import Item


@dataclass
class Offer:
    id: str
    label: str
    amount: float | None
    commitment: str          # sentence appended to every agent's state when testing this offer

    def event(self) -> dict:
        return {"id": self.id, "label": self.label, "amount": self.amount}


def offers(item: Item, owns_similar: bool | None = None, dup_item: str | None = None,
           dup_price: float | None = None) -> list[Offer]:
    from .agents import goals
    p = F.persona
    n, g = p.first_name, p.goal_short
    avg = p.avg_delivery
    two, four = round(2 * avg, 2), round(4 * avg, 2)
    hours = round(item.price / p.hourly, 1) if p.hourly else 0.0  # no pay stub (mode "mine") → offer dropped below
    owned_name = (dup_item or p.owned_item or "similar item").split("(")[0].strip()
    owned_price = float(dup_price or p.owned_price or 0)
    resale = round(owned_price * 0.5)
    br = goals.broken_rule(item)
    over_rule = round(max(0.0, item.price - br["limit"]), 2) if br else 0.0
    out = [
        Offer("wait_payday", f"Wait until payday ({p.next_payday[5:].replace('-', '/')})", None,
              f"{n} commits to waiting until their payday on {p.next_payday} before buying, so rent and bills are already covered."),
        Offer("skip_takeout_2", f"Skip two takeout orders (${two:,.0f})", two,
              f"{n} commits to skipping two food-delivery orders this month, saving ${two:,.2f}."),
        Offer("skip_takeout_4", f"Skip four takeout orders (${four:,.0f})", four,
              f"{n} commits to skipping four food-delivery orders this month, saving ${four:,.2f}."),
        Offer("resell_earbuds", f"Resell the {owned_name} (≈ +${resale})", float(resale),
              f"{n} commits to reselling their ${owned_price:.0f} {owned_name} for about ${resale}, so they won't own two similar things."),
        Offer("top_up_japan", f"Top up {g} fund by ${over_rule:,.0f}", over_rule,
              f"{n} commits to adding ${over_rule:,.2f} (the amount over their own limit) to the {g} fund on payday, so the goal does not slip."),
        Offer("resell_and_topup", f"Resell the {owned_name} (≈ +${resale}) AND put ${over_rule:,.0f} into the {g} fund", over_rule + resale,
              f"{n} commits to reselling their ${owned_price:.0f} {owned_name} (about ${resale}) so they own one, AND adding ${over_rule:,.2f} "
              f"(the amount over their own limit) to the {g} fund on payday so the goal does not slip."),
        Offer("extra_hours", f"Work {hours} extra hours", round(item.price, 2),
              f"{n} commits to {hours} extra paid hours (${item.price:,.2f} at ${p.hourly:.0f}/hr) to cover this purchase."),
        Offer("return_30", "Keep the box — return within 30 days if unused", None,
              f"{n} commits to keeping the packaging and returning it within the 30-day window if they aren't using it weekly."),
        Offer("wait_24h", "Sleep on it — decide in 24 hours", None,
              f"{n} commits to waiting 24 hours and buying only if they still want it."),
    ]
    if owns_similar is None:  # no vote available (tests, bench helpers): fall back to the demo heuristic
        owns_similar = bool(p.owned_item) and item.category == "headphones"
    owns_similar = owns_similar and bool(p.owned_item)
    drop = set()
    if over_rule <= 0:
        drop |= {"top_up_japan", "resell_and_topup"}
    if not owns_similar:
        drop |= {"resell_earbuds", "resell_and_topup"}
    if not p.delivery_count:
        drop |= {"skip_takeout_2", "skip_takeout_4"}
    if not p.hourly:
        drop.add("extra_hours")
    return [o for o in out if o.id not in drop]
