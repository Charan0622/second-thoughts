# API contract (backend ⇄ frontend)

The backend runs at `http://localhost:8000`. The Vite dev server proxies `/api` and `/files` to it. Every response is JSON.

## `POST /api/verdict` → streamed NDJSON (`application/x-ndjson`)

Request:
```json
{ "demo_item": "shoes" | "headphones" | "macmini" | null,
  "frame": "data:image/jpeg;base64,..." | null,
  "price": 349.0 | null,
  "item_name": "Sony WH-1000XM6" | null }
```
Send either `demo_item` or `frame`. A manual `price` overrides the price read from the frame.

The response is one JSON object per line, in the order shown. The frontend reads it with `fetch` and a stream reader, splitting on `\n`.

```jsonc
{"type":"perceive_start"}
{"type":"perceive", "item_name":"Sony WH-1000XM6 Headphones", "category":"headphones", "category_p":0.99,
 "price_bucket":"200_399", "price":349.0, "price_source":"ndi"|"manual"|"cache"|"bucket", "ms":290}
{"type":"council_start", "agents":["budget","goals","owned","deal"]}
// one per agent, in arrival order (they run in parallel):
{"type":"vote", "agent":"budget", "label":"Budget You",
 "p_regret":0.03, "stake":2.3, "stance":"buy"|"wait",           // stance = p_regret < 0.5 ? "buy" : "wait"
 "headline":"Fits in $425 free cash; $76 left before payday",       // computed in code
 "citation":{"doc":"bank_statement.pdf", "doc_label":"Bank statement", "page":1,
             "quote":"Available balance (Nov 14) $2,480.00",
             "bbox":[0.72,0.25,0.80,0.27] | null,                   // normalized x0,y0,x1,y1
             "crop_url":"/files/crops/budget_balance.png" | null},  // image of the cited region
 "cite_p":0.91,               // Drex's probability for the fact it chose as decisive
 "model":"drex-max-v1.1", "ms":312}
{"type":"veto", "agent":"budget", "p":0.959, "threshold":0.93, "fired":true,
 "reason":"Rent $1,850 on Nov 20 becomes unpayable"}
{"type":"pool", "p":0.58, "band":"buy_with_condition", "weights":{"budget":2.3,"goals":3.1,"owned":2.0,"deal":1.4}}
// only when 0.35 <= p <= 0.65 and no veto:
{"type":"negotiation", "offers":[{"id":"skip_takeout_2","label":"Skip two takeout orders","amount":54.0 /* number or null */}, ...],
 "picks":[{"agent":"goals","offer_id":"wait_payday","p_before":0.71,"p_after":0.22}],
 "chosen":{"id":"wait_payday","label":"Wait until payday (Nov 27)","p_after":0.31}, "ms":340}
{"type":"verdict", "band":"buy"|"buy_with_condition"|"wait",
 "title":"Buy — with a condition", "p":0.31,
 "condition":"Wait until payday (Nov 27)" | null,
 "tally":{"buy":2,"wait":2},
 "price_terms":{"hours_of_work":8.3, "japan_slip_days":37, "pct_free_cash":82},
 "total_ms":712}
{"type":"sentence", "text":"Your budget is fine but your own rule says no gadgets over $200 — wait for payday.", "source":"deepinfra"|"template"}
{"type":"done"}
// on failure at any point:
{"type":"error", "message":"..."}
```

Band thresholds: `< 0.35` → `buy`, `0.35–0.65` → `buy_with_condition`, `> 0.65` → `wait`. A veto always gives `wait`.

## `GET /api/demo_items`
```json
[{"id":"shoes","name":"TrailFlow 5 Running Shoes","price":160,"frame_url":"/files/demo_frames/price_tag_shoes.jpg"}, ...]
```

## `GET /api/ledger`
```json
{"tools":{
   "drex":     {"calls":42,"errors":0,"ms_median":280,"input_tokens":15800},
   "ndi":      {"calls":7,"errors":0,"ms_median":6100},
   "keenable": {"calls":3,"errors":0,"ms_median":1800},
   "deepinfra":{"calls":5,"errors":0,"ms_median":900},
   "intern":   {"calls":1,"errors":0,"ms_median":14000},
   "adobe":    {"calls":0,"note":"Firefly avatars + Express slides (offline)"}},
 "verdicts":6, "cost_usd_est":0.012}
```

## `GET /api/persona`
A summary for the "who am I" strip, for example `{"name":"Maya Chen","free_cash":425,"next_payday":"2026-11-27","japan":{"target":4000,"saved":2600,"monthly":280},"rules":["No gadgets over $200 before Japan. Running gear is exempt."]}`

## `GET /api/health` → `{"ok":true,"facts_loaded":true}`

## Static files
- `/files/demo_frames/*.jpg`, `/files/crops/*.png`
- `/avatars/{budget,goals,owned,deal}.png` are served by the frontend from `frontend/public/avatars/`. They are optional; the UI falls back to a monogram.
