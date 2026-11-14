# Benchmark results (v3)

> Re-run on the **current council code** on Sat Nov 14, 2026, starting 13:17 PT, after the Nace console stopped returning 403. Raw outputs:
> - `results_holdout.jsonl` and `results_v3.jsonl`
> - neutral-phrasing ablation: `results_holdout_neutral.jsonl` and `results_v3_neutral.jsonl`

## TL;DR

- **On 24 blind hold-out cards the Drex council scores 75% (95% CI 58–92%).** A second run scored 71%, with 23/24 verdicts identical between runs.
- **Its edge over the alternatives is small and not statistically significant:**

| Compared with | Its score | Council minus it (95% CI) |
|---|---|---|
| Plain-Python rules floor | 67% | +8 pts (−8 to +25) |
| Single Drex call with band definitions | 71% | +4 pts (−21 to +29) |
| Single frontier-LLM call | 67% | +8 pts (−12 to +29) |
| Frontier-LLM council | 75% | 0 pts (−21 to +21) |

- **Where the council is genuinely better:**
  - it is the only model-based method with **zero false alarms** (no Wait when the label is Buy) and the best Buy-vs-Wait separation;
  - it costs **$0.0005 per verdict at 0.47 s**, against $0.002 and 1.8 s for the LLM council.
- **Where it is worse:** it is the weakest model on Waits that are **not about bills**, catching 2 of 6. Its negotiation round tends to turn a "wait" into "buy with a condition".
- **On the original 40 cards it scores 92% (CI 82–100%), but the rules floor scores 88%.** That set's Waits all reduce to price > free cash, and the council was tuned on it, so it is a development set, not evidence.

## Setup

- **Two card sets.**
  - `cards.jsonl`: the original 40 cards (4 persona variants × 10 items). Their labels come from the rubric in `make_cards.py`, and the council was iterated against them in v1→v2. **Treat this set as a development set.**
  - `holdout_cards.jsonl`: **24 new hold-out cards** (the same 4 variants × 6 new items: groceries, a $1.79 snack, a subscription, gifts, a concert ticket, a refurbished laptop and iPad, furniture and sale items).
    - They were labelled **blind**, before the current agent code was read, by asking what a sensible friend who knows the persona would advise. Each card has a one-line `label_reason`.
    - Labels: 10 Buy / 5 Condition / 9 Wait.
    - **6 of the 9 Waits are not about bills.** The price fits under free cash, but the item duplicates owned earbuds, breaks her rule while eating most of her cash, or is an impulse buy that eats 90%+ of free cash.
- **Every method sees the same persona facts and the same code-computed lines:** free cash, rule check, receipts and web-price lines. Only the decider changes.
- **Methods:**

| Key | Method |
|---|---|
| `council` | Drex council: 4 selves, Budget veto, stake-weighted logit pool (stake capped at 5), and negotiation that must satisfy every dissenter. Deal abstains on unknown products or fewer than 3 on-topic prices. |
| `drex1` | One Drex `choice` call over all the facts, **with plain-English band definitions**. |
| `llm1` | One `Qwen/Qwen3.8-Max` call (DeepInfra, temperature 0) over all the facts, **with the same band definitions**. |
| `llmcouncil` | 4 × Qwen3.8-Max selves: same states, same pooling, stake cap, Deal abstention and veto. It has **no negotiation round**. |
| `rules` | **Rules floor**, three lines of Python over the shared facts: price > free cash → wait; breaks a parsed $ rule, or headphones while she owns earbuds → condition; else buy. |

- **Band definitions given to both single-call baselines:**
  - buy = affordable, within the person's own rules, not a duplicate;
  - buy_with_condition = buyable only with a specific trade-off;
  - wait = should not buy now.
- **Runs.** Methods run **sequentially per card**. Drex cost is the ledger input-token diff around each method, at $0.12 per million tokens. LLM cost uses an estimated DeepInfra list price ($1.2/M in, $6/M out).
- **Statistics.**
  - CIs are 95% percentile bootstrap over cards (4,000 resamples). The "council minus X" CIs are paired.
  - **Non-veto subset** means price ≤ free cash, the cards where "rent would bounce" can't decide the answer.
  - **False alarm** means predicted Wait when the label is Buy.
- **Commands:**
  - `uv run python bench/run_bench.py --cards holdout_cards.jsonl --out results_holdout.jsonl`
  - `--report <file>` re-prints the metrics.
  - `--neutral` runs the phrasing ablation.

## Hold-out: 24 blind cards (the numbers to quote)

