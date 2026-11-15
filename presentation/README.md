# Second Thoughts: the four-slide keynote

A standalone HTML deck (fixed 1920×1080 stage, scaled to any screen). It uses no build step and needs no network: fonts and images are in `assets/`.

## Present

```bash
open presentation/index.html          # from the repo root; or double-click the file
```

Press **F** for fullscreen. **Esc** leaves fullscreen.

| Key | Action |
|---|---|
| → · Space · PageDown | Next (slide 4 has two steps: the picture, then the closing line) |
| ← · PageUp | Back |
| 1–4 · Home · End | Jump to a slide |
| F | Fullscreen on and off |
| D | Open the live app in a new tab |

The URL hash keeps your place (`#3`, `#4.2`). Switch tabs to the demo and back, and the deck is where you left it. The controls in the bottom bar fade after 2.5 s without the mouse.

## Live demo (slide 3)

1. Start the app (see the repo README): the backend on `:8000`, the frontend on `:5173`.
2. On slide 3 the status line says **App running at localhost:5173**, or **App not reachable** when it isn't. It rechecks every 5 s.
3. Click **OPEN LIVE DEMO** or press **D**. In the app, press **2** for the headphones.
4. Come back to the deck tab and press → for slide 4.

To use a different app address, open `index.html?demo=http://host:port/`.

**If the app is down**, present from the slide itself: the screenshot and every number on slide 3 come from a real run (see below). As a last resort, the frontend's `?mock=1` mode replays a recorded event stream with no backend. Say it's a replay if you use it.

## What's real on each slide

- **Slide 1:** the tag shows the real demo item, Sony WH-1000XM6 at $349. The photo (`assets/photos/hackathon-room.webp`) is the Drexathon room with purchase-dilemma thought bubbles added.
- **The four selves** use the app's names (`frontend/src/Council.tsx`): The Accountant, The Planner, The Minimalist and The Bargain Hunter.
- **Slide 2:** the pipeline matches the code. NDI extracts facts with page and line. Each self makes one batched Drex call (regret, stake, the cited fact, a self-specific check). The veto, the pooling and every number are Python. Intern is credited as the coding agent (AGENTS.md is its spec) and the headless Clerk (`backend/app/clerk.py`).
- **Slide 3:** the screenshot is the real app, captured on Nov 14, 2026 after `?run=headphones`. The verdict, condition and regret 0.86 → 0.05 come from the run logged in `assets/screens/headphones-run-2026-11-14.ndjson`. If you rerun and the numbers change, update the `.verdict` block in `index.html`. The screenshot predates the renaming of the selves.
- **Slide 4:** `assets/photos/best-price-right-time.webp` is an illustrative example (it says so on the image), cropped below its own headline. The live price search it stands for is The Bargain Hunter, via Keenable.

## PDF

`second-thoughts-deck.pdf` has 5 pages (slides 1–4 plus slide 4's closing line). To regenerate it after a change (it uses your installed Chrome, nothing big to download):

```bash
cd presentation && npm i --no-save playwright-core@1.48.2 && node scripts/export-pdf.mjs
```

## Files

```
presentation/
  index.html                      the deck (all CSS/JS inline)
  assets/fonts.css, fonts/        Instrument Serif, Geist, Geist Mono (Latin, SIL OFL)
  assets/screens/                 real app screenshots + the run log they came from
  assets/photos/                  slide 1 room photo, slide 4 illustration
  scripts/export-pdf.mjs          PDF export
  second-thoughts-deck.pdf
```

Colours and type are the app's own (`frontend/src/index.css`). Change them in `:root` at the top of `index.html`.
