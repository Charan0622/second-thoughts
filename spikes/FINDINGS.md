# Spike findings

Sources: Nace agent docs (`https://console.nace.ai/llms-full.txt`) and `nace-sdk` 0.8.0. Each entry is marked **[docs]** until a live call confirms it, then **[live]**.

## 1. Drex question shape [docs; noul confirmed live]

Live check, 2026-11-14: `drex-max-v1.1`, one noul question → HTTP 200, `noul` 0.906, `evaluation_time_ms` 162.7, 0.30 s round trip from SF, 93 input tokens. The response shape matches the docs.

`POST https://console.nace.ai/v1/systemone`, with `Authorization: Bearer $NACE_API_KEY` and `Content-Type: application/json`. Optional `X-Nace-Client` header.

Body: `{model, state, questions: {<id>: question}, images?: [...]}`

| type | `instructions` | `criteria` | answer fields |
|---|---|---|---|
| `noul` | string (optional) | `{"true": str, "false": str}` (optional; needs instructions or criteria) | `noul` (P(yes)), `confidence` |
| `choice` | string | **required** object `{label: description\|null}` | `choice`, `confidence`, `probabilities{label: p}` |
| `score` | string | **required** array, low → high | `score` (expected index, fractional), `legend`, `probabilities{"0": p, …}`, `confidence` |

Response: `{model, answers: {<id>: {...type...}}, usage: {input_tokens, output_tokens, image_tokens?}, evaluation_time_ms, request_id}`

- Batching questions in one call sends the state once. The docs measured about 47% fewer input tokens. **Each agent should send one call holding all its questions.**
- `criteria.true`/`false` on a noul question move the answer a lot. Use them to define "regret" and "unpayable" precisely.
- A 422 has `error.issues[].path` and is not retryable.
- Python SDK: `NaceClient(model=...).system_one(state=..., questions={"x": Noul(instructions=...)})`, then `result.choices[...]` / `result.scores[...]`. `AsyncNaceClient` is available.

## 2. Drex Max images [docs]

- `model: "drex-max-v1.1"`. Top-level `images: ["data:image/jpeg;base64,..."]` (a bare base64 string also works). PNG/JPEG/WebP.
- At most 8 images. The body is at most 4 MiB including base64, which leaves about 3 MiB of image bytes. Images are downscaled to 1280×1280 px, so **send at most 1280 px JPEG**.
- An image placed in `state` or `questions` returns 422. Any other model given `images` returns 422.
- Drex Max's token budget covers the **whole** request (state + images + all questions). Drex 2.0's budget is per question (state ≤131k tokens).

### Spike 1 live results: Budget state, 4 batched questions (noul ×2, score, choice)

| model | $160 shoes regret / unpayable | $349 headphones | $599 Mac mini | round trip (median) | 4 parallel, wall |
|---|---|---|---|---|---|
| drex-v2.0 | 0.169 / 0.234 | 0.296 / **0.518** ✗ | 0.794 / 0.936 | 195 ms (eval 26–97 ms) | 254 ms |
| drex-max-v1.1 | 0.029 / 0.010 | 0.567 / **0.030** ✓ | 0.984 / **0.959** ✓ veto | 266 ms (eval 159–242 ms) | 352 ms |

- **Decision: use `drex-max-v1.1` for every agent vote.** drex-v2.0 is miscalibrated on the price-versus-free-cash comparison ($349 < $425 gave unpayable 0.518). Max is only about 100 ms slower, and the four parallel calls finish in 352 ms.
- The $599 veto at 0.959 clears 0.93, but only just. **Put the computed headroom in `state`** ("Price exceeds free cash by $174.00") so Drex judges a number the code computed instead of doing the arithmetic. This matches the AGENTS.md rule.
- `choice` and `score` both work. The `category` choice was correct for every item on both models. 4 questions use about 300–400 input tokens.

## 2. Drex Max images [live]

Price-tag JPEG at 1024 px max, with two choice questions: `category`, and `price_bucket` (<100 / 100–199 / 200–399 / 400+).

| frame | category | price_bucket | round trip | eval |
|---|---|---|---|---|
| shoes $160 | running_gear 0.99 | 100_199 0.98 | 385 ms | 182 ms |
| headphones $349 | headphones 0.99 | 200_399 0.99 | 284 ms | 144 ms |
| mac mini $599 | computer 0.99 | 400_plus 0.99 | 305 ms | 172 ms |

The image used 672 image tokens out of 905 input tokens. **Drex Max reads the price range from the frame**, so the first view can show a coarse price within about 300 ms.

## 3. NDI with a console key [live] ✅

- `nace_sdk.AsyncNaceClient(api_key=...)` → `documents.upload(path)` → `.as_source()` → `documents.extract(src, schema=..., citations={...}, wait_seconds≤60)` → `jobs.wait()` if not finished. **`wait_seconds` is capped at 60 by the SDK.**
- Bank statement PDF: **8.4 s** total (0.6 s of that was upload). It found `available_balance` 2480, `account_last4` "4417", and all 3 scheduled payments with dates and amounts. The amounts come back negative.
- Each `fields[]` entry has `{path, value, status: found|not_found, confidence, ambiguous, derived, citations: [{location: {kind: page_region, page, polygons: [[[x,y]…]] (normalized 0–1)}, source_text}]}`. **The citations already include page + bbox + quote, so a separate `ground` call isn't needed for votes.**
- `food_delivery_count` came back `not_found`, because aggregates aren't extracted. Extract the transaction list instead and **count in code**.
- → Pre-extract every persona doc at startup (about 8 s each, run in parallel) and cache the results in SQLite.

## 4. Price from a frame [live] ✅ but slow

- NDI extract on the headphones price-tag photo gave `{"price": 349, "product_name": "Sony WH-1000XM6 Headphones"}` in **4.7 s**.
- **That's too slow for the ~1 s hot path.** Plan: Drex Max gives category + price bucket in ~300 ms → NDI exact price arrives in ~5 s (UI shows "reading price…") → the council runs. Demo mode uses cached NDI results for the stored frames. A manual price field overrides everything.

## 5. Keenable [live]

- It works without a key: `Keenable().search(q)` returns a `SearchResponse`, and `.to_context()` gives numbered results with snippets.
- `search("Sony WH-1000XM6 price")` took **1.75 s**. Top hit: Amazon $378.00 (list $459.99). With a key it's 1.7–2.0 s, and the Mac mini query returns live early-Black-Friday articles from 2026-11-14.
- → **Too slow for the hot path. Pre-fetch per demo item and cache** with a timestamp. Keyless use is rate-limited per hour; `KEENABLE_API_KEY` is set in `.env` and sent as `X-API-Key`.

## DeepInfra [live]

- `GET https://api.deepinfra.com/v1/openai/models` → 200 with 178 models. `Qwen/Qwen3.8-27B` is present, so Intern's System 2 id is valid.

## Intern [live]

- `intern --system1 drex-latest --system2 deepinfra/Qwen/Qwen3.8-27B -p "say ok"` → `ok`, 3 s, 3,940 input tokens.

## Latency budget for one verdict (live path)

Perceive (Drex Max image) ~300 ms → round one (4× Drex Max, parallel) ~350 ms → negotiation if needed (parallel) ~350 ms → Qwen sentence (async, not blocking) → **about 1 s to the verdict, not counting the NDI price read.**

## Spec issue found

- The earbuds were bought in March with a 30-day return window, so they **can't be returned in November**. The trade-off "return March earbuds = +$179" doesn't hold. Replace it with "resell earbuds ≈ +$90 (est.)", or let Already-Own-It You argue "you already have noise-cancelling earbuds".