| Method | Accuracy (95% CI) | Non-veto acc. (n=21) | Macro-F1 | False alarms (of 10 Buy) | Non-bill Waits caught (of 6) | Median latency | Tokens / verdict | Cost / verdict |
|---|---|---|---|---|---|---|---|---|
| **Drex council** | **75% (58–92)** | **71% (52–90)** | 0.71 | **0** | 2 | 0.47 s | 4,130 (Drex) | $0.00050 |
| Single Drex call + band defs | 71% (50–88) | 67% (43–86) | 0.54 | 2 | 6 | 0.31 s | 1,038 (Drex) | $0.00012 |
| Single Qwen3.8-Max call + band defs | 67% (46–83) | 62% (43–81) | 0.51 | 2 | 5 | 1.37 s | 984 | $0.00121 |
| Qwen3.8-Max council (no negotiation) | 75% (54–92) | 71% (52–90) | **0.72** | **0** | 5 | 1.77 s | 1,370 | $0.00199 |
| **Rules floor** (plain Python) | 67% (46–83) | 62% (43–81) | 0.62 | 0 | **0** | 0 s | 0 | $0 |

- **Paired difference, council minus other:**

| Other method | Difference (95% CI) |
|---|---|
| Rules floor | +8 pts (−8 to +25) |
| Single Drex call | +4 pts (−21 to +29) |
| Single LLM call | +8 pts (−12 to +29) |
| LLM council | +0 pts (−21 to +21) |

  **None of these differences is significant with 24 cards.**
- **Repeat run.** A second council run on the hold-out cards scored 17/24 (71%), and 23/24 verdicts were identical. Only `ho-nofrill-05` flipped.

**Confusion matrices.** Rows are labels; columns are predictions: buy / cond / wait.

| | council | drex1 | llm1 | llmcouncil | rules |
|---|---|---|---|---|---|
| label buy | 10 / 0 / 0 | 8 / 0 / 2 | 8 / 0 / 2 | 7 / 3 / 0 | 10 / 0 / 0 |
| label cond | 2 / 3 / 0 | 0 / 0 / 5 | 1 / 0 / 4 | 1 / 3 / 1 | 2 / 3 / 0 |
| label wait | 0 / 4 / 5 | 0 / 0 / 9 | 0 / 1 / 8 | 0 / 1 / 8 | 3 / 3 / 3 |

**Per-variant accuracy (6 cards each):**

| Method | maya | flush | tight | nofrill |
|---|---|---|---|---|
| council | 5 | 4 | 4 | 5 |
| drex1 | 5 | 3 | 5 | 4 |
| llm1 | 5 | 3 | 4 | 4 |
| llmcouncil | 5 | 4 | 4 | 5 |
| rules | 4 | 4 | 4 | 4 |

<details><summary>Per-card hold-out predictions (misses in bold)</summary>

| Card | Label | council | drex1 | llm1 | llmcouncil | rules |
|---|---|---|---|---|---|---|
| ho-maya-00 Trader Joe's weekly groceries $62.40 | buy | buy | buy | buy | buy | buy |
| ho-maya-01 Refurbished MacBook Air M3 $749 | wait | wait | wait | wait | wait | wait |
| ho-maya-02 Beats Studio Buds+ earbuds $169.99 | wait | **cond** | wait | wait | wait | **cond** |
| ho-maya-03 Concert ticket (GA) $135 | buy | buy | buy | buy | buy | buy |
| ho-maya-04 Refurbished iPad 10th gen $279 | cond | cond | **wait** | **wait** | **wait** | cond |
| ho-maya-05 Apple Watch Series 11 $399 | wait | wait | wait | wait | wait | **cond** |
| ho-flush-00 IKEA KALLAX shelf $89.99 | buy | buy | **wait** | buy | buy | buy |
| ho-flush-01 Refurbished MacBook Air M3 $749 | cond | cond | **wait** | **wait** | cond | cond |
| ho-flush-02 Sony WF-1000XM5 earbuds $229 | wait | **cond** | wait | wait | **cond** | **cond** |
| ho-flush-03 Le Creuset Dutch oven (sale) $279 | buy | buy | buy | **wait** | **cond** | buy |
| ho-flush-04 Herman Miller Aeron $1,395 | wait | wait | wait | wait | wait | **buy** |
| ho-flush-05 Nintendo Switch 2 $449 | cond | **buy** | **wait** | **wait** | cond | cond |
| ho-tight-00 Doritos snack $1.79 | buy | buy | buy | buy | buy | buy |
| ho-tight-01 Safeway essentials $48.20 | buy | buy | buy | buy | buy | buy |
| ho-tight-02 Spotify Premium $11.99 | buy | buy | buy | buy | **cond** | buy |
| ho-tight-03 Cashmere scarf (gift) $45 | cond | **buy** | **wait** | **buy** | **buy** | **buy** |
| ho-tight-04 Brooks Ghost 16 (sale) $89.95 | wait | **cond** | wait | **cond** | wait | **buy** |
| ho-tight-05 Concert ticket (GA) $135 | wait | wait | wait | wait | wait | wait |
| ho-nofrill-00 Bose QC Ultra Earbuds $299 | cond | cond | **wait** | **wait** | cond | **buy** |
| ho-nofrill-01 Refurbished MacBook Air M3 $749 | wait | wait | wait | wait | wait | wait |
| ho-nofrill-02 Trader Joe's weekly groceries $62.40 | buy | buy | buy | buy | buy | buy |
| ho-nofrill-03 West Elm accent chair (sale) $399 | wait | **cond** | wait | wait | wait | **buy** |
| ho-nofrill-04 Starbucks gift card $25 | buy | buy | buy | buy | buy | buy |
| ho-nofrill-05 Apple Watch SE (sale) $189 | buy | buy | **wait** | **wait** | **cond** | buy |

