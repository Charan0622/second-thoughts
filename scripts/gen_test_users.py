"""Generate fictional test users for trying Second Thoughts as a NEW user (not the Maya demo persona).

Run: uv run --project backend python scripts/gen_test_users.py
Output: data/test_users/<user>/ (bank statement, pay stub, receipts, ANSWERS.md) and data/test_users/products/.
Every name, number, account and store here is invented.
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from email.utils import format_datetime
from pathlib import Path

from PIL import Image, ImageDraw
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

sys.path.insert(0, str(Path(__file__).parent))
from gen_persona import font, mono, photo_look  # noqa: E402  (shared drawing helpers)

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "test_users"

USERS = {
    "jordan": {
        "name": "Jordan Lee", "bank": "Northgate Federal", "acct": "••••3388", "employer": "Brightwell Coffee Co.",
        "role": "Shift Supervisor", "hourly": 24.50, "hours": 76, "net": 1512.80, "pay_date": "Nov 7, 2026",
        "next_pay": "2026-11-21", "balance": 1385.00,
        "scheduled": [("2026-11-15", "Transfer to Savings — Emergency Fund", 75.00), ("2026-11-17", "Verizon Wireless", 58.00),
                      ("2026-11-18", "Spotify Family", 17.99), ("2026-11-19", "Rent — Lakeview Apartments", 995.00)],
        "transactions": [("11-01", "Transfer to Savings — Emergency Fund", -75.00), ("11-02", "Kroger #318", -86.40),
                         ("11-03", "DoorDash*Chipotle", -18.75), ("11-05", "Shell Oil 5521", -42.10),
                         ("11-06", "UberEats*Panda Express", -21.30), ("11-07", "Payroll — Brightwell Coffee Co.", 1512.80),
                         ("11-08", "DoorDash*Wingstop", -27.85), ("11-09", "Target T-1182", -54.12),
                         ("11-11", "Netflix", -15.49), ("11-12", "UberEats*Sweetgreen", -19.60), ("11-13", "Kroger #318", -71.05)],
        "receipts": [
            {"kind": "eml", "file": "receipt_airpods.eml", "store": "Apple Store", "item": "AirPods (4th generation)",
             "price": 129.00, "date": datetime(2026, 4, 22, 18, 5)},
            {"kind": "jpg", "file": "receipt_switch.jpg", "store": "GAMESTOP #4410", "item": "NINTENDO SWITCH OLED",
             "price": 349.99, "date": "07/14/2026"},
            {"kind": "pdf", "file": "receipt_airfryer.pdf", "store": "Best Buy", "item": "Ninja 4-qt Air Fryer AF101",
             "price": 89.99, "date": "2026-09-03"},
        ],
        "answers": {"goal": "Emergency fund", "target": 3000, "saved": 1200, "monthly": 150, "date": "June 2027",
                    "rules": ["No gaming purchases over $60 until the emergency fund hits $3,000",
                              "Max two takeout orders a week"]},
        "story": "Tight month: about $239 free before payday. Owns AirPods and a Switch, and is building an emergency fund.",
    },
    "priya": {
        "name": "Priya Nair", "bank": "Harborline Bank", "acct": "••••7710", "employer": "Quanta Health Analytics",
        "role": "Data Analyst", "hourly": 51.00, "hours": 80, "net": 3021.60, "pay_date": "Nov 13, 2026",
        "next_pay": "2026-11-27", "balance": 4920.00,
        "scheduled": [("2026-11-15", "Transfer to Savings — Car Fund", 400.00), ("2026-11-16", "Comcast Xfinity", 79.99),
                      ("2026-11-20", "Car insurance — Geico", 132.00), ("2026-11-22", "Rent — The Meridian", 2150.00)],
        "transactions": [("10-31", "Transfer to Savings — Car Fund", -400.00), ("11-01", "Whole Foods Market", -112.48),
                         ("11-02", "Equinox Membership", -185.00), ("11-04", "Lyft", -23.40),
                         ("11-06", "DoorDash*Tartine", -34.10), ("11-09", "REI Co-op #77", -64.95),
                         ("11-11", "Trader Joe's #19", -58.30), ("11-13", "Payroll — Quanta Health Analytics", 3021.60)],
        "receipts": [
            {"kind": "eml", "file": "receipt_kindle.eml", "store": "Amazon", "item": "Kindle Paperwhite (16 GB)",
             "price": 159.99, "date": datetime(2026, 2, 10, 9, 41)},
            {"kind": "jpg", "file": "receipt_garmin.jpg", "store": "REI CO-OP #77", "item": "GARMIN FORERUNNER 265",
             "price": 349.95, "date": "08/30/2026"},
            {"kind": "txt", "file": "receipt_dyson.txt", "store": "Dyson Demo Store", "item": "Dyson V8 cordless vacuum",
             "price": 349.99, "date": "2026-05-18"},
        ],
        "answers": {"goal": "Car down payment", "target": 8000, "saved": 5200, "monthly": 400, "date": "March 2027",
                    "rules": ["No single purchase over $500 without waiting 48 hours",
                              "Fitness gear is fine"]},
        "story": "Comfortable: about $2,158 free before payday. Owns a Kindle, a Garmin watch and a Dyson, and is saving for a car.",
    },
}

PRODUCTS = [  # (file, title, price or None for a no-tag photo-style card)
    ("tag_switch2.jpg", "Nintendo Switch 2", "$449.99"),
    ("tag_kindle_scribe.jpg", "Amazon Kindle Scribe (16 GB)", "$399.99"),
    ("tag_yeti_bottle.jpg", "YETI Rambler 26 oz Bottle", "$40.00"),
    ("tag_belvita.jpg", "belVita Breakfast Biscuits 5ct", "$3.49"),
    ("tag_lululemon.jpg", "lululemon Align Leggings 25\"", "$98.00"),
    ("notag_airpods_pro.jpg", "AirPods Pro", None),
]


# ---------------------------------------------------------------- documents
def bank_statement(u: dict, out: Path) -> None:
    st = getSampleStyleSheet()
    doc = SimpleDocTemplate(str(out), pagesize=letter, title=f"{u['bank']} statement", author=f"{u['bank']} (fictional)")
    s = [Paragraph(f"<b>{u['bank']}</b>", st["Title"]),
         Paragraph(f"Checking {u['acct']} · Account holder: {u['name']}", st["Normal"]),
         Paragraph("Statement period: Nov 1, 2026 – Nov 14, 2026", st["Normal"]), Spacer(1, 10),
         Table([["Available balance (Nov 14)", f"${u['balance']:,.2f}"]], colWidths=[260, 120],
               style=TableStyle([("FONT", (0, 0), (-1, -1), "Helvetica-Bold", 11), ("ALIGN", (1, 0), (1, 0), "RIGHT")])),
         Spacer(1, 12), Paragraph("<b>Transactions</b>", st["Heading2"])]
    rows = [["Date", "Description", "Amount"]] + [[f"2026-{d}", m, f"{a:+,.2f}"] for d, m, a in u["transactions"]]
    t = Table(rows, colWidths=[70, 320, 80], repeatRows=1)
    t.setStyle(TableStyle([("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 9), ("FONT", (0, 1), (-1, -1), "Helvetica", 9),
                           ("ALIGN", (2, 0), (2, -1), "RIGHT"), ("LINEBELOW", (0, 0), (-1, 0), 0.8, colors.black),
                           ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F2F4F7")])]))
    s += [t, Spacer(1, 12), Paragraph("<b>Scheduled payments (upcoming)</b>", st["Heading2"])]
    sch = [["Date", "Payee", "Amount"]] + [[d, p, f"-{a:,.2f}"] for d, p, a in u["scheduled"]]
    t = Table(sch, colWidths=[70, 320, 80])
    t.setStyle(TableStyle([("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 9), ("FONT", (0, 1), (-1, -1), "Helvetica", 9),
                           ("ALIGN", (2, 0), (2, -1), "RIGHT"), ("LINEBELOW", (0, 0), (-1, 0), 0.8, colors.black)]))
    s += [t, Spacer(1, 8), Paragraph(f"Next direct deposit expected: {u['next_pay']}.", st["Normal"])]
    doc.build(s)


def pay_stub(u: dict, out: Path) -> None:
    W, H = 1100, 640
    img = Image.new("RGB", (W, H), (250, 249, 244))
    d = ImageDraw.Draw(img)
    gross = u["hourly"] * u["hours"]
    d.text((40, 30), u["employer"].upper(), font=font(32, True), fill="black")
    d.text((40, 72), "Earnings Statement  ·  Pay frequency: Biweekly", font=font(22), fill=(40, 40, 40))
    d.line((40, 110, W - 40, 110), fill="black", width=2)
    y = 128
    nxt = datetime.strptime(u["next_pay"], "%Y-%m-%d").strftime("%b %-d, %Y")
    for k, v in [("Employee", u["name"]), ("Position", u["role"]), ("Pay date", u["pay_date"]), ("Next pay date", nxt)]:
        d.text((40, y), k, font=font(22, True), fill="black"); d.text((300, y), v, font=font(22), fill="black"); y += 36
    y += 12
    d.line((40, y, W - 40, y), fill="black", width=1); y += 14
    d.text((40, y), "Regular", font=font(22, True), fill="black")
    d.text((300, y), f"${u['hourly']:.2f}/hr   {u['hours']:.2f}    ${gross:,.2f}", font=mono(22), fill="black"); y += 44
    for k, v, b in [("Gross pay", f"${gross:,.2f}", False), ("Taxes & deductions", f"-${gross - u['net']:,.2f}", False),
                    ("Net pay", f"${u['net']:,.2f}", True)]:
        d.text((40, y), k, font=font(22, b), fill="black"); d.text((520, y), v, font=mono(24 if b else 22), fill="black"); y += 36
    photo_look(img, angle=-1.0).save(out, quality=85)


def receipt(u: dict, r: dict, out: Path) -> None:
    if r["kind"] == "eml":
        m = EmailMessage()
        m["From"] = f"{r['store']} <orders@{r['store'].lower().replace(' ', '')}.example>"
        m["To"] = f"{u['name']} <{u['name'].split()[0].lower()}@example.com>"
        m["Subject"] = f"Your {r['store']} receipt"
        m["Date"] = format_datetime(r["date"].replace(tzinfo=timezone(timedelta(hours=-8))))
        m.set_content(f"Hi {u['name'].split()[0]},\n\nThanks for your purchase on {r['date']:%B %-d, %Y}.\n\n"
                      f"  1 × {r['item']}    ${r['price']:,.2f}\n  Total charged: ${r['price']:,.2f}\n\n"
                      "Returns accepted within 14 days of purchase.\n(This is a fictional receipt generated for testing.)\n")
        out.write_bytes(bytes(m))
    elif r["kind"] == "jpg":
        W, H = 560, 760
        img = Image.new("RGB", (W, H), (247, 245, 238))
        d = ImageDraw.Draw(img)
        y = 30
        for line, big in [(f"  {r['store']}", True), ("", False), (f"{r['date']}      15:42", False), ("-" * 28, False),
                          (r["item"][:26], False), (f"              {r['price']:.2f}", False), ("-" * 28, False),
                          (f"TOTAL         {r['price']:.2f}", True), ("", False), ("  THANK YOU!", True)]:
            d.text((24, y), line, font=mono(26 if big else 22), fill=(30, 30, 30)); y += 40
        photo_look(img, angle=3.0, bg=(70, 72, 78)).save(out, quality=82)
    elif r["kind"] == "pdf":
        st = getSampleStyleSheet()
        SimpleDocTemplate(str(out), pagesize=letter).build([
            Paragraph(f"<b>{r['store']} — Receipt</b>", st["Title"]), Paragraph(f"Customer: {u['name']} · {r['date']}", st["Normal"]),
            Spacer(1, 10), Table([["Item", "Price"], [r["item"], f"${r['price']:,.2f}"], ["Total", f"${r['price']:,.2f}"]],
                                 colWidths=[320, 100])])
    else:
        out.write_text(f"{r['store']} receipt\nDate: {r['date']}\nCustomer: {u['name']}\nItem: {r['item']}\n"
                        f"Total: ${r['price']:,.2f}\n")


def answers_md(u: dict, out: Path) -> None:
    a = u["answers"]
    free = u["balance"] - sum(x[2] for x in u["scheduled"])
    out.write_text(f"""# Test user: {u['name']} (fictional)

