"""Fact store: NDI-extract every persona doc once, keep values + citations, cut citation crops.

Values are read from NDI results; if a field is missing, the persona default is used and the citation is marked.
Snapshot persisted in data/private/facts.sqlite.
"""

from __future__ import annotations

import asyncio
import json
import sqlite3
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from PIL import Image

from . import ndi
from .config import CROPS, PERSONA, PRIVATE

DB = PRIVATE / "facts.sqlite"


@dataclass
class Fact:
    id: str
    agent: str
    text: str                       # sentence shown to Drex and in the UI
    doc: str
    doc_label: str
    page: int | None = None
    quote: str = ""
    bbox: list[float] | None = None
    crop_url: str | None = None
    status: str = "found"

    def citation(self) -> dict:
        return {"doc": self.doc, "doc_label": self.doc_label, "page": self.page, "quote": self.quote or self.text,
                "bbox": self.bbox, "crop_url": self.crop_url}


@dataclass
class Persona:
    name: str = "Maya Chen"
    balance: float = 2480.0
    scheduled: list[dict] = field(default_factory=lambda: [
        {"date": "2026-11-15", "payee": "Transfer to Savings — Japan Fund", "amount": 140.0},
        {"date": "2026-11-18", "payee": "Lumen Mobile — phone bill", "amount": 65.0},
        {"date": "2026-11-20", "payee": "Parkside Lofts — rent", "amount": 1850.0}])
    next_payday: str = "2026-11-27"
    hourly: float = 42.0
    net_pay: float = 2516.40
    japan_target: float = 4000.0
    japan_saved: float = 2600.0
    japan_monthly: float = 280.0
    japan_date: str = "April 2027"
    delivery_count: int = 9
    delivery_total: float = 245.0
    owned_item: str = "Brightline Pulse Pro wireless earbuds (noise cancelling)"
    owned_price: float = 179.0
    owned_date: str = "March 8, 2026"
    owned_return: str = "30-day return window — closed April 10, 2026"
    rules: list[str] = field(default_factory=lambda: ["No gadgets over $200 before Japan.", "Running gear is exempt."])
    rules_source: str = "transcript"

    @property
    def free_cash(self) -> float:
        return round(self.balance - sum(s["amount"] for s in self.scheduled), 2)

    @property
    def rent(self) -> dict:
        return max(self.scheduled, key=lambda s: s["amount"])

    @property
    def avg_delivery(self) -> float:
        return round(self.delivery_total / max(self.delivery_count, 1), 2)


# ---------------------------------------------------------------- NDI schemas per doc
S = lambda props, req=None: {"type": "object", "properties": props, "required": req or list(props)}  # noqa: E731
SCHEMAS: dict[str, dict] = {
    "bank_statement.pdf": S({
        "available_balance": {"type": "number", "description": "Available balance at the end of the statement period"},
        "account_last4": {"type": "string", "description": "Last 4 digits of the account number"},
        "scheduled_payments": {"type": "array", "description": "Upcoming scheduled payments (positive amounts)", "items": S({
            "date": {"type": "string"}, "payee": {"type": "string"}, "amount": {"type": "number"}})},
        "food_delivery": {"type": "array", "description": "Every DoorDash or UberEats transaction", "items": S({
            "date": {"type": "string"}, "merchant": {"type": "string"}, "amount": {"type": "number"}})},
        "next_deposit_date": {"type": "string", "description": "Next expected direct deposit date, YYYY-MM-DD"}}),
    "pay_stub.jpg": S({
        "hourly_rate": {"type": "number"}, "pay_frequency": {"type": "string"},
        "pay_date": {"type": "string"}, "next_pay_date": {"type": "string", "description": "YYYY-MM-DD"},
        "net_pay": {"type": "number"}}),
    "savings_tracker.xlsx": S({
        "goal": {"type": "string"}, "target_amount": {"type": "number"}, "target_date": {"type": "string"},
        "saved_so_far": {"type": "number"}, "monthly_contribution": {"type": "number"}}),
    "receipt_email.eml": S({
        "item": {"type": "string"}, "price": {"type": "number"}, "purchase_date": {"type": "string"},
        "return_policy": {"type": "string"}, "warranty": {"type": "string"}}),
    "paper_receipt.jpg": S({
        "item": {"type": "string"}, "price": {"type": "number"}, "date": {"type": "string"},
        "return_policy": {"type": "string"}, "warranty": {"type": "string", "description": "Warranty length, if printed"}}),
    "rules_memo.m4a": S({"rules": {"type": "array", "items": {"type": "string"},
                                   "description": "Personal spending rules the speaker states"}}),
}
LABELS = {"bank_statement.pdf": "Bank statement", "pay_stub.jpg": "Pay stub (photo)", "savings_tracker.xlsx": "Savings tracker",
          "receipt_email.eml": "Receipt email", "paper_receipt.jpg": "Paper receipt (photo)", "rules_memo.m4a": "Voice memo"}

