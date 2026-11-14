"""Generate Maya's fictional demo documents into data/persona/.

Run: uv run --project backend python scripts/gen_persona.py
Every name, number and account in these files is invented.
"""

from __future__ import annotations

import random
from datetime import date
from email.message import EmailMessage
from email.utils import format_datetime
from datetime import datetime, timezone, timedelta
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill
from PIL import Image, ImageDraw, ImageFilter, ImageFont
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "persona"
FRAMES = ROOT / "data" / "demo_frames"
random.seed(4417)

# ---- Persona facts (single source of truth; mirrored in AGENTS.md) ----
NAME = "Maya Chen"
ACCT = "••••4417"
BALANCE = 2480.00
SCHEDULED = [("2026-11-15", "Transfer to Savings — Japan Fund", 140.00),
             ("2026-11-18", "Lumen Mobile — phone bill", 65.00),
             ("2026-11-20", "Parkside Lofts — rent", 1850.00)]
FREE_CASH = BALANCE - sum(a for _, _, a in SCHEDULED)  # 425.00
assert abs(FREE_CASH - 425.0) < 0.01
HOURLY, HOURS = 42.00, 80
GROSS = HOURLY * HOURS  # 3360
NET = 2516.40


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    for p in (["/System/Library/Fonts/Supplemental/Arial Bold.ttf"] if bold else []) + [
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
        "/Library/Fonts/Arial.ttf",
    ]:
        if Path(p).exists():
            return ImageFont.truetype(p, size)
    return ImageFont.load_default(size=size)


def mono(size: int) -> ImageFont.FreeTypeFont:
    for p in ("/System/Library/Fonts/Menlo.ttc", "/System/Library/Fonts/Supplemental/Courier New.ttf"):
        if Path(p).exists():
            return ImageFont.truetype(p, size)
    return font(size)


