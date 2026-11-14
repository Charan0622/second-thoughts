# Pitch kit

## 5-slide outline (Adobe Express)

**1 · The problem: "add to cart" is a one-person decision**
- Impulse buys happen in seconds. The facts that should stop you are spread across a bank statement, a savings sheet, old receipts and rules you set for yourself.
- Big line: *"Your future selves weigh in before you pay."*
- Visual: the four selves around a price tag.

**2 · Live demo (switch to the app)**
1. Shoes, $109.95 → **Buy** (4/4 agree, ~0.4 s)
2. Sony headphones, $349 → Goals and Already-Own-It object → both pick **"resell the earbuds AND put $149 into the Japan fund"** → **Buy, with a condition**. Click **Ask the Clerk** (Intern explains it).
3. Mac mini, $599 → **VETO**: "rent $1,850 on Nov 20 becomes unpayable". Point at the highlighted rent line from the real PDF.
- Backup: the recorded video.

**3 · Architecture: a swarm where Drex makes every call**
- Diagram from the README.
- Callouts:
  - Each self = **one batched Drex call** (regret, stake, decisive fact, a self-specific check)
  - **Drex picks the citation**; NDI's page and bbox turn it into a highlighted crop
  - **Code computes the numbers, Drex judges them**
  - Veto at p ≥ 0.93 · log-odds pooling · negotiation where every self scores every trade-off

**4 · Numbers**
- Hold-out (24 blind cards): council 75%, the same as a Qwen3.8-Max council but at about a quarter of the cost and latency; 0 false alarms; most robust when giveaway words are removed (71% vs 58%). Its lead over simpler methods isn't significant at n=24, and say so.
- Latency and cost: ~0.47 s and $0.0005 per verdict.
- Honesty slide: our own review tore the first benchmark apart; show what we changed.

**5 · Tool usage**
- Ledger screenshot plus a tally table:
  - **Drex:** perceive, votes, veto, citations, negotiation
  - **NDI:** 5 document types, citations, price read
  - **Intern:** Clerk at setup and for explanations; also the coding spec in AGENTS.md
  - **Keenable:** live prices
  - **DeepInfra:** spoken sentence and benchmark baseline
- Closing line: *"Every vote cites a line from your own documents. That's what makes a second thought something you can trust."*

## 60–90 s demo video script

| t | Screen | Voice-over |
|---|---|---|
| 0:00 | App idle, persona strip | "This is Maya. She has $425 of free cash until payday and she's saving for Japan." |
| 0:08 | Press **1** (shoes) | "Running shoes, $110. Four of her future selves vote in under half a second. Each one reads only its own documents." |
| 0:18 | Verdict **Buy** | "All four agree. Buy." |
| 0:22 | Press **2** (headphones) | "Now $349 headphones." |
| 0:27 | Goals and Owned cards turn red | "Goals You says this breaks her own rule: no gadgets over $200. Already-Own-It You found $179 earbuds in her receipts." |
| 0:37 | Negotiation chips fly to the cards | "Every self scores every trade-off with Drex. Both dissenters pick the same one: resell the earbuds and put $149 into the Japan fund." |
| 0:47 | Verdict **Buy, with a condition**; sentence spoken | (let the spoken sentence play) |
| 0:53 | Press **3** (Mac mini) | "And the Mac mini, $599." |
| 0:57 | VETO stamp | "Budget You vetoes it. Rent would bounce on November 20th. And here's the actual line from her bank statement." |
| 1:05 | Zoom on the highlighted crop, then the ledger | "Drex makes every decision. NDI grounds every vote. Intern is the clerk. Decided in 0.7 seconds, for a twentieth of a cent." |
| 1:15 | Logo | "Second Thoughts. Your future selves weigh in before you pay." |

Recording tip: open `http://localhost:5173/?run=shoes`, then use keys 2 and 3. macOS: ⌘⇧5 → record a selected portion.
