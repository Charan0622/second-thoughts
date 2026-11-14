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

## 3. NDI — TODO (live)
## 4. Price from frame — TODO (live)
## 5. Keenable [live]

- Works keyless: `Keenable().search(q)` returns a `SearchResponse`, and `.to_context()` gives numbered results with snippets.
- `search("Sony WH-1000XM6 price")` took **1.75 s**. Top hit: Amazon, $378.00 (list $459.99). → Too slow for the hot path. **Pre-fetch per demo item and cache.**
- Keyless use is rate-limited per hour. Setting `KEENABLE_API_KEY` (from https://keenable.ai/console) lifts the limit; the SDK sends it as `X-API-Key`.

## DeepInfra [live]

- `GET https://api.deepinfra.com/v1/openai/models` → 200 with 178 models. `Qwen/Qwen3.8-27B` exists, so Intern's System 2 id is valid.

## Latencies — TODO (live)
