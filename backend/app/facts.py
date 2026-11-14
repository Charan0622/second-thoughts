"""Fact store: NDI-extract every persona doc once, keep values + citations, cut citation crops.

Documents live in SLOTS (bank, paystub, savings, receipts, rules). The demo persona's files are in data/persona/;
a user's uploads (data/private/my_docs/<slot>/) override the demo slot by slot. If NDI can't find a field in a
user's doc, the demo value is used and the fact is flagged. Snapshot persisted in data/private/facts.sqlite.
"""

from __future__ import annotations

import asyncio
import json
import re
import sqlite3
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from PIL import Image

from . import ndi
from .config import CROPS, PERSONA, PRIVATE, TODAY

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
    goal_name: str = "Japan trip"
    owned: list[dict] = field(default_factory=list)        # [{item, price, date, return_policy, warranty}]
    today: str = TODAY
    flags: list[str] = field(default_factory=list)          # fields that fell back to demo values

    @property
    def net_hourly(self) -> float:
        """Take-home per hour (biweekly stub = 80 h)."""
        return round(self.net_pay / 80, 2) if self.net_pay else self.hourly

    @property
    def days_to_payday(self) -> int:
        from datetime import date, datetime
        try:
            today = datetime.strptime(self.today, "%A, %B %d, %Y").date()
        except ValueError:
            today = date.today()
        try:
            return max(1, (datetime.strptime(self.next_payday[:10], "%Y-%m-%d").date() - today).days)
        except ValueError:
            return 13

    @property
    def first_name(self) -> str:
        return (self.name or "You").split()[0]

    @property
    def goal_short(self) -> str:
        g = (self.goal_name or "savings goal").split("(")[0].strip()
        for suffix in (" trip", " fund", " goal"):
            if g.lower().endswith(suffix):
                g = g[: -len(suffix)]
        return g.strip() or "savings goal"

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
RECEIPT = S({"item": {"type": "string", "description": "The main item purchased"}, "price": {"type": "number"},
             "purchase_date": {"type": "string"}, "return_policy": {"type": "string"},
             "warranty": {"type": "string", "description": "Warranty length, if printed"}})
SLOT_SCHEMAS: dict[str, dict] = {
    "bank": S({
        "account_holder": {"type": "string", "description": "Name of the account holder"},
        "available_balance": {"type": "number", "description": "Available balance at the end of the statement period"},
        "account_last4": {"type": "string", "description": "Last 4 digits of the account number"},
        "scheduled_payments": {"type": "array", "description": "Upcoming scheduled payments or bills (positive amounts)", "items": S({
            "date": {"type": "string"}, "payee": {"type": "string"}, "amount": {"type": "number"}})},
        "food_delivery": {"type": "array", "description": "Every food-delivery or takeout transaction (DoorDash, UberEats, Grubhub…)", "items": S({
            "date": {"type": "string"}, "merchant": {"type": "string"}, "amount": {"type": "number"}})},
        "next_deposit_date": {"type": "string", "description": "Next expected direct deposit date, YYYY-MM-DD"}},
        req=["available_balance", "scheduled_payments"]),
    "paystub": S({
        "hourly_rate": {"type": "number"}, "pay_frequency": {"type": "string"},
        "pay_date": {"type": "string"}, "next_pay_date": {"type": "string", "description": "YYYY-MM-DD"},
        "net_pay": {"type": "number"}}),
    "savings": S({
        "goal": {"type": "string"}, "target_amount": {"type": "number"}, "target_date": {"type": "string"},
        "saved_so_far": {"type": "number"}, "monthly_contribution": {"type": "number"}}),
    "receipts": RECEIPT,
    "rules": S({"rules": {"type": "array", "items": {"type": "string"},
                          "description": "Personal spending rules the person states"}}),
}
SLOT_LABELS = {"bank": "Bank statement", "paystub": "Pay stub", "savings": "Savings tracker", "receipts": "Receipt",
               "rules": "Rules memo"}
