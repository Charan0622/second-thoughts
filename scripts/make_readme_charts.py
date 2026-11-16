"""README charts as static SVGs (light + dark), from the benchmark and usage numbers.

Run: python3 scripts/make_readme_charts.py  → docs/media/charts/*.svg
Emphasis encoding: the Drex council is the accent, every other method is neutral context;
every bar is directly labelled, so identity never depends on colour alone.
"""

from __future__ import annotations

from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "docs" / "media" / "charts"
OUT.mkdir(parents=True, exist_ok=True)

THEMES = {
    "light": dict(surface="#fcfcfb", border="#e7e6e1", ink="#0b0b0b", ink2="#52514e", muted="#7a7974", grid="#ecebe6",
                  accent="#2a78d6", accent_soft="#d6e6f8", ctx="#8a8983", ctx_soft="#e4e3de"),
    "dark": dict(surface="#1a1a19", border="#2e2e2c", ink="#f0efec", ink2="#c3c2b7", muted="#9a998f", grid="#2a2a28",
                 accent="#3987e5", accent_soft="#1f3a5c", ctx="#6f6e69", ctx_soft="#33332f"),
}
FONT = "-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif"
MONO = "ui-monospace,SFMono-Regular,Menlo,Consolas,monospace"


def esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def frame(w: int, h: int, t: dict, title: str, subtitle: str, body: str) -> str:
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" role="img" '
            f'aria-label="{esc(title)}. {esc(subtitle)}">'
            f'<rect x="0.5" y="0.5" width="{w-1}" height="{h-1}" rx="14" fill="{t["surface"]}" stroke="{t["border"]}"/>'
            f'<text x="28" y="40" font-family="{FONT}" font-size="19" font-weight="650" fill="{t["ink"]}">{esc(title)}</text>'
            f'<text x="28" y="63" font-family="{FONT}" font-size="13.5" fill="{t["ink2"]}">{esc(subtitle)}</text>'
            f'{body}</svg>')


def bar(x: float, y: float, w: float, h: float, fill: str, r: float = 4) -> str:
    """Horizontal bar anchored at the baseline (square left), 4px rounded data-end (right)."""
    if w <= 0:
        return ""
    r = min(r, w, h / 2)
    return (f'<path d="M{x},{y} H{x+w-r} Q{x+w},{y} {x+w},{y+r} V{y+h-r} Q{x+w},{y+h} {x+w-r},{y+h} H{x} Z" '
            f'fill="{fill}"/>')


# ---------------------------------------------------------------- 1. hold-out accuracy with 95% CIs
ACC = [  # label, accuracy, lo, hi, ours
    ("Drex council (ours)", 75, 58, 92, True),
    ("Qwen3.8-Max council", 75, 54, 92, False),
    ("Single Drex call", 71, 50, 88, False),
    ("Single Qwen3.8-Max call", 67, 46, 83, False),
    ("Rules floor (3 lines of Python)", 67, 46, 83, False),
]


def accuracy(t: dict) -> str:
    W, H = 860, 392
    x0, x1, top, rowh, bh = 270, 800, 100, 46, 20
    sx = lambda v: x0 + (x1 - x0) * v / 100
    g = []
    for v in (0, 25, 50, 75, 100):
        g.append(f'<line x1="{sx(v)}" y1="{top-12}" x2="{sx(v)}" y2="{top+rowh*len(ACC)-16}" stroke="{t["grid"]}" stroke-width="1"/>')
        g.append(f'<text x="{sx(v)}" y="{top+rowh*len(ACC)+4}" text-anchor="middle" font-family="{FONT}" font-size="12" fill="{t["muted"]}">{v}%</text>')
    for i, (lab, a, lo, hi, ours) in enumerate(ACC):
        y = top + i * rowh
        col = t["accent"] if ours else t["ctx"]
        g.append(f'<text x="{x0-14}" y="{y+bh/2+5}" text-anchor="end" font-family="{FONT}" font-size="14" '
                 f'font-weight="{650 if ours else 450}" fill="{t["ink"] if ours else t["ink2"]}">{esc(lab)}</text>')
        g.append(bar(x0, y, sx(a) - x0, bh, col))
        cy = y + bh / 2   # 95% CI whisker
        g.append(f'<line x1="{sx(lo)}" y1="{cy}" x2="{sx(hi)}" y2="{cy}" stroke="{t["ink2"]}" stroke-width="2"/>')
        for v in (lo, hi):
            g.append(f'<line x1="{sx(v)}" y1="{cy-6}" x2="{sx(v)}" y2="{cy+6}" stroke="{t["ink2"]}" stroke-width="2"/>')
        g.append(f'<text x="{sx(hi)+10}" y="{cy+5}" font-family="{FONT}" font-size="14" font-weight="650" fill="{t["ink"]}">{a}%</text>')
    g.append(f'<line x1="{x0}" y1="{top-12}" x2="{x0}" y2="{top+rowh*len(ACC)-16}" stroke="{t["ink2"]}" stroke-width="1.5"/>')
    g.append(f'<text x="28" y="{H-22}" font-family="{FONT}" font-size="12" fill="{t["muted"]}">Whiskers: 95% bootstrap CI (4,000 resamples). '
             f'Labels written before reading the agent code. n = 24.</text>')
    return frame(W, H, t, "Blind hold-out accuracy", "24 unseen purchase scenarios · Buy / Buy with a condition / Wait", "".join(g))


