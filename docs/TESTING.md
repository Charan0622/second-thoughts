# How to test Second Thoughts

## 0 · One-time setup
```bash
cp .env.example .env                    # NACE_API_KEY + DEEPINFRA_API_KEY (KEENABLE_API_KEY optional)
cd backend && uv sync && cd ..
cd frontend && npm install && cd ..
```

## 1 · Start it (two terminals)
```bash
cd backend && uv run uvicorn app.main:app --port 8000     # first start: NDI extracts the 6 persona docs (~10 s), then cached
cd frontend && npm run dev                                 # open http://localhost:5173 in Chrome
```
Backend check: `curl localhost:8000/api/health` should return `{"ok":true,"facts_loaded":true,"errors":{}}`.
If the UI shows a **MOCK** badge, it can't reach the backend.

## 2 · Demo mode (the pitch path)
Demo mode is on by default. Press **1 / 2 / 3** (or click the buttons):

| Key | Item | You should see |
|---|---|---|
| 1 | ASICS Gel-Nimbus 27, $109.95 | 4 cards light up BUY → green **Buy it** |
| 2 | Sony WH-1000XM6, $349 | Goals + Already-Own-It say WAIT → negotiation chips → amber **Buy — with a condition** ("Resell the earbuds … AND put $149 into the Japan fund") |
| 3 | Apple Mac mini, $599 | **VETO** stamp on Budget You → red **Wait** ("Wait until payday (11/27)") |

Check on each run:
- [ ] Each card shows a citation; Budget You shows a **highlighted crop** of the bank statement
- [ ] Gauge needle moves (and moves again after negotiation for item 2)
- [ ] "decided in ~0.4–0.9 s"
- [ ] **The sentence is spoken aloud**. The 🔊 / 🔇 button toggles it. Chrome only allows speech after you've interacted with the page, so click or press a key once first.
- [ ] After item 2, **Ask the Clerk** shows Intern's paragraph in ~4–30 s
- [ ] The tool ledger (bottom left) counts up

Pitch shortcut: `http://localhost:5173/?run=headphones` (or `shoes` / `macmini`) starts a run on page load.

## 3 · Live webcam
1. Switch **Demo mode** off and allow camera access when Chrome asks. localhost is allowed.
2. Point the camera at a product with a visible price tag. Holding a phone showing one of the `data/demo_frames/price_tag_*.jpg` images also works.
3. Click **Capture & ask**.
   - Drex Max reads the category and price range (~0.3 s). NDI then reads the exact price (**~5 s for a new frame**) before the council runs.
   - To skip the wait, type a price in **Price $** first. A manual price overrides everything.
   - If NDI can't find a price, the midpoint of Drex's price range is used, tagged with the source "bucket".
4. If you see "Camera unavailable": check System Settings → Privacy & Security → Camera → enable your browser.

## 4 · Frontend without a backend
`http://localhost:5173/?mock=1` replays all three flows with no keys and no network.

## 5 · Backend checks
```bash
cd backend
uv run pytest tests -q                                    # 12 offline tests (council math, trade-offs)
curl -sN -X POST localhost:8000/api/verdict -H 'Content-Type: application/json' -d '{"demo_item":"macmini"}'
                                                          # watch the NDJSON events stream in
curl -s localhost:8000/api/ledger                         # per-tool usage
uv run python bench/run_bench.py --limit 5                # quick benchmark (full: ~5 min, ~$0.20)
```

## Troubleshooting
| Symptom | Fix |
|---|---|
| `address already in use` | `pkill -f "uvicorn app.main:app"` or `lsof -i :8000` |
| MOCK badge with backend running | Backend must be on port 8000; restart `npm run dev` |
| First verdict slow (~5 s) | The NDI price read on a new frame; later runs of the same frame are cached |
| Deal You citation says "(cached)" | Expected: Keenable results are cached for 6 h |