</details>

### Why the council misses what it misses (hold-out)

- **Negotiation turns objections into Conditions (4 of 6 misses).** In each case one or two selves object with p(regret) ≥ 0.95. Round one's pooled p is 0.53, 0.85, 0.60 and 0.93. Negotiation then finds an offer that satisfies every dissenter (final pooled p 0.03–0.11), so the verdict becomes Buy with condition.
  - **Duplicate earbuds (`maya-02`, `flush-02`).** The resolving offer is "resell the earbuds you own" (plus "+$29 to Japan" for `flush-02`). A friend would just say "you already have earbuds".
  - **Impulse buys that eat 90%+ of free cash (`tight-04`, `nofrill-03`).** The resolving offer is "Wait until payday (11/27)", which is reported as *Buy with condition*. Semantically that is close to a Wait, so the band boundary is fuzzy here. Counting a "wait until payday" condition as Wait would move the hold-out score to 19/24. On the original cards it would cost points instead, so we don't apply it.
- **A lone, confident dissenter gets out-voted (`flush-05` Switch 2; also `flush-12` Mac mini on the original set).**
  - Goals You says p(regret) ≈ 0.99–1.0 because the item breaks her $200 rule. Its stake of about 8 is capped at 5.
  - Three low-regret selves pull the pool to p = 0.31 (0.33 for the Mac mini), which is Buy. Because the band is Buy, negotiation never runs.
  - The design consequence: a rule break alone can't force a condition.
- **Round-one-only ablation.** Using the same council run but ignoring negotiation, the round-one pool plus veto also scores **18/24**. On the hold-out set, negotiation helped exactly as many cards as it hurt. On the original set it was +7 (30 → 37), which is consistent with negotiation having been tuned on that set.

## Original 40 cards (development set, re-run on current code)

| Method | Accuracy (95% CI) | Non-veto acc. (n=28) | Macro-F1 | False alarms (of 17) | Median latency | Tokens / verdict | Cost / verdict |
|---|---|---|---|---|---|---|---|
| Drex council | 92% (82–100) | 89% (79–100) | 0.93 | 0 | 0.40 s | 4,274 | $0.00051 |
| Single Drex call + band defs | 42% (28–57) | 21% (7–39) | 0.34 | 11 | 0.31 s | 1,099 | $0.00013 |
| Single Qwen3.8-Max call + band defs | 35% (20–50) | 7% (0–18) | 0.23 | 14 | 1.50 s | 1,074 | $0.00132 |
| Qwen3.8-Max council (no negotiation) | 50% (35–65) | 39% (21–57) | 0.51 | 0 | 1.74 s | 1,674 | $0.00241 |
| **Rules floor** | **88% (78–98)** | 82% (68–96) | 0.86 | 0 | 0 s | 0 | $0 |

- **Council minus other (paired):**

| Other method | Difference (95% CI) |
|---|---|
| Rules floor | **+5 pts (−10 to +20), not significant** |
| Single Drex call | +50 pts (+35 to +65) |
| Single LLM call | +58 pts (+42 to +72) |
| LLM council | +43 pts (+25 to +60) |

- **Council confusion matrix** (rows buy / cond / wait; columns buy / cond / wait): 15/2/0, 1/10/0, 0/0/12.
- **Council misses (3):**
  - `flush-12` Mac mini: label cond, predicted buy (the lone-dissenter pattern above);
  - `flush-17` jacket: label buy, predicted cond ("work 6.6 extra hours");
  - `nofrill-35` AirPods: label buy, predicted cond ("wait until payday").