DEMO_DOCS: dict[str, list[str]] = {"bank": ["bank_statement.pdf"], "paystub": ["pay_stub.jpg"],
                                   "savings": ["savings_tracker.xlsx"], "receipts": ["receipt_email.eml", "paper_receipt.jpg"],
                                   "rules": ["rules_memo_transcript.txt"]}
# Demo docs keep their original schemas so cached NDI results and the benchmark stay identical.
SCHEMAS: dict[str, dict] = {
    "bank_statement.pdf": S({k: v for k, v in SLOT_SCHEMAS["bank"]["properties"].items() if k != "account_holder"}),
    "pay_stub.jpg": SLOT_SCHEMAS["paystub"], "savings_tracker.xlsx": SLOT_SCHEMAS["savings"],
    "receipt_email.eml": S({
        "item": {"type": "string"}, "price": {"type": "number"}, "purchase_date": {"type": "string"},
        "return_policy": {"type": "string"}, "warranty": {"type": "string"}}),
    "paper_receipt.jpg": S({
        "item": {"type": "string"}, "price": {"type": "number"}, "date": {"type": "string"},
        "return_policy": {"type": "string"}, "warranty": {"type": "string", "description": "Warranty length, if printed"}}),
    "rules_memo_transcript.txt": S({"rules": {"type": "array", "items": {"type": "string"},
                                   "description": "Personal spending rules the speaker states"}}),
}
LABELS = {"bank_statement.pdf": "Bank statement", "pay_stub.jpg": "Pay stub (photo)", "savings_tracker.xlsx": "Savings tracker",
          "receipt_email.eml": "Receipt email", "paper_receipt.jpg": "Paper receipt (photo)", "rules_memo_transcript.txt": "Rules memo (transcript)"}
MY_DOCS = PRIVATE / "my_docs"
MY_DOCS.mkdir(exist_ok=True)
_paths: dict[str, Path] = {}          # doc key -> file path
_slot_docs: dict[str, list[str]] = {}  # slot -> active doc keys
_slot_owner: dict[str, str] = {}       # slot -> "yours" | "demo"


def active_docs() -> dict[str, list[tuple[str, Path, str]]]:
    """slot -> [(doc_key, path, owner)]: the user's files if the slot has any, else the demo files."""
    out: dict[str, list[tuple[str, Path, str]]] = {}
    for slot, demo in DEMO_DOCS.items():
        mine = sorted(p for p in (MY_DOCS / slot).glob("*") if p.is_file()) if (MY_DOCS / slot).exists() else []
        if mine:
            out[slot] = [(f"my_{slot}_{p.name}", p, "yours") for p in mine]
        else:
            out[slot] = [(d, PERSONA / d, "demo") for d in demo if (PERSONA / d).exists()]
    return out


def _schema_for(slot: str, key: str) -> dict:
    return SCHEMAS[key] if key in SCHEMAS else SLOT_SCHEMAS[slot]


def _label_for(slot: str, key: str, path: Path) -> str:
    if key in LABELS:
        return LABELS[key]
    return f"Your {SLOT_LABELS[slot].lower()} ({path.name})"


_results: dict[str, dict] = {}
_errors: dict[str, str] = {}
persona = Persona()
facts: dict[str, list[Fact]] = {"budget": [], "goals": [], "owned": [], "deal": []}
loaded = False


# ---------------------------------------------------------------- crops
_page_cache: dict[tuple[str, int], Image.Image] = {}


