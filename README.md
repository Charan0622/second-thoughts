# Second Thoughts

**Your future selves weigh in before you pay.**

Point your webcam at something you're about to buy. Four agents, your "selves", vote and negotiate a verdict in **under a second**. Each self reads only its own documents. Every vote cites the exact line of your own documents it came from, shown as a highlighted snip of the real page.

Built at **Drexathon 2026** · Track 2: **Swarm Intelligence** (Drex makes every agent's calls).

| Self | Grounded in | Asks |
|---|---|---|
| 💳 **Budget You** | Bank statement (PDF), pay stub (photo) | Can I afford this before payday once the scheduled bills are paid? **Holds a veto.** |
| 🗾 **Goals You** | Savings tracker (XLSX), transcript of my own spending rules (TXT) | Does it delay my goal or break my own rule? |
| 🧾 **Already-Own-It You** | Receipt email (EML), paper receipt (photo) | Do I already own something like this? |
| 🏷️ **Deal You** | Live web via Keenable | Is this a good price, or will waiting (Black Friday) win? |

## Demo

| Item | Verdict | Why |
|---|---|---|
| ASICS Gel-Nimbus 27, $109.95 | ✅ **Buy** | Affordable, running gear is exempt from the rule, matches the typical low price online |
| Sony WH-1000XM6, $349 | 🟡 **Buy, with a condition** | Goals ("breaks your $200 gadget rule") and Already-Own-It ("you own $179 earbuds") dissent. Both independently pick **"resell the earbuds AND put $149 into the Japan fund"**, and pooled regret falls from 0.83 to 0.04 |
| Apple Mac mini, $599 | ⛔ **Wait: Budget veto** | p(rent becomes unpayable) = 0.9995. The citation is the highlighted rent line on page 2 of the bank statement |

## How it works

```mermaid
flowchart LR
  subgraph Setup["Setup (once, cached)"]
    D[Persona docs<br/>PDF · JPG · XLSX · EML · TXT] -->|NDI extract<br/>+ citations| F[(Fact store<br/>values · page · bbox · quote)]
    F --> C[Citation crops<br/>highlighted line]
    I[Intern · the Clerk] -->|headless| S[Facts summary]
    K[Keenable] -->|live prices| W[(Deal cache)]
  end
  Cam[Webcam frame] -->|Drex Max: category + price range| P[Perceive]
  Cam -->|NDI: exact price| P
  P --> R1
  subgraph Council["Council (about 0.4–0.9 s)"]
    R1{{4 selves in parallel<br/>one batched Drex call each}} --> V[Veto check<br/>Budget p ≥ 0.93]
    V --> PL[Stake-weighted<br/>log-odds pool]
    PL -->|split or wait| N[Negotiate: each self scores<br/>every trade-off with Drex]
    PL -->|clear| B[Band]
    N --> B
  end
  B --> UI[Verdict + cited votes<br/>+ price in your terms]
  B -->|DeepInfra Qwen| SPK[One spoken sentence]
  B -->|split| CL[Intern · Clerk explains]
```

**Each self is one Drex call** (`drex-max-v1.1`) with four batched questions:
1. `regret` (noul): "Will the buyer regret this, or will it cause them a problem, within 30 days?", with explicit true/false criteria per self
2. `stake` (score 0–10): how much this matters from that self's point of view; this is its pooling weight
3. `decisive_fact` (choice over the self's own fact ids): **Drex picks the citation**
4. A self-specific check: `bill_unpayable` (the veto), `breaks_rule`, `duplicate` or `wait_wins`

**The code computes the numbers. Drex judges them.** Free cash, headroom, hours of work and Japan-slip days are computed in Python and put into the `state`. Drex never does arithmetic. In the risk spikes, `drex-v2.0` put P(unpayable) at 0.52 for a $349 item against $425 free cash. With the computed headroom in the state, `drex-max-v1.1` gives 0.005.

**Veto:** Budget You's `bill_unpayable ≥ 0.93` forces Wait. Nace reports that when Drex Max is at least 93% sure, it is right 97% of the time.

**Pooling:** weighted mean of `logit(p_regret)`, weights = stake. Bands: `< 0.35` Buy · `0.35–0.65` Buy with condition · `> 0.65` Wait.

**Negotiation, also all Drex:** when there is no veto and the result isn't a clear Buy, every self gets one more Drex call. In it, the self scores its regret under each templated trade-off (fixed order, amounts computed in code: skip two takeout orders = $54, resell earbuds ≈ +$90, …) and picks the one it prefers. The trade-off with the lowest pooled regret becomes the condition.

**Language models only write prose.** DeepInfra (Qwen) writes the one spoken sentence, and Intern writes the Clerk's explanation. Neither makes a decision.

## Results

**Being rerun on the current code. Earlier numbers are withdrawn.**

An internal adversarial review of our first benchmark (40 cards, written and labelled by us) found that it overstated the council's advantage:
- Every "wait" label reduced to *price > free cash*, which any method gets right from the shared facts. A few lines of plain code scored 35/40.
- The single-call baselines weren't given the band definitions the council effectively uses. With a fitted cut-off, a single Drex call matched the council.
- The jump from 70% to 90% came from one change aimed at specific cards.
- Costs were mis-attributed because the methods ran concurrently.

The rebuilt benchmark adds:
- 24 hold-out cards labelled blind, including "wait" cases that aren't about bills
- fairer baselines
- a plain-rules floor
- bootstrap confidence intervals and the subset where cards are *not* decided by price vs. free cash
- per-method cost, measured with the methods run one after another

Results go in [`backend/bench/RESULTS.md`](backend/bench/RESULTS.md).

## Tool usage

| Tool | Where it's used |
|---|---|
| **Drex** (System One) | Perceive (Drex Max, image), all 4 votes, the veto, the citation choice, the negotiation scoring. That's 5–9 calls per verdict at about 350 ms median |
| **NDI** | Extracts all 6 persona documents (PDF, 2 photos, XLSX, EML, TXT) with page/bbox citations, which become the highlighted crops; reads the price tag from the camera frame |
| **Intern** | **In the product:** the Clerk, run headless (`intern -p --json`). It writes the persona facts summary at setup ([`docs/clerk_summary.md`](docs/clerk_summary.md)) and explains split verdicts in ~4 s. **As a coding agent:** given `AGENTS.md` as its spec, it wrote [`backend/tests/test_council_math.py`](backend/tests/test_council_math.py) (12 tests of the pooling, bands and trade-offs; 8 turns, 17 Drex System 1 decisions) |
| **Keenable** | Live web prices and Black Friday signals for Deal You, cached per query |
| **DeepInfra** | Qwen writes the spoken verdict sentence; Qwen3.8-Max is the frontier baseline in the benchmark |

The live **usage ledger** in the UI shows calls, median latency and dollars per tool (`GET /api/ledger`).

**Tally while building and benchmarking** (from the ledger, 2026-11-14 12:06 PT):

| Tool | Calls | Errors | Median latency | Spend |
|---|---|---|---|---|
| Drex | 897 | 0 | 300 ms | $0.095 (792k input tokens) |
| NDI | 11 jobs | 0 | 6.2 s | $0.156 |
| Intern | 10 runs | 1 (an early timeout, since fixed) | 51 s (setup runs are long; explanations ~4 s) | — |
| Keenable | 33 searches | 0 | 2.0 s | — |
| DeepInfra | 23 calls (verdict sentences); about 400 more Qwen3.8-Max calls ran as benchmark baselines and aren't in the ledger | 0 | 1.1 s | — |
| **Total** | | | | **≈ $0.25** |

## Run it

Prerequisites: Python 3.12 via [uv](https://docs.astral.sh/uv/), Node 20+.

```bash
cp .env.example .env          # fill NACE_API_KEY and DEEPINFRA_API_KEY (Keenable works keyless)

# backend (first start extracts the persona docs with NDI, ~10 s, then caches them)
cd backend && uv sync && uv run uvicorn app.main:app --port 8000

# frontend (in another terminal)
cd frontend && npm install && npm run dev      # http://localhost:5173
```

**Frontend-only work needs no keys or backend.** Open `http://localhost:5173/?mock=1`. A built-in mock replays realistic event streams for all three demo items.

Keys: `1` `2` `3` (or ← →) pick a demo item. `?run=headphones` (or `shoes` / `macmini`) starts a run on load.

Full test guide: [`docs/TESTING.md`](docs/TESTING.md). Tests: `cd backend && uv run pytest tests -q` (offline). Benchmark: `cd backend && uv run python bench/run_bench.py` (40 cards, about 5 min, about $0.20).

## Repo map

| Path | What |
|---|---|
| `docs/API.md` | Backend ⇄ frontend contract (streamed NDJSON events) |
| `AGENTS.md` | Spec for coding agents (Intern) |
| `backend/app/` | `council.py` (veto, pooling, negotiation), `agents/` (four selves), `facts.py` (NDI fact store and crops), `tradeoffs.py`, `drex.py`, `ndi.py`, `keenable_client.py`, `voice.py`, `clerk.py`, `ledger.py` |
| `backend/bench/` | `cards.jsonl` (40 labelled scenarios with reasons), `run_bench.py`, `RESULTS.md` |
| `frontend/src/` | React UI: `Camera`, `Council`, `Gauge`, `Verdict`, `Ledger`, `mock.ts` |
| `data/persona/` | Fictional demo documents for Maya Chen (`scripts/gen_persona.py`) |
| `spikes/FINDINGS.md` | Measured API behaviour and latencies from the risk spikes |

All persona data is invented. No real personal or financial data is used.