_results: dict[str, dict] = {}
_errors: dict[str, str] = {}
persona = Persona()
facts: dict[str, list[Fact]] = {"budget": [], "goals": [], "owned": [], "deal": []}
loaded = False


# ---------------------------------------------------------------- crops
_page_cache: dict[tuple[str, int], Image.Image] = {}


def _page_image(doc: str, page: int | None) -> Image.Image | None:
    p = PERSONA / doc
    key = (doc, page or 1)
    if key in _page_cache:
        return _page_cache[key]
    img = None
    if p.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp"):
        img = Image.open(p).convert("RGB")
    elif p.suffix.lower() == ".pdf":
        import pypdfium2 as pdfium
        pdf = pdfium.PdfDocument(str(p))
        img = pdf[(page or 1) - 1].render(scale=2.5).to_pil().convert("RGB")
    if img is not None:
        _page_cache[key] = img
    return img


def make_crop(fact: Fact) -> None:
    if not fact.bbox:
        return
    img = _page_image(fact.doc, fact.page)
    if img is None:
        return
    W, H = img.size
    x0, y0, x1, y1 = fact.bbox
    # pad generously so the line has context; extend left so table rows show their label
    px, py = 0.03, 0.012
    box = (max(0, int((x0 - px) * W)), max(0, int((y0 - py) * H)), min(W, int((x1 + px) * W)), min(H, int((y1 + py) * H)))
    if box[2] - box[0] < 40 or box[3] - box[1] < 12:
        return
    crop = img.crop(box)
    if crop.width > 900:
        crop = crop.resize((900, int(crop.height * 900 / crop.width)))
    out = CROPS / f"{fact.id}.png"
    crop.save(out)
    fact.crop_url = f"/files/crops/{fact.id}.png"


def _fact(fid: str, agent: str, text: str, doc: str, path: str | None) -> Fact:
    f = Fact(id=fid, agent=agent, text=text, doc=doc, doc_label=LABELS.get(doc, doc))
    res = _results.get(doc)
    if res and path:
        c = ndi.citation_of(res, path)
        f.page, f.quote, f.bbox, f.status = c["page"], c["quote"], c["bbox"], c["status"] or "found"
    elif not res:
        f.status = "fallback"
    return f


def _val(doc: str, path: str, default: Any) -> Any:
    res = _results.get(doc)
    if not res:
        return default
    f = ndi.field(res, path)
    if not f or f.get("status") != "found" or f.get("value") in (None, ""):
        return default
    return f["value"]


def _num(x: Any, default: float) -> float:
    try:
        return abs(float(str(x).replace("$", "").replace(",", "")))
    except (TypeError, ValueError):
        return default


# ---------------------------------------------------------------- build
def _build() -> None:
    global persona
    p = Persona()
    B, PS, ST, RE, PR, RM = ("bank_statement.pdf", "pay_stub.jpg", "savings_tracker.xlsx", "receipt_email.eml",
                             "paper_receipt.jpg", "rules_memo.m4a")
    p.balance = _num(_val(B, "/available_balance", p.balance), p.balance)
    bank = _results.get(B, {}).get("data") or {}
    if bank.get("scheduled_payments"):
        p.scheduled = [{"date": s.get("date"), "payee": s.get("payee"), "amount": _num(s.get("amount"), 0)}
                       for s in bank["scheduled_payments"]]
    if bank.get("food_delivery"):
        p.delivery_count = len(bank["food_delivery"])
        p.delivery_total = round(sum(_num(t.get("amount"), 0) for t in bank["food_delivery"]), 2)
    p.hourly = _num(_val(PS, "/hourly_rate", p.hourly), p.hourly)
    p.next_payday = str(_val(PS, "/next_pay_date", p.next_payday))
    p.japan_target = _num(_val(ST, "/target_amount", p.japan_target), p.japan_target)
    p.japan_saved = _num(_val(ST, "/saved_so_far", p.japan_saved), p.japan_saved)
    p.japan_monthly = _num(_val(ST, "/monthly_contribution", p.japan_monthly), p.japan_monthly)
    p.owned_price = _num(_val(RE, "/price", p.owned_price), p.owned_price)
    rm = (_results.get(RM, {}).get("data") or {}).get("rules")
    if rm:
        p.rules, p.rules_source = [str(r) for r in rm], "ndi"
    use_persona(p, crops=True)
    _persist()


BASE: Persona | None = None