# ---------------------------------------------------------------- 2. cost + latency (two panels, two axes)
CL = [  # label, cost $/verdict, latency s, ours
    ("Drex council (ours)", 0.00050, 0.47, True),
    ("Qwen3.8-Max council", 0.00199, 1.77, False),
    ("Single Drex call", 0.00012, 0.31, False),
    ("Single Qwen3.8-Max call", 0.00121, 1.37, False),
]


def cost_latency(t: dict) -> str:
    W, H = 860, 330
    top, rowh, bh = 112, 44, 18
    panels = [("Cost per verdict", 1, 0.0022, lambda v: f"${v:.4f}", 230, 520),
              ("Latency per verdict", 2, 2.0, lambda v: f"{v:.2f} s", 560, 820)]
    g = []
    for i, (lab, *_r, ours) in enumerate(CL):
        y = top + i * rowh
        g.append(f'<text x="214" y="{y+bh/2+5}" text-anchor="end" font-family="{FONT}" font-size="14" '
                 f'font-weight="{650 if ours else 450}" fill="{t["ink"] if ours else t["ink2"]}">{esc(lab)}</text>')
    for title, idx, vmax, fmt, x0, x1 in panels:
        sx = lambda v, x0=x0, x1=x1, vmax=vmax: x0 + (x1 - x0 - 70) * v / vmax
        g.append(f'<text x="{x0}" y="{top-20}" font-family="{FONT}" font-size="13" font-weight="600" fill="{t["ink2"]}">{title}</text>')
        g.append(f'<line x1="{x0}" y1="{top-8}" x2="{x0}" y2="{top+rowh*len(CL)-20}" stroke="{t["ink2"]}" stroke-width="1.5"/>')
        for i, row in enumerate(CL):
            v, ours = row[idx], row[3]
            y = top + i * rowh
            g.append(bar(x0, y, sx(v) - x0, bh, t["accent"] if ours else t["ctx"]))
            g.append(f'<text x="{sx(v)+8}" y="{y+bh/2+5}" font-family="{MONO}" font-size="12.5" font-weight="{700 if ours else 500}" '
                     f'fill="{t["ink"]}">{fmt(v)}</text>')
    g.append(f'<text x="28" y="{H-22}" font-family="{FONT}" font-size="12" fill="{t["muted"]}">Measured sequentially per card on the hold-out run. '
             f'Drex at $0.12 per M input tokens; Qwen at an estimated DeepInfra list price.</text>')
    return frame(W, H, t, "Same accuracy as the frontier-LLM council, ¼ the cost and ¼ the time",
                 "Median per verdict on the 24 hold-out cards", "".join(g))


# ---------------------------------------------------------------- 3. wording ablation (dumbbell)
AB = [  # label, normal, neutral, ours
    ("Drex council (ours)", 75, 71, True),
    ("Qwen3.8-Max council", 75, 58, False),
    ("Single Drex call", 71, 58, False),
    ("Single Qwen3.8-Max call", 67, 58, False),
    ("Rules floor", 67, 67, False),
]


