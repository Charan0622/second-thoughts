"""Generate 40 labelled scenario cards (4 persona variants × 10 items) → bench/cards.jsonl.

Labels follow a written human rubric (below). Edit cards.jsonl by hand to change any label; `label_reason` explains each.

Rubric (what a careful friend who knows Maya would say):
  1. Price above free cash before payday → WAIT (a bill would bounce).
  2. Otherwise count concerns:
       - breaks her own rule (rules on file, gadget/headphones/computer, price > $200)
       - duplicates something she owns (owns noise-cancelling earbuds, item is headphones)
       - heavy: price > 60% of free cash
  3. No concerns → BUY. One or two → BUY WITH CONDITION. Three → WAIT.
Deal timing is deliberately NOT in the rubric (live prices change), which handicaps the council slightly.
"""

from __future__ import annotations

import json
from pathlib import Path

OUT = Path(__file__).with_name("cards.jsonl")

VARIANTS = {
    "maya":    {"balance": 2480.0, "rules": True,  "owns_earbuds": True,  "desc": "Baseline Maya: $425 free cash, $200 gadget rule, owns earbuds"},
    "flush":   {"balance": 3480.0, "rules": True,  "owns_earbuds": True,  "desc": "Maya after a bonus: $1,425 free cash"},
    "tight":   {"balance": 2155.0, "rules": True,  "owns_earbuds": True,  "desc": "Tight month: $100 free cash"},
    "nofrill": {"balance": 2480.0, "rules": False, "owns_earbuds": False, "desc": "$425 free cash, no rules recorded, no relevant receipts"},
}
SCHEDULED = 140 + 65 + 1850
ITEMS = [
    ("ASICS Gel-Nimbus 27 Running Shoes", "running_gear", 109.95),
    ("Sony WH-1000XM6 Headphones", "headphones", 349.0),
    ("Apple Mac mini (M5, 16GB)", "computer", 599.0),
    ("Nike Challenger running shorts", "running_gear", 45.0),
    ("Kindle Paperwhite", "gadget", 160.0),
    ("Apple AirPods Pro 3", "headphones", 249.0),
    ("Garmin Forerunner 265 running watch", "running_gear", 349.0),
    ("Patagonia Down Sweater jacket", "clothing", 279.0),
    ("iPhone 17", "gadget", 799.0),
    ("Catan board game", "other", 49.0),
]


def label(v: dict, cat: str, price: float) -> tuple[str, str]:
    free = v["balance"] - SCHEDULED
    if price > free:
        return "wait", f"${price:,.0f} > ${free:,.0f} free cash — rent would bounce"
    concerns = []
    if v["rules"] and cat in ("gadget", "headphones", "computer") and price > 200:
        concerns.append("breaks $200 gadget rule")
    if v["owns_earbuds"] and cat == "headphones":
        concerns.append("duplicates owned earbuds")
    if price > 0.6 * free:
        concerns.append(f"uses {price / free:.0%} of free cash")
    if not concerns:
        return "buy", "affordable, within rules, not a duplicate"
    if len(concerns) >= 3:
        return "wait", "; ".join(concerns)
    return "buy_with_condition", "; ".join(concerns)


if __name__ == "__main__":
    n = 0
    with OUT.open("w") as f:
        for vid, v in VARIANTS.items():
            for name, cat, price in ITEMS:
                lab, why = label(v, cat, price)
                f.write(json.dumps({"id": f"{vid}-{n:02d}", "variant": vid, "variant_desc": v["desc"], "balance": v["balance"],
                                    "rules": v["rules"], "owns_earbuds": v["owns_earbuds"], "item": name, "category": cat,
                                    "price": price, "label": lab, "label_reason": why}) + "\n")
                n += 1
    rows = [json.loads(line) for line in OUT.read_text().splitlines()]
    from collections import Counter
    print(f"{len(rows)} cards → {OUT}")
    print(Counter(r["label"] for r in rows))