def use_persona(p: Persona, crops: bool = False) -> None:
    """Rebuild every self's facts from persona values (citations still point at the NDI-extracted docs)."""
    global persona, BASE
    if BASE is None or crops:
        BASE = p
    persona = p
    B, PS, ST, RE, PR, RM = ("bank_statement.pdf", "pay_stub.jpg", "savings_tracker.xlsx", "receipt_email.eml",
                             "paper_receipt.jpg", "rules_memo.m4a")
    rent = p.rent
    fs: dict[str, list[Fact]] = {"budget": [], "goals": [], "owned": [], "deal": []}
    fs["budget"] += [
        _fact("budget_balance", "budget", f"Checking balance today is ${p.balance:,.2f}.", B, "/available_balance"),
        *[_fact(f"budget_sched_{i}", "budget", f"Scheduled: {s['payee']} ${s['amount']:,.2f} on {s['date']}.", B,
                f"/scheduled_payments/{i}") for i, s in enumerate(p.scheduled)],
        _fact("budget_payday", "budget", f"Next payday is {p.next_payday}.", PS, "/next_pay_date"),
        _fact("budget_delivery", "budget",
              f"{p.delivery_count} food-delivery orders this month, about ${p.avg_delivery:.0f} each.", B, "/food_delivery/0"),
    ]
    fs["goals"] += [
        _fact("goals_target", "goals", f"Japan trip goal: ${p.japan_target:,.0f} by {p.japan_date}.", ST, "/target_amount"),
        _fact("goals_saved", "goals", f"Saved so far: ${p.japan_saved:,.0f}; contributing ${p.japan_monthly:,.0f}/month.", ST, "/saved_so_far"),
        *[_fact(f"goals_rule_{i}", "goals", f"My own rule (voice memo): \"{r}\"", RM, f"/rules/{i}") for i, r in enumerate(p.rules)],
    ]
    for f in fs["goals"]:
        if f.doc == RM and f.status == "fallback":
            f.doc_label = "Voice memo (transcript)"
    fs["owned"] += [
        _fact("owned_item", "owned", f"Already own: {p.owned_item}, bought {p.owned_date} for ${p.owned_price:.0f}.", RE, "/item"),
        _fact("owned_return", "owned", f"Earbuds: {p.owned_return}.", RE, "/return_policy"),
        _fact("owned_paper", "owned", f"Paper receipt confirms ${p.owned_price:.0f} earbuds purchase on 03/08/2026.", PR, "/price"),
        _fact("owned_warranty", "owned", "Paper receipt does not state a warranty length; the email says 1-year limited.", RE, "/warranty"),
    ]
    if not p.owned_item:
        fs["owned"] = [Fact(id="owned_none", agent="owned", text="No receipts on file for anything similar.",
                            doc="receipts", doc_label="Receipts")]
    for agent_facts in fs.values():
        for f in agent_facts:
            if crops:
                try:
                    make_crop(f)
                except Exception:  # noqa: BLE001
                    pass
            elif BASE is not None:
                f.crop_url = f"/files/crops/{f.id}.png" if (CROPS / f"{f.id}.png").exists() else None
    facts.clear()
    facts.update(fs)


def _persist() -> None:
    con = sqlite3.connect(DB)
    con.execute("CREATE TABLE IF NOT EXISTS facts (id TEXT PRIMARY KEY, agent TEXT, json TEXT)")
    con.execute("DELETE FROM facts")
    con.executemany("INSERT INTO facts VALUES (?,?,?)",
                    [(f.id, f.agent, json.dumps(asdict(f))) for fl in facts.values() for f in fl])
    con.execute("CREATE TABLE IF NOT EXISTS persona (k TEXT PRIMARY KEY, v TEXT)")
    con.execute("INSERT OR REPLACE INTO persona VALUES ('persona', ?)", (json.dumps(asdict(persona)),))
    con.commit()
    con.close()


async def load(use_cache: bool = True) -> dict:
    """Extract every present persona doc in parallel (cached), then build facts."""
    global loaded
    docs = [d for d in SCHEMAS if (PERSONA / d).exists()]

    async def one(doc: str):
        try:
            _results[doc] = await ndi.extract(PERSONA / doc, SCHEMAS[doc], use_cache=use_cache)
        except Exception as e:  # noqa: BLE001
            _errors[doc] = f"{type(e).__name__}: {str(e)[:200]}"

    await asyncio.gather(*(one(d) for d in docs))
    _build()
    loaded = True
    return {"extracted": sorted(_results), "errors": _errors,
            "facts": {a: len(v) for a, v in facts.items()}, "free_cash": persona.free_cash}


def all_facts() -> list[Fact]:
    return [f for fl in facts.values() for f in fl]