def ablation(t: dict) -> str:
    W, H = 860, 392
    x0, x1, top, rowh = 270, 800, 116, 42
    lo_, hi_ = 50, 80
    sx = lambda v: x0 + (x1 - x0) * (v - lo_) / (hi_ - lo_)
    g = []
    # legend (two states → legend always present; shape is the secondary encoding)
    g.append(f'<circle cx="{x0+6}" cy="86" r="6" fill="none" stroke="{t["ink2"]}" stroke-width="2.5"/>'
             f'<text x="{x0+18}" y="91" font-family="{FONT}" font-size="13" fill="{t["ink2"]}">Normal facts</text>'
             f'<circle cx="{x0+136}" cy="86" r="6" fill="{t["ink2"]}"/>'
             f'<text x="{x0+148}" y="91" font-family="{FONT}" font-size="13" fill="{t["ink2"]}">Giveaway words removed ("OVER", "EXCEEDS"…)</text>')
    for v in range(50, 81, 10):
        g.append(f'<line x1="{sx(v)}" y1="{top-14}" x2="{sx(v)}" y2="{top+rowh*len(AB)-14}" stroke="{t["grid"]}"/>')
        g.append(f'<text x="{sx(v)}" y="{top+rowh*len(AB)+6}" text-anchor="middle" font-family="{FONT}" font-size="12" fill="{t["muted"]}">{v}%</text>')
    for i, (lab, a, b, ours) in enumerate(AB):
        y = top + i * rowh
        col = t["accent"] if ours else t["ctx"]
        g.append(f'<text x="{x0-14}" y="{y+5}" text-anchor="end" font-family="{FONT}" font-size="14" '
                 f'font-weight="{650 if ours else 450}" fill="{t["ink"] if ours else t["ink2"]}">{esc(lab)}</text>')
        if a != b:
            g.append(f'<line x1="{sx(b)}" y1="{y}" x2="{sx(a)}" y2="{y}" stroke="{col}" stroke-width="2.5"/>')
        g.append(f'<circle cx="{sx(a)}" cy="{y}" r="7" fill="{t["surface"]}" stroke="{col}" stroke-width="2.5"/>')
        g.append(f'<circle cx="{sx(b)}" cy="{y}" r="7" fill="{col}" stroke="{t["surface"]}" stroke-width="2"/>')
        drop = a - b
        g.append(f'<text x="{sx(a)+16}" y="{y+5}" font-family="{FONT}" font-size="13" font-weight="{650 if ours else 500}" '
                 f'fill="{t["ink"]}">{"no change" if drop == 0 else f"−{drop} pts"}</text>')
    g.append(f'<text x="28" y="{H-22}" font-family="{FONT}" font-size="12" fill="{t["muted"]}">Same 24 hold-out cards; the numbers stay, '
             f'only the words that spell out the answer are removed.</text>')
    return frame(W, H, t, "The council doesn't need the answer spelled out",
                 "Accuracy with vs without rubric-shaped wording in the facts", "".join(g))


# ---------------------------------------------------------------- 4. stat tiles
TILES = [("2,765", "Drex decisions", "99.5% success"), ("313 ms", "median Drex call", "4 selves in parallel"),
         ("0.47 s", "per verdict", "hold-out median"), ("$0.0005", "per verdict", "Drex tokens"),
         ("0", "false alarms", "on blind hold-out")]


def tiles(t: dict) -> str:
    W, H = 860, 150
    tw = (W - 56 - 4 * 12) / 5
    g = []
    for i, (big, lab, sub) in enumerate(TILES):
        x = 28 + i * (tw + 12)
        g.append(f'<rect x="{x}" y="22" width="{tw}" height="106" rx="10" fill="{t["accent_soft"] if i == 0 else t["ctx_soft"]}" '
                 f'fill-opacity="{0.55 if i == 0 else 0.45}"/>')
        g.append(f'<text x="{x+16}" y="66" font-family="{FONT}" font-size="30" font-weight="700" fill="{t["ink"]}">{esc(big)}</text>')
        g.append(f'<text x="{x+16}" y="92" font-family="{FONT}" font-size="13.5" font-weight="600" fill="{t["ink"]}">{esc(lab)}</text>')
        g.append(f'<text x="{x+16}" y="112" font-family="{FONT}" font-size="12" fill="{t["ink2"]}">{esc(sub)}</text>')
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" role="img" '
            f'aria-label="Key numbers: 2,765 Drex decisions, 313 ms median call, 0.47 s per verdict, $0.0005 per verdict, 0 false alarms">'
            f'<rect x="0.5" y="0.5" width="{W-1}" height="{H-1}" rx="14" fill="{t["surface"]}" stroke="{t["border"]}"/>{"".join(g)}</svg>')


if __name__ == "__main__":
    for mode, t in THEMES.items():
        for name, fn in (("accuracy", accuracy), ("cost-latency", cost_latency), ("ablation", ablation), ("tiles", tiles)):
            (OUT / f"{name}-{mode}.svg").write_text(fn(t))
    print("\n".join(sorted(p.name for p in OUT.iterdir())))