def photo_look(img: Image.Image, angle: float, bg=(92, 84, 76)) -> Image.Image:
    """Make a flat render look like a phone photo of paper on a table."""
    img = img.rotate(angle, expand=True, fillcolor=bg, resample=Image.BICUBIC)
    pad = Image.new("RGB", (img.width + 120, img.height + 120), bg)
    pad.paste(img, (60, 60))
    # uneven lighting
    shade = Image.linear_gradient("L").resize(pad.size).rotate(30)
    pad = Image.composite(pad, Image.new("RGB", pad.size, (40, 36, 32)), shade.point(lambda v: 200 + v // 5))
    noise = Image.effect_noise(pad.size, 12).convert("RGB")
    pad = Image.blend(pad, noise, 0.06).filter(ImageFilter.GaussianBlur(0.6))
    if pad.width > 1280:
        pad = pad.resize((1280, int(pad.height * 1280 / pad.width)))
    return pad


# ---------------------------------------------------------------- bank statement
def bank_statement() -> None:
    styles = getSampleStyleSheet()
    doc = SimpleDocTemplate(str(OUT / "bank_statement.pdf"), pagesize=letter,
                            title="Harbor Federal Credit Union — Statement", author="Harbor Federal (fictional)")
    s = []
    s.append(Paragraph("<b>Harbor Federal Credit Union</b>", styles["Title"]))
    s.append(Paragraph(f"Everyday Checking {ACCT} &nbsp;·&nbsp; {NAME} &nbsp;·&nbsp; 418 Alder St Apt 3, San Francisco, CA 94110", styles["Normal"]))
    s.append(Paragraph("Statement period: Oct 15, 2026 – Nov 14, 2026", styles["Normal"]))
    s.append(Spacer(1, 10))

    summary = [["Opening balance (Oct 15)", "$1,912.37"], ["Total deposits", "$5,032.80"],
               ["Total withdrawals", "$4,465.17"], ["Available balance (Nov 14)", f"${BALANCE:,.2f}"]]
    t = Table(summary, colWidths=[260, 120])
    t.setStyle(TableStyle([("FONT", (0, 0), (-1, -1), "Helvetica", 10), ("FONT", (0, 3), (-1, 3), "Helvetica-Bold", 11),
                           ("ALIGN", (1, 0), (1, -1), "RIGHT"), ("LINEABOVE", (0, 3), (-1, 3), 1, colors.black)]))
    s += [t, Spacer(1, 14), Paragraph("<b>Transactions</b>", styles["Heading2"])]

    delivery = [("10-17", "DoorDash*Thai Basil", 26.84), ("10-21", "UberEats*Poke Bar", 27.90),
                ("10-24", "DoorDash*Burma Love", 28.15), ("10-28", "UberEats*Souvla", 26.40),
                ("10-31", "DoorDash*Pizzeria Delfina", 27.65), ("11-03", "UberEats*Sweetgreen", 25.95),
                ("11-06", "DoorDash*Thai Basil", 27.10), ("11-09", "UberEats*Nopalito", 28.30),
                ("11-12", "DoorDash*Burma Love", 26.71)]
    rows = [("10-15", "Transfer to Savings — Japan Fund", -140.00), ("10-16", "Paycheck — Fernway Studio (direct dep)", NET),
            ("10-18", "Lumen Mobile — phone bill", -65.00), ("10-19", "Safeway #2231", -84.12),
            ("10-20", "Parkside Lofts — rent", -1850.00), ("10-22", "Clipper Card reload", -40.00),
            ("10-25", "Rainbow Grocery", -62.48), ("10-29", "PG&E — utilities", -71.33),
            ("10-30", "Spotify", -11.99), ("11-01", "Transfer to Savings — Japan Fund", -140.00),
            ("11-02", "Trader Joe's #236", -58.21), ("11-05", "Blue Bottle Coffee", -7.50),
            ("11-07", "Muni / Clipper", -40.00), ("11-08", "Walgreens #4410", -23.17),
            ("11-10", "Trader Joe's #236", -66.04), ("11-13", "Paycheck — Fernway Studio (direct dep)", NET)]
    rows += [(d, m, -a) for d, m, a in delivery]
    rows.sort(key=lambda r: r[0])
    table = [["Date", "Description", "Amount"]] + [[f"2026-{d}", m, f"{a:+,.2f}"] for d, m, a in rows]
    half = 15
    for i, chunk in enumerate([table[: half + 1], [table[0]] + table[half + 1:]]):
        t = Table(chunk, colWidths=[70, 320, 80], repeatRows=1)
        t.setStyle(TableStyle([("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 9), ("FONT", (0, 1), (-1, -1), "Helvetica", 9),
                               ("ALIGN", (2, 0), (2, -1), "RIGHT"), ("LINEBELOW", (0, 0), (-1, 0), 0.8, colors.black),
                               ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F2F4F7")])]))
        s.append(t)
        if i == 0:
            s += [PageBreak(), Paragraph(f"<b>Everyday Checking {ACCT} — page 2</b>", styles["Heading3"])]

    s += [Spacer(1, 14), Paragraph("<b>Scheduled payments (upcoming)</b>", styles["Heading2"])]
    sched = [["Date", "Payee", "Amount"]] + [[d, p, f"-{a:,.2f}"] for d, p, a in SCHEDULED]
    t = Table(sched, colWidths=[70, 320, 80])
    t.setStyle(TableStyle([("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 9), ("FONT", (0, 1), (-1, -1), "Helvetica", 9),
                           ("ALIGN", (2, 0), (2, -1), "RIGHT"), ("LINEBELOW", (0, 0), (-1, 0), 0.8, colors.black)]))
    s += [t, Spacer(1, 8), Paragraph("Next direct deposit expected: 2026-11-27.", styles["Normal"])]
    doc.build(s)


# ---------------------------------------------------------------- pay stub photo
def pay_stub() -> None:
    W, H = 1100, 760
    img = Image.new("RGB", (W, H), (250, 249, 244))
    d = ImageDraw.Draw(img)
    d.text((40, 30), "FERNWAY STUDIO LLC", font=font(34, True), fill="black")
    d.text((40, 75), "Earnings Statement  ·  Pay frequency: Biweekly", font=font(22), fill=(40, 40, 40))
    d.line((40, 115, W - 40, 115), fill="black", width=2)
    lines = [("Employee", NAME), ("Position", "Product Designer"), ("Pay period", "Oct 31, 2026 – Nov 13, 2026"),
             ("Pay date", "Nov 13, 2026"), ("Next pay date", "Nov 27, 2026")]
    y = 135
    for k, v in lines:
        d.text((40, y), k, font=font(22, True), fill="black"); d.text((300, y), v, font=font(22), fill="black"); y += 36
    y += 14
    d.line((40, y, W - 40, y), fill="black", width=1); y += 12
    for k, v in [("Description", "Rate      Hours        Amount"), ("Regular", f"${HOURLY:.2f}/hr   {HOURS:.2f}    ${GROSS:,.2f}")]:
        d.text((40, y), k, font=font(22, True), fill="black"); d.text((300, y), v, font=mono(22), fill="black"); y += 36
    y += 8
    for k, v in [("Gross pay", f"${GROSS:,.2f}"), ("Federal tax", "-$412.60"), ("CA state tax", "-$174.05"),
                 ("Social Security / Medicare", "-$257.04"), ("Net pay", f"${NET:,.2f}")]:
        bold = k == "Net pay"
        d.text((40, y), k, font=font(22, bold), fill="black"); d.text((520, y), v, font=mono(24 if bold else 22), fill="black"); y += 34
    photo_look(img, angle=-1.3).save(OUT / "pay_stub.jpg", quality=85)


# ---------------------------------------------------------------- savings tracker
def savings_tracker() -> None:
    wb = Workbook()
    ws = wb.active
    ws.title = "Japan Fund"
    ws["A1"] = "Japan trip — savings tracker"; ws["A1"].font = Font(bold=True, size=14)
    for r, (k, v) in enumerate([("Goal", "Japan trip (Tokyo + Kyoto, 12 days)"), ("Target amount", 4000),
                                ("Target date", "April 2027"), ("Saved so far", 2600), ("Monthly contribution", 280),
                                ("Remaining", "=B4-B5"), ("Months to goal at current rate", "=B7/B6")], start=3):
        ws.cell(r, 1, k).font = Font(bold=True); ws.cell(r, 2, v)
    for c in ("B4", "B6", "B7", "B8"):
        ws[c].number_format = '"$"#,##0'
    ws["B5"] = 2600; ws["B5"].number_format = '"$"#,##0'
    ws["B9"].number_format = "0.0"
    ws["A11"] = "Month"; ws["B11"] = "Deposit"; ws["C11"] = "Running total"
    for c in ("A11", "B11", "C11"):
        ws[c].font = Font(bold=True); ws[c].fill = PatternFill("solid", fgColor="DDE7F0")
    months = ["Jan 2026", "Feb 2026", "Mar 2026", "Apr 2026", "May 2026", "Jun 2026", "Jul 2026", "Aug 2026", "Sep 2026",
              "Oct 2026", "Nov 2026 (1st)"]
    deposits = [200, 200, 200, 240, 240, 240, 280, 280, 280, 280, 160]  # = 2600
    assert sum(deposits) == 2600
    total = 0
    for i, (m, dep) in enumerate(zip(months, deposits), start=12):
        total += dep
        ws.cell(i, 1, m); ws.cell(i, 2, dep).number_format = '"$"#,##0'; ws.cell(i, 3, total).number_format = '"$"#,##0'
    ws.column_dimensions["A"].width = 32; ws.column_dimensions["B"].width = 36; ws.column_dimensions["C"].width = 16
    wb.save(OUT / "savings_tracker.xlsx")


# ---------------------------------------------------------------- receipts
def receipt_email() -> None:
    m = EmailMessage()
    m["From"] = "Brightline Audio <orders@brightline-audio.example>"
    m["To"] = f"{NAME} <maya.chen@example.com>"
    m["Subject"] = "Your Brightline order #BA-208114 is confirmed"
    m["Date"] = format_datetime(datetime(2026, 3, 8, 14, 22, tzinfo=timezone(timedelta(hours=-8))))
    m.set_content(f"""Hi Maya,

Thanks for your order! Here's your receipt.

Order #BA-208114 — placed March 8, 2026

  1 × Brightline Pulse Pro wireless earbuds (Graphite)   $179.00
      Active noise cancelling · Bluetooth 5.4 · 32h with case
  Shipping                                                $0.00
  Tax                                                    included
  -------------------------------------------------------------
  Total charged to Visa ending 4417                     $179.00

Returns: You can return unused items within 30 days of delivery for a full refund.
Delivered: March 11, 2026 (return window closed April 10, 2026).

Warranty: 1-year limited manufacturer warranty.

— The Brightline Audio team
(This is a fictional receipt generated for a demo.)
""")
    (OUT / "receipt_email.eml").write_bytes(bytes(m))


def paper_receipt() -> None:
    W, H = 560, 980
    img = Image.new("RGB", (W, H), (247, 245, 238))
    d = ImageDraw.Draw(img)
    f, fb = mono(22), mono(26)
    y = 30
    for line, ff in [("   BRIGHTLINE AUDIO", fb), ("   Union Square Store", f), ("  233 Geary St, SF CA", f), ("", f),
                     ("03/08/2026      14:22", f), ("Store 014   Reg 2   #5531", f), ("-" * 28, f),
                     ("PULSE PRO EARBUDS", f), ("  GRAPHITE  SKU 77120", f), ("              179.00", f), ("-" * 28, f),
                     ("SUBTOTAL      179.00", f), ("TAX (incl)      0.00", f), ("TOTAL         179.00", fb), ("", f),
                     ("VISA ****4417", f), ("AUTH 08812C", f), ("-" * 28, f),
                     ("RETURNS ACCEPTED WITHIN", f), ("30 DAYS WITH RECEIPT", f), ("", f), ("  THANK YOU!", fb)]:
        d.text((24, y), line, font=ff, fill=(30, 30, 30)); y += 38
    # deliberately no warranty line
    photo_look(img, angle=4.5, bg=(70, 72, 78)).save(OUT / "paper_receipt.jpg", quality=82)


# ---------------------------------------------------------------- price tags (spike 4 / demo fallback)
def price_tag(name: str, title: str, price: str) -> None:
    W, H = 900, 520
    img = Image.new("RGB", (W, H), (255, 255, 255))
    d = ImageDraw.Draw(img)
    d.rectangle((0, 0, W, 70), fill=(200, 16, 46))
    d.text((30, 14), "SALE", font=font(40, True), fill="white")
    d.text((30, 110), title, font=font(40, True), fill="black")
    d.text((30, 220), price, font=font(150, True), fill=(200, 16, 46))
    d.text((30, 430), "Price valid through 11/22/2026", font=font(26), fill=(60, 60, 60))
    photo_look(img, angle=-2.0, bg=(120, 120, 125)).save(FRAMES / f"price_tag_{name}.jpg", quality=85)


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    FRAMES.mkdir(parents=True, exist_ok=True)
    bank_statement(); pay_stub(); savings_tracker(); receipt_email(); paper_receipt()
    price_tag("shoes", "ASICS Gel-Nimbus 27 Running Shoes", "$109.95")
    price_tag("headphones", "Sony WH-1000XM6 Headphones", "$349.00")
    price_tag("macmini", "Apple Mac mini (M5, 16GB)", "$599.00")
    print(f"free cash before payday = ${FREE_CASH:.2f}")
    for p in sorted(list(OUT.iterdir()) + list(FRAMES.iterdir())):
        print(f"{p.relative_to(ROOT)}  {p.stat().st_size // 1024} KB")
