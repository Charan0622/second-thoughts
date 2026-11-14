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

## 1b · First visit: choose whose documents
A fresh install (no `data/private/mode.json`) is in persona mode **none**. Open the app and the camera is replaced by **"Whose money is this?"**:
- **📄 Upload your documents** opens the documents panel. The first upload switches to mode **mine**: only your files are used. Each slot you skip says *not uploaded* and shows up as a warning (for example "No pay stub uploaded — payday unknown (assuming …, 14 days from today)"). Maya's numbers are never used in its place.
- **Try the demo persona (Maya)** switches to mode **demo**: Maya's documents, exactly as before.
- Until you choose, nothing runs. `/api/verdict` answers with the error "Choose your documents or the demo persona first", and the header reads "No documents yet".
- **Remove my documents** (in the documents panel) deletes every upload and goes back to onboarding.
- Reset from a terminal: `rm data/private/mode.json` (back to onboarding), or `curl -X POST localhost:8000/api/mode -H 'Content-Type: application/json' -d '{"mode":"demo"}'`.
- Rules accept text, PDF, DOCX or a photo of a note. Audio uploads are rejected.

Checks for mode **mine**:
- [ ] Upload only a bank statement. The header shows its name and free cash. The panel lists the other four slots as *not uploaded*, each with a flag.
- [ ] Ask about an item. All four selves still vote. The Planner says it has no goal or rules on file, and The Minimalist has no receipts.

## 2 · Demo persona (the pitch path)
Choose **Try the demo persona (Maya)**, or open `?run=…`, which switches to the demo persona for you. The main entry is now **📷 Upload a photo of what you want to buy** (or the live camera, or 📱 Connect phone). The three demo items sit behind the small **or try an example** link, and **1 / 2 / 3** run them directly as a presenter backup. Both appear only for the demo persona.

| Key | Item | You should see |
|---|---|---|
| 1 | ASICS Gel-Nimbus 27, $109.95 | 4 cards light up BUY → green **Buy it** |
| 2 | Sony WH-1000XM6, $349 | Goals + Already-Own-It say WAIT → negotiation chips → amber **Buy — with a condition** ("Resell the earbuds … AND put $149 into the Japan fund") |
| 3 | Apple Mac mini, $599 | **VETO** stamp on The Accountant → red **Wait** ("Wait until payday (11/27)") |

Check on each run:
- [ ] Each card shows a citation; The Accountant shows a **highlighted crop** of the bank statement
- [ ] Gauge needle moves (and moves again after negotiation for item 2)
- [ ] "decided in ~0.4–0.9 s"
- [ ] **The sentence is spoken aloud**. The 🔊 / 🔇 button toggles it. Chrome only allows speech after you've interacted with the page, so click or press a key once first.
- [ ] After item 2, **Ask the Clerk** shows Intern's paragraph in ~4–30 s
- [ ] The tool ledger (bottom left) counts up

Pitch shortcut: `http://localhost:5173/?run=headphones` (or `shoes` / `macmini`) switches to the demo persona and starts a run on page load.

## 3 · Upload a photo / live webcam
- **📷 Upload a photo of what you want to buy**: pick any image. It is downscaled to ≤ 1280 px JPEG in the browser and sent exactly like a webcam capture (`{frame, price}`).
1. The live camera starts automatically. Allow camera access when Chrome asks; localhost is allowed.
2. Point the camera at a product with a visible price tag. Holding a phone showing one of the `data/demo_frames/price_tag_*.jpg` images also works.
3. Click **Capture & ask**.
   - Drex Max reads the category and price range (~0.3 s). NDI then reads the exact price (**~5 s for a new frame**) before the council runs.
   - To skip the wait, type a price in **Price $** first. A manual price overrides everything.
   - If NDI can't find a price, the midpoint of Drex's price range is used, tagged with the source "bucket".
4. If you see "Camera unavailable": check System Settings → Privacy & Security → Camera → enable your browser.

## 3b · Connect your phone
Take the photo with a phone instead of the laptop webcam. The laptop runs the council exactly as for a webcam capture.
1. Run the backend on all interfaces: `uv run uvicorn app.main:app --host 0.0.0.0 --port 8000`. Without `--host 0.0.0.0` the phone can't reach it.
2. Put the phone and laptop on the **same Wi-Fi**.
3. Click **📱 Connect phone** in the header. Scan the QR code. It opens `http://<laptop-LAN-IP>:8000/phone`.
4. On the phone, tap **Take photo**. You can type a **Price $** first to skip the NDI price read. The overlay on the laptop closes and the council runs on that photo.
- macOS may ask whether Python can accept incoming network connections. Click **Allow**.
- Venue Wi-Fi often isolates clients from each other, so the phone can't reach the laptop. Fallback: turn on the phone's hotspot and join the laptop to it, then reopen the QR because the IP changes.
- The phone page uses a file input with `capture`, not getUserMedia, so it works over plain http.
- Check from the laptop: `curl -s localhost:8000/api/phone/info` returns the URL the QR encodes.

### Phone camera without shared Wi-Fi
**Option A: iPhone as the webcam (macOS Continuity Camera, no network needed).** Keep the iPhone near the Mac, on the same Apple ID, with Wi-Fi and Bluetooth on. In the app, use the live camera and pick **iPhone Camera** in the **Camera** dropdown. The app picks it automatically when it's available.

**Option B: secure public phone link (any phone, any network, including mobile data).**
```bash
./scripts/phone_tunnel.sh        # starts a temporary https://….trycloudflare.com link; Ctrl+C to stop
```
**📱 Connect phone** now shows a QR code for that HTTPS link. Through the tunnel, **only** `/phone` and `/api/phone/frame` are reachable. Documents, persona, crops, the ledger and verdicts all return 403. The link changes every time the script starts.

## 4 · Frontend without a backend
`http://localhost:5173/?mock=1` replays all three flows with no keys and no network. Mock mode always behaves as the demo persona: there's no onboarding, **or try an example** and 1/2/3 work, and an uploaded photo replays the headphones flow.

## 5 · Backend checks
```bash
cd backend
uv run pytest tests -q                                    # offline tests (council math, trade-offs, persona modes)
curl -sN -X POST localhost:8000/api/verdict -H 'Content-Type: application/json' -d '{"demo_item":"macmini"}'
                                                          # watch the NDJSON events stream in (needs mode demo, see 1b)
curl -s localhost:8000/api/ledger                         # per-tool usage
uv run python bench/run_bench.py --limit 5                # quick benchmark (full: ~5 min, ~$0.20)
```

## Troubleshooting
| Symptom | Fix |
|---|---|
| `address already in use` | `pkill -f "uvicorn app.main:app"` or `lsof -i :8000` |
| MOCK badge with backend running | Backend must be on port 8000; restart `npm run dev` |
| First verdict slow (~5 s) | The NDI price read on a new frame; later runs of the same frame are cached |
| The Bargain Hunter citation says "(cached)" | Expected: Keenable results are cached for 6 h |