{u['story']}

## Upload (📄 Use my documents)
- **Bank statement:** `bank_statement.pdf`. Expect balance ${u['balance']:,.2f}, {len(u['scheduled'])} upcoming bills, free cash ≈ **${free:,.2f}**.
- **Pay stub:** `pay_stub.jpg`. Expect next payday {u['next_pay']}.
- **Receipts:** add the files in `receipts/` one at a time, and check that the owned list grows.

## Quick questions: type these
| Question | Answer |
|---|---|
| What are you saving for? | {a['goal']} |
| By when? | {a['date']} |
| Target amount ($) | {a['target']} |
| Saved so far ($) | {a['saved']} |
| Saving per month ($) | {a['monthly']} (the panel should suggest about this from the statement's savings transfer) |
| Rules | {' / '.join(a['rules'])} |

## Things to try (photos in `data/test_users/products/`)
- `tag_switch2.jpg` ($449.99)
- `tag_kindle_scribe.jpg` ($399.99)
- `tag_yeti_bottle.jpg` ($40)
- `tag_belvita.jpg` ($3.49)
- `tag_lululemon.jpg` ($98)
- `notag_airpods_pro.jpg`: no price shown, so the app should look the price up online and ask you to confirm.
""")


def product_card(title: str, price: str | None, out: Path) -> None:
    W, H = 900, 560
    img = Image.new("RGB", (W, H), (255, 255, 255))
    d = ImageDraw.Draw(img)
    if price:
        d.rectangle((0, 0, W, 64), fill=(28, 92, 160))
        d.text((30, 12), "PRICE", font=font(36, True), fill="white")
        d.text((30, 100), title, font=font(38, True), fill="black")
        d.text((30, 210), price, font=font(140, True), fill=(28, 92, 160))
        d.text((30, 450), "In stock · ships in 2 days", font=font(26), fill=(60, 60, 60))
    else:  # product box shot, no price anywhere
        d.rounded_rectangle((180, 60, 720, 500), radius=40, fill=(245, 245, 247), outline=(210, 210, 215), width=4)
        d.text((300, 200), "", font=font(80, True), fill="black")
        d.text((250, 260), title, font=font(64, True), fill="black")
        d.text((265, 350), "Active Noise Cancellation", font=font(24), fill=(90, 90, 90))
    photo_look(img, angle=-1.5, bg=(120, 120, 125)).save(out, quality=85)


if __name__ == "__main__":
    for key, u in USERS.items():
        d = OUT / key
        (d / "receipts").mkdir(parents=True, exist_ok=True)
        bank_statement(u, d / "bank_statement.pdf")
        pay_stub(u, d / "pay_stub.jpg")
        for r in u["receipts"]:
            receipt(u, r, d / "receipts" / r["file"])
        answers_md(u, d / "ANSWERS.md")
    (OUT / "products").mkdir(parents=True, exist_ok=True)
    for f, title, price in PRODUCTS:
        product_card(title, price, OUT / "products" / f)
    (OUT / "README.md").write_text(
        "# Test users (fictional)\n\nTwo invented people for trying Second Thoughts as a **new user**, not the Maya demo:\n\n"
        "- `jordan/`: Jordan Lee, a tight month (≈ $239 free before payday), building an emergency fund.\n"
        "- `priya/`: Priya Nair, comfortable (≈ $2,158 free), saving for a car.\n\n"
        "Each folder has a bank statement, a pay stub, receipts in several formats (email, photo, PDF, text) and "
        "`ANSWERS.md` with what to type in the quick questions. `products/` has photos to check, including one with no "
        "price tag. Regenerate with `uv run --project backend python scripts/gen_test_users.py`. All data is invented.\n")
    for p in sorted(OUT.rglob("*")):
        if p.is_file():
            print(f"{p.relative_to(ROOT)}  {p.stat().st_size // 1024} KB")
