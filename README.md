# Second Thoughts

**Your future selves weigh in before you pay.** Point your webcam at something you're about to buy. Four agents, your "selves", each grounded in your own documents, vote and negotiate a verdict in under a second. Every vote cites the exact line it came from.

Built at Drexathon 2026 (Track 2: Swarm Intelligence) on Nace **Drex**, **NDI** and **Intern**, with **Keenable**, **DeepInfra** and **Adobe**.

> Full write-up, architecture and benchmark results are coming. This is the quick start.

## Quick start

Prerequisites: Python 3.12 via [uv](https://docs.astral.sh/uv/), Node 20+.

```bash
cp .env.example .env          # fill NACE_API_KEY and DEEPINFRA_API_KEY (Keenable works keyless)

# backend (first start extracts the persona docs with NDI, ~10 s, then caches them)
cd backend && uv sync && uv run uvicorn app.main:app --port 8000

# frontend (in another terminal)
cd frontend && npm install && npm run dev      # http://localhost:5173
```

**Frontend-only work needs no keys or backend.** Open `http://localhost:5173/?mock=1`. A built-in mock (`frontend/src/mock.ts`) replays realistic event streams for all three demo items.

Keys: `1` `2` `3` (or ← →) pick a demo item. `?run=headphones` (or `shoes` / `macmini`) starts a run on load.

## Repo map

| Path | What |
|---|---|
| `docs/API.md` | Backend ⇄ frontend contract (streamed NDJSON events) |
| `AGENTS.md` | Spec for coding agents (Intern) |
| `backend/app/` | FastAPI app: `council.py` (veto, pooling, negotiation), `agents/` (four selves), `facts.py` (NDI fact store and citation crops), `drex.py`, `ndi.py`, `keenable_client.py`, `voice.py` (DeepInfra), `clerk.py` (Intern) |
| `backend/bench/` | 40 labelled scenario cards and a benchmark runner |
| `frontend/src/` | React UI: `Camera`, `Council`, `Gauge`, `Verdict`, `Ledger` |
| `data/persona/` | Fictional demo documents (Maya Chen). Generate them with `scripts/gen_persona.py` |
| `spikes/FINDINGS.md` | Measured API behaviour and latencies |

All persona data is invented.