- **Why the single-call baselines collapse here and not on the hold-out cards.** The original items carry strong Deal cues, such as "29% above the typical low price" and "Black Friday in 13 days". Given every fact at once, a single decider treats those cues as reasons to wait. The rubric deliberately ignores deal timing. Most hold-out items have too few reliable web prices, so the cue is absent and the single calls do much better (67–71%).
  - **The large council-vs-single-call gap on this set comes from how the labels treat price cues. It is not a general property of single calls.**

## Neutral-phrasing ablation (`--neutral`)

`--neutral` strips the rubric-shaped words from the computed lines: "OVER / within the limit", "EXCEEDS free cash … rent short", and "every bill stays covered". The numbers stay, but the conclusions are no longer spelled out.

| Method | Hold-out, normal | Hold-out, neutral | Original 40, normal | Original 40, neutral |
|---|---|---|---|---|
| Drex council | 75% | 71% | 92% | 92% |
| Single Drex call | 71% | 58% | 42% | 32% |
| Single Qwen call | 67% | 58% | — | — |
| Qwen council | 75% | 58% | — | — |
| Rules floor | 67% | 67% | 88% | 88% |

The council is the **least sensitive** to the giveaway words: −1 card on the hold-out set and no change on the original set. The single calls and the LLM council lose 2–4 hold-out cards each. This is the strongest evidence here that the per-self decomposition does real work. It is still 24 cards.

## What this does and does not show

**Does show:**
- **The council is cheap and fast.** It costs about 4.1k Drex input tokens ($0.0005) per verdict at about 0.45 s median, sequentially measured. The LLM council costs about 4× more and runs about 4× slower for the same hold-out accuracy.
- **It never raised a false alarm on either set.** It never said Wait when the label was Buy. The single-call baselines raise 2–14.
- **It holds up better than the alternatives when the computed lines stop spelling out the answer** (the neutral ablation).
- **It is stable run to run** (23/24 identical verdicts).
- **The veto handles "rent would bounce" perfectly,** but so does one line of Python.

**Does not show:**
- **The council has not been shown to beat a three-line rules floor, a single Drex call with band definitions, or an LLM council on held-out cards.** All the paired CIs include 0.
- **The 92% on the original 40 cards is a development-set number.** The council was iterated on those cards, and the rules floor gets 88% there.
- **Wait-type judgement beyond bills is the council's weak spot.** It catches 2 of 6 such Waits; the other model baselines catch 5–6. Negotiation is the main cause.
- **The labels come from one person** (blind to the code, but not independent annotators). 24 cards give ±17-point CIs. Some labels are judgement calls: `tight-04`, `nofrill-00` and `flush-03`.
- **The LLM council has no negotiation round,** so it is not a full replica of the council.
- **Deal facts come from cached Keenable searches.** Costs use Drex Max at $0.12/M input tokens and an *estimated* DeepInfra list price.

## Changelog

- **v1** (`RESULTS_v1.md`, `results_v1.jsonl`): council 28/40 (70%) on the original cards.
- **v2** (`RESULTS_v2.md`, `results_v2.jsonl`; the old `results.jsonl` is the same data): council 36/40 (90%).
  - Changes were made **after seeing the v1 errors**: two trade-off bugs ("resell earbuds" offered without earbuds; "top up Japan" offered without the rule), plus **one targeted design change**. Deal You now judges savings in dollars, which stopped "wait for Black Friday" on cheap items such as the $49 board game. **Most of the +8 came from that one change, on the cards it was aimed at.**
  - A later hostile review found more problems with v2:
    - all 12 Wait labels reduce to price > free cash (the rules floor scores 35/40);
    - the single-call baselines got no band definitions (a single Drex call with a fitted cut-off scores ~37/40);
    - methods ran concurrently against a global token ledger, so cost per verdict was mis-attributed;
    - there were no CIs;
    - "critical errors" was 0 for every method, so it carried no information.
- **v3** (this file):
  - **Council code changed since v2:**
    - negotiation must satisfy every dissenter;
    - stake cap of 5;
    - Budget "tight" days;
    - Deal abstains on unknown products or fewer than 3 on-topic prices;
    - take-home-pay hours.
  - **Benchmark changes:**
    - blind 24-card hold-out set;
    - band definitions for both single-call baselines;
    - rules floor;
    - sequential runs with a per-method ledger diff, so Drex cost is correct;
    - one shared httpx client for LLM calls;
    - bootstrap and paired CIs, non-veto subset, macro-F1, false alarms, confusion matrices and per-variant tables;
    - `--cards`, `--limit`, `--merge`, `--report` and `--neutral` flags.
  - **Bench bug fixed:** the "no receipts" variant now also clears `persona.owned`. The Owned self reads that list, so it previously still saw the earbuds receipt.
