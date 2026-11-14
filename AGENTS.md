# AGENTS.md — Second Thoughts

Spec for coding agents (e.g. Intern) working in this repo. Read this before you change anything.

## What we are building

**Second Thoughts** asks your future selves before you pay. You point the laptop webcam at something you are about to buy. Four agents, your "selves", each read only their own documents. They vote, a pooling rule combines the votes, and you get a verdict in about a second. Every vote cites the exact document line it relies on.

This is a hackathon build (Drexathon, Track 2). The deadline is **15:00 Pacific**. Pick the boring, reliable option. A working demo matters more than complete coverage.

## Hard rules

- **Never commit secrets.** Keys live only in `.env`, which is gitignored. `.env.example` lists the variable names and no values.
- Do not commit `data/private/`, `*.sqlite`, `.venv/` or `node_modules/`.
- Generated persona data is **fictional**. Do not add real personal data.
- Every external call goes through its thin client (`drex.py`, `ndi.py`, `keenable_client.py`, `clerk.py`) and is recorded in the ledger (`ledger.py`): tool name, latency in ms, success or failure.
- Every vote must carry a citation: `{doc, page, line_text, bbox?}`. A vote without a citation is a bug.
- Numbers such as trade-off amounts, hours of work and slip days are **computed in code**. LLMs never compute them. LLMs only write prose.
- Keep the demo mode working at all times. It cycles three stored photos and needs no webcam and no live price read.

## Stack

- Backend: Python 3.12, `uv`, FastAPI, httpx (async), pydantic, SQLite (stdlib `sqlite3`).
- Frontend: Vite + React + TypeScript, framer-motion. One screen.
- External services:
  - **Drex** (Nace System One): `POST https://console.nace.ai/v1/systemone`, `Authorization: Bearer $NACE_API_KEY`. The body is `{model, state, questions}`, plus a top-level `images` array of base64 data URLs. Images are never allowed in `state`. Use `drex-max-v1.1` for image calls and `drex-v2.0` for text-only calls; `drex-v2.0` rejects images. Drex has no closed-book knowledge, so every fact it needs goes in `state`. The exact question field names are recorded in `spikes/FINDINGS.md`. Treat that file as the source of truth.
  - **NDI** (Nace Document Intelligence): parse / extract / ground through the **console route**. Console keys do not work on `ndi-api.nace.ai`. Extract persona documents once at startup and cache the results. Only the price read runs on the hot path.
  - **Keenable**: the `keenable` Python SDK (`search`, `fetch`, `to_context()`). It needs no key by default.
  - **DeepInfra**: Qwen. Used for the single verdict sentence and as Intern's System 2.
  - **Intern**: the "Clerk". It runs headless (`intern -p --json`) for the setup facts summary and to explain split verdicts.

## Layout

```
AGENTS.md  README.md  .env.example
data/persona/            # generated fictional demo docs (Maya)
data/demo_frames/        # 3 product photos for demo mode
spikes/                  # risk spikes + FINDINGS.md
backend/app/
  main.py                # FastAPI: GET /health, POST /ingest, POST /verdict, GET /ledger
  drex.py                # async Drex client
  ndi.py                 # ingest + extract + ground
  keenable_client.py
  clerk.py               # Intern headless wrapper
  agents/                # budget.py goals.py owned.py deal.py
  council.py             # veto, pooling, negotiation, bands
  tradeoffs.py           # fixed-order templated trade-offs
  facts.py               # SQLite fact store
  ledger.py              # per-tool counts + latency
backend/bench/
  cards.jsonl            # labelled scenario cards
  run_bench.py           # council vs single Drex call vs frontier-LLM council
frontend/src/
  App.tsx Camera.tsx Council.tsx Verdict.tsx Ledger.tsx
```

## The four selves

| Agent | Facts from | Question it answers |
|---|---|---|
| `budget` | bank_statement.pdf, pay_stub.jpg | Can I afford this before payday once the scheduled bills are paid? **Holds a veto.** |
| `goals` | savings_tracker.xlsx, rules memo (audio → transcript) | Does this delay the Japan goal or break one of my own rules? |
| `owned` | receipt_email.eml, paper_receipt.jpg | Do I already own something like this? |
| `deal` | Keenable live search | Is this a good price now, or will waiting (Black Friday, Nov 27) win? |

Each agent module exposes:

```python
async def vote(item: Item, facts: FactStore) -> Vote
# Vote = {agent, p_regret: float 0..1, stake: int 0..10, citation: Citation, rationale: str, latency_ms}
```

An agent builds a `state` string from **its own facts only**. It asks Drex: "Will this purchase be regretted or cause a problem within 30 days?" (yes/no → `p_regret`). It asks a second question for the 0–10 stake. Budget also asks the veto question: "Will a scheduled bill become unpayable?"

## Council protocol (`council.py`)

1. **Perceive**: Drex Max classifies the item category from the frame. NDI reads the price. If either fails, fall back to the manual category or price.
2. **Round one**: the four `vote()` calls run in parallel with `asyncio.gather`. A timeout on any one agent drops that agent from the pool and is logged. It never crashes the council.
3. **Veto**: if Budget's `p(bill unpayable) ≥ 0.93`, the verdict is **Wait**, and the condition is the next payday.
4. **Pool**: convert each vote to log-odds with `logit(p)`, take the mean weighted by stake (stake 0 counts as 0.5), then apply sigmoid.
5. **Negotiate** only when the pooled value is in `[0.35, 0.65]`. Walk `tradeoffs.py` in its **fixed order**. Each trade-off carries numbers computed in code. Re-ask the dissenting agents with the trade-off added to their state. The trade-off with the lowest pooled regret wins.
6. **Bands**: `< 0.35` Buy · `0.35–0.65` Buy with condition · `> 0.65` Wait 24h.
7. **Verdict payload**: band, pooled p, per-agent votes with citations, the condition, and the price in your own terms (hours of work at $42/hr, days the Japan trip slips at $280/month). Add one sentence from DeepInfra. If that call fails, use a template sentence.

## Demo persona (fictional)

Maya, 27, a designer saving for Japan. Today is Sat Nov 14, 2026. The balance is $2,480. Scheduled: savings $140 (Nov 15), phone $65 (Nov 18), rent $1,850 (Nov 20). **Free cash before payday is $425.** Pay is $42/hr, biweekly, with paydays Nov 13 and Nov 27. The Japan goal is $4,000 by Apr 2027, with $2,600 saved at $280/month. She bought earbuds in March for $179, with a 30-day return window. Her rule: "No gadgets over $200 before Japan. Running gear is exempt."

Expected demo outcomes: running shoes $160 → **Buy**; headphones $349 → **Buy with condition / Wait**; Mac Mini (price above $425) → **Budget veto, wait until Nov 27**.

## Commands

```bash
# backend
cd backend && uv run uvicorn app.main:app --reload --port 8000
# frontend
cd frontend && npm run dev
# bench
cd backend && uv run python bench/run_bench.py
```

## Done means

- `/verdict` returns the full payload in under ~2 s for the demo frames.
- The UI shows four cards that light up as votes arrive, the verdict banner and the ledger.
- Demo mode works with no network except Drex. When Keenable is unavailable, Deal falls back to a cached snapshot labelled as cached.