def _page_image(doc: str, page: int | None) -> Image.Image | None:
    p = _paths.get(doc, PERSONA / doc)
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
    """Cut a ~3:1 'snipped paper' crop around the cited region and highlight the exact line."""
    if not fact.bbox:
        return
    img = _page_image(fact.doc, fact.page)
    if img is None:
        return
    W, H = img.size
    x0, y0, x1, y1 = (fact.bbox[0] * W, fact.bbox[1] * H, fact.bbox[2] * W, fact.bbox[3] * H)
    if x1 - x0 < 8 or y1 - y0 < 4:
        return
    # horizontal: bbox + margin; vertical: grow to ~3:1 aspect around the line, so neighbours give context
    bx0, bx1 = max(0, x0 - 0.03 * W), min(W, x1 + 0.03 * W)
    if bx1 - bx0 < 0.6 * W:  # value-only box (e.g. "$2,480.00"): widen leftward to include the row label
        bx0 = max(0, bx1 - 0.6 * W) if bx1 > 0.6 * W else 0
        bx1 = max(bx1, min(W, bx0 + 0.6 * W))
    want_h = max((bx1 - bx0) / 3.0, (y1 - y0) + 0.02 * H)
    cy = (y0 + y1) / 2
    by0, by1 = max(0, cy - want_h / 2), min(H, cy + want_h / 2)
    crop = img.crop((int(bx0), int(by0), int(bx1), int(by1))).convert("RGBA")
    # highlighter over the cited line (only when the region is a line, not a whole block)
    if (y1 - y0) < 0.6 * (by1 - by0):
        overlay = Image.new("RGBA", crop.size, (0, 0, 0, 0))
        from PIL import ImageDraw
        d = ImageDraw.Draw(overlay)
        pad = max(2, int(0.004 * H))
        d.rounded_rectangle((x0 - bx0 - pad, y0 - by0 - pad, x1 - bx0 + pad, y1 - by0 + pad), radius=pad * 2,
                            fill=(255, 221, 51, 95), outline=(240, 180, 0, 220), width=max(2, pad // 2))
        crop = Image.alpha_composite(crop, overlay)
    crop = crop.convert("RGB")
    if crop.width > 900:
        crop = crop.resize((900, int(crop.height * 900 / crop.width)))
    crop.save(CROPS / f"{fact.id}.png")
    fact.crop_url = f"/files/crops/{fact.id}.png"


def _fact(fid: str, agent: str, text: str, doc: str, path: str | None) -> Fact:
    f = Fact(id=fid, agent=agent, text=text, doc=_paths[doc].name if doc in _paths else doc,
             doc_label=_doc_labels.get(doc, LABELS.get(doc, doc)))
    res = _results.get(doc)
    if res and path:
        c = ndi.citation_of(res, path)
        f.page, f.quote, f.bbox, f.status = c["page"], c["quote"], c["bbox"], c["status"] or "found"
    elif not res:
        f.status = "fallback"
    f._key = doc  # type: ignore[attr-defined]
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
_doc_labels: dict[str, str] = {}


def _first(slot: str) -> str | None:
    ks = _slot_docs.get(slot) or []
    return ks[0] if ks else None


def _build() -> None:
    p = Persona()
    flags: list[str] = []
    B, PS, ST, RM = _first("bank"), _first("paystub"), _first("savings"), _first("rules")

    def val(doc, path, default, what):
        v = _val(doc, path, None) if doc else None
        if v is None:
            if doc and _slot_owner.get(_slot_of(doc)) == "yours":
                flags.append(f"{what}: not found in your {SLOT_LABELS[_slot_of(doc)].lower()} — using demo value")
            return default
        return v

    holder = _val(B, "/account_holder", None) if B else None
    if holder and _slot_owner.get("bank") == "yours":
        p.name = str(holder).title()
    p.balance = _num(val(B, "/available_balance", p.balance, "balance"), p.balance)
    bank = (_results.get(B, {}).get("data") or {}) if B else {}
    if bank.get("scheduled_payments"):
        p.scheduled = [{"date": s.get("date"), "payee": s.get("payee"), "amount": _num(s.get("amount"), 0)}
                       for s in bank["scheduled_payments"] if _num(s.get("amount"), 0) > 0] or p.scheduled
    elif _slot_owner.get("bank") == "yours":
        flags.append("scheduled bills: none found in your bank statement — using demo bills")
    if bank.get("food_delivery"):
        p.delivery_count = len(bank["food_delivery"])
        p.delivery_total = round(sum(_num(t.get("amount"), 0) for t in bank["food_delivery"]), 2)
    p.hourly = _num(val(PS, "/hourly_rate", p.hourly, "hourly rate"), p.hourly)
    p.net_pay = _num(val(PS, "/net_pay", p.net_pay, "net pay"), p.net_pay)
    p.next_payday = str(val(PS, "/next_pay_date", p.next_payday, "next payday"))
    p.japan_target = _num(val(ST, "/target_amount", p.japan_target, "goal target"), p.japan_target)
    p.japan_saved = _num(val(ST, "/saved_so_far", p.japan_saved, "goal saved"), p.japan_saved)
    p.japan_monthly = _num(val(ST, "/monthly_contribution", p.japan_monthly, "monthly saving"), p.japan_monthly) or 1.0
    p.japan_date = str(val(ST, "/target_date", p.japan_date, "goal date"))
    p.goal_name = str(_val(ST, "/goal", p.goal_name) if ST else p.goal_name)
    if _slot_owner.get("savings") != "yours":
        p.goal_name = "Japan trip"
    # receipts → owned list
    owned = []
    for key in _slot_docs.get("receipts", []):
        d = _results.get(key, {}).get("data") or {}
        if d.get("item"):
            owned.append({"key": key, "item": str(d["item"]), "price": _num(d.get("price"), 0.0),
                          "date": str(d.get("purchase_date") or d.get("date") or ""),
                          "return_policy": str(d.get("return_policy") or ""), "warranty": str(d.get("warranty") or "")})
    if _slot_owner.get("receipts") == "yours":
        p.owned = owned
        if owned:
            o = owned[0]
            p.owned_item, p.owned_price, p.owned_date = o["item"], o["price"], o["date"]
            p.owned_return = o["return_policy"] or "return policy not stated"
        else:
            p.owned_item, flags = "", flags + ["receipts: no purchased item found in your receipts"]
    else:
        p.owned = [{"key": "receipt_email.eml", "item": p.owned_item, "price": p.owned_price, "date": p.owned_date,
                    "return_policy": p.owned_return, "warranty": "1-year limited"}]
        p.owned_price = _num(_val("receipt_email.eml", "/price", p.owned_price), p.owned_price)
    rm = ((_results.get(RM, {}).get("data") or {}).get("rules")) if RM else None
    if not rm and RM and RM in _errors and _paths.get(RM, Path("x")).suffix.lower() == ".txt":
        # NDI unavailable: read a plain-text rules file locally (labelled as such) rather than drop the user's rules
        txt = _paths[RM].read_text(errors="replace")
        rm = [x.strip(' "“”') for x in re.split(r"(?<=[.!])\s+|\n", txt) if len(x.strip(' "“”')) > 8
              and not x.lower().startswith(("alex rules", "rules memo", "voice memo"))][:6]
        if rm:
            flags.append("rules: NDI unavailable — read your text file locally")
            _doc_labels[RM] = _doc_labels.get(RM, "Rules") + " (read locally)"
    if rm:
        p.rules, p.rules_source = [str(r) for r in rm], "ndi"
    elif _slot_owner.get("rules") == "yours" and not any(f.startswith("rules:") for f in flags):
        flags.append("rules: none found in your rules document")
        p.rules = []
    if any(o == "yours" for o in _slot_owner.values()):
        from datetime import date
        p.today = date.today().strftime("%A, %B %-d, %Y")
    p.flags = flags
    use_persona(p, crops=True)
    _persist()


def _slot_of(doc: str) -> str:
    for slot, ks in _slot_docs.items():
        if doc in ks:
            return slot
    return "bank"


BASE: Persona | None = None


def use_persona(p: Persona, crops: bool = False) -> None:
    """Rebuild every self's facts from persona values (citations still point at the NDI-extracted docs)."""
    global persona, BASE
    if BASE is None or crops:
        BASE = p
    persona = p
    B, PS, ST, RM = _first("bank"), _first("paystub"), _first("savings"), _first("rules")
    B, PS, ST, RM = B or "bank_statement.pdf", PS or "pay_stub.jpg", ST or "savings_tracker.xlsx", RM or "rules_memo_transcript.txt"
    fs: dict[str, list[Fact]] = {"budget": [], "goals": [], "owned": [], "deal": []}
    fs["budget"] += [
        _fact("budget_balance", "budget", f"Checking balance today is ${p.balance:,.2f}.", B, "/available_balance"),
        *[_fact(f"budget_sched_{i}", "budget", f"Scheduled: {s['payee']} ${s['amount']:,.2f} on {s['date']}.", B,
                f"/scheduled_payments/{i}") for i, s in enumerate(p.scheduled)],
        _fact("budget_payday", "budget", f"Next payday is {p.next_payday}.", PS, "/next_pay_date"),
    ]
    if p.delivery_count:
        fs["budget"].append(_fact("budget_delivery", "budget",
                                  f"{p.delivery_count} food-delivery orders this month, about ${p.avg_delivery:.0f} each.",
                                  B, "/food_delivery/0"))
    fs["goals"] += [
        _fact("goals_target", "goals", f"{p.goal_name} goal: ${p.japan_target:,.0f} by {p.japan_date}.", ST, "/target_amount"),
        _fact("goals_saved", "goals", f"Saved so far: ${p.japan_saved:,.0f}; contributing ${p.japan_monthly:,.0f}/month.", ST, "/saved_so_far"),
        *[_fact(f"goals_rule_{i}", "goals", f"My own rule (memo): \"{r}\"", RM, f"/rules/{i}") for i, r in enumerate(p.rules)],
    ]
    if _slot_owner.get("receipts", "demo") == "demo" and p.owned_item:
        RE, PR = "receipt_email.eml", "paper_receipt.jpg"
        fs["owned"] += [
            _fact("owned_item", "owned", f"Already own: {p.owned_item}, bought {p.owned_date} for ${p.owned_price:.0f}.", RE, "/item"),
            _fact("owned_return", "owned", f"Earbuds: {p.owned_return}.", RE, "/return_policy"),
            _fact("owned_paper", "owned", f"Paper receipt confirms ${p.owned_price:.0f} earbuds purchase on 03/08/2026.", PR, "/price"),
            _fact("owned_warranty", "owned", "Paper receipt does not state a warranty length; the email says 1-year limited.", RE, "/warranty"),
        ]
    else:
        for i, o in enumerate(p.owned):
            fs["owned"].append(_fact(f"owned_{i}", "owned",
                                     f"Already own: {o['item']}" + (f", bought {o['date']}" if o['date'] else "")
                                     + (f" for ${o['price']:,.0f}" if o['price'] else "") + ".", o["key"], "/item"))
    if not fs["owned"]:
        fs["owned"] = [Fact(id="owned_none", agent="owned", text="No receipts on file for anything similar.",
                            doc="receipts", doc_label="Receipts", status="none")]
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
    """Extract every active doc (yours if uploaded, else demo) in parallel (cached by file hash), then build facts."""
    global loaded
    _results.clear(); _errors.clear(); _paths.clear(); _slot_docs.clear(); _slot_owner.clear(); _doc_labels.clear()
    _page_cache.clear()
    jobs = []
    for slot, docs in active_docs().items():
        _slot_docs[slot] = [k for k, _, _ in docs]
        _slot_owner[slot] = docs[0][2] if docs else "demo"
        for key, path, owner in docs:
            _paths[key] = path
            _doc_labels[key] = _label_for(slot, key, path)
            jobs.append((slot, key, path))

    async def one(slot: str, key: str, path: Path):
        try:
            _results[key] = await ndi.extract(path, _schema_for(slot, key), use_cache=use_cache)
        except Exception as e:  # noqa: BLE001
            _errors[key] = f"{type(e).__name__}: {str(e)[:200]}"

    await asyncio.gather(*(one(*j) for j in jobs))
    _build()
    loaded = True
    return summary()


def summary() -> dict:
    slots = {}
    for slot in DEMO_DOCS:
        ks = _slot_docs.get(slot, [])
        slots[slot] = {"label": SLOT_LABELS[slot], "owner": _slot_owner.get(slot, "demo"),
                       "files": [_paths[k].name for k in ks if k in _paths],
                       "errors": [_errors[k] for k in ks if k in _errors]}
    return {"slots": slots, "flags": persona.flags, "errors": _errors,
            "facts": {a: len(v) for a, v in facts.items()}, "free_cash": persona.free_cash, "name": persona.name}


def all_facts() -> list[Fact]:
    return [f for fl in facts.values() for f in fl]
