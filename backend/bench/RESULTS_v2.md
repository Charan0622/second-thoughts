# Benchmark results

**Setup.** 40 labelled scenario cards (`cards.jsonl`): 4 persona variants × 10 items, with labels Buy / Buy with condition / Wait.
- Labels come from a written human rubric (see `make_cards.py`). Every card has a `label_reason`.
- One label was changed after human spot-check: `maya-01` → Buy with condition.
- Label mix: 17 Buy / 11 Condition / 12 Wait.

**Every method sees the same facts and the same code-computed numbers.** Only the decider changes.

## Final (v2)

| Method | Agreement with labels | Critical errors (said BUY, label = WAIT) | Median latency | Cost / verdict |
|---|---|---|---|---|
| **Drex council (ours)**: 4 selves + veto + pooling + negotiation | **36/40 (90%)** | **0** | **0.43 s** | $0.00062 |
| Single Drex call with all docs (`drex-max-v1.1`, one choice question) | 16/40 (40%) | 0 | 0.32 s | $0.00034 |
| Single frontier-LLM call (`Qwen/Qwen3.8-Max`, DeepInfra) | 13/40 (32%) | 0 | 1.75 s | $0.00129 |
| Frontier-LLM council (4× `Qwen3.8-Max`, same states, pooling and veto) | 17/40 (42%) | 0 | 2.07 s | $0.00238 |

**Prediction mix:**

| Method | Buy | Condition | Wait |
|---|---|---|---|
| Council | 17 | 11 | 12 (matches the label mix) |
| Single Drex call | 5 | 0 | 35 |
| Single LLM call | 0 | 1 | 39 |
| LLM council | 0 | 19 | 21 |

## What this shows

1. **Splitting the decision into selves is what works.** Given every fact at once, both single-call deciders latch onto *any* reason to wait, such as Black Friday or a rule, and say "wait" to almost everything. Their scores are close to the 30% Wait base rate.
2. **On the same council structure, Drex beats a frontier LLM:** 90% vs 42%, about 5× faster and 4× cheaper. The LLM selves report middling probabilities, so their pool never reaches "buy".
3. **Every council vote carries a citation that Drex chose** (`decisive_fact`) and that points to a page and region of a real document. The single-call baselines give a verdict with no grounding.
4. **No method made a critical error** (saying BUY when the label is WAIT). The veto plus code-computed headroom makes "rent would bounce" cases easy for every decider.

## Caveats (read these)

- **v1 → v2 changes were made after seeing v1 results.** In v1 (`RESULTS_v1.md`) the council scored **28/40 (70%)**. We then:
  - fixed two bugs: trade-offs offered "resell the earbuds" to personas without earbuds, and "top up the Japan fund" to personas without the rule;
  - made one design change: Deal You now judges the possible saving in dollars, so it stops saying "wait for Black Friday" on a $49 board game.

  We then reran **all four methods** on the v2 facts. The baselines see the same new Deal line, and they moved only slightly (32→40%, 32→32%, 40→42%). With only 40 cards, some overfitting to this set is possible.
- **The frontier-LLM council has no negotiation round.** Scoring every trade-off would need about 8 more LLM calls per self. Its "condition" verdicts come only from the pooled band.
- **The labels come from one rubric written by the team,** not independent annotators. The council's 4 remaining misses all disagree with the rubric's "uses more than 60% of free cash" concern, which Budget You doesn't treat as a problem when the bills are covered.
- The Deal facts come from cached Keenable searches (live web, 2026-11-14). Costs use Drex Max at $0.12 per million input tokens and an estimated DeepInfra list price for Qwen3.8-Max.

Raw per-card outputs: `results.jsonl` (v2) and `results_v1.jsonl`.
