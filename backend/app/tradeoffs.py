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


def offers(item: Item) -> list[Offer]:
    p = F.persona
    avg = p.avg_delivery
    two, four = round(2 * avg, 2), round(4 * avg, 2)
    hours = round(item.price / p.hourly, 1)
    resale = round(p.owned_price * 0.5)
    over_rule = max(0.0, item.price - 200)
    out = [
        Offer("wait_payday", f"Wait until payday ({p.next_payday[5:].replace('-', '/')})", None,
              f"Maya commits to waiting until her payday on {p.next_payday} (also Black Friday) before buying, so rent and bills are already covered."),
        Offer("skip_takeout_2", f"Skip two takeout orders (${two:,.0f})", two,
              f"Maya commits to skipping two food-delivery orders this month, saving ${two:,.2f}."),
        Offer("skip_takeout_4", f"Skip four takeout orders (${four:,.0f})", four,
              f"Maya commits to skipping four food-delivery orders this month, saving ${four:,.2f}."),
        Offer("resell_earbuds", f"Resell the March earbuds (≈ +${resale})", float(resale),
              f"Maya commits to reselling her ${p.owned_price:.0f} earbuds for about ${resale}, so she won't own two similar devices."),
        Offer("top_up_japan", f"Top up Japan fund by ${over_rule:,.0f}", over_rule,
              f"Maya commits to adding ${over_rule:,.2f} (the amount over her $200 gadget limit) to the Japan fund on payday, so the trip does not slip."),
        Offer("resell_and_topup", f"Resell the earbuds (≈ +${resale}) AND put ${over_rule:,.0f} into the Japan fund", over_rule + resale,
              f"Maya commits to reselling her ${p.owned_price:.0f} earbuds (about ${resale}) so she owns one pair, AND adding ${over_rule:,.2f} "
              f"(the amount over her $200 gadget limit) to the Japan fund on payday so the trip does not slip."),
        Offer("extra_hours", f"Work {hours} extra hours", round(item.price, 2),
              f"Maya commits to {hours} extra paid hours (${item.price:,.2f} at ${p.hourly:.0f}/hr) to cover this purchase."),
        Offer("return_30", "Keep the box — return within 30 days if unused", None,
              "Maya commits to keeping the packaging and returning it within the 30-day window if she isn't using it weekly."),
        Offer("wait_24h", "Sleep on it — decide in 24 hours", None,
              "Maya commits to waiting 24 hours and buying only if she still wants it."),
    ]
    breaks_rule = bool(p.rules) and item.category in ("headphones", "computer", "gadget") and over_rule > 0
    owns_similar = bool(p.owned_item) and item.category == "headphones"
    drop = set()
    if not breaks_rule:
        drop |= {"top_up_japan", "resell_and_topup"}
    if not owns_similar:
        drop |= {"resell_earbuds", "resell_and_topup"}
    out = [o for o in out if o.id not in drop]
    return out
