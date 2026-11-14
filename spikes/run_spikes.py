"""Phase 1 risk spikes. Raw responses -> spikes/out/*.json, summary -> stdout.

Run: uv run --project backend python spikes/run_spikes.py [1 2 3 4]
"""

from __future__ import annotations

import asyncio
import base64
import io
import json
import os
import statistics
import sys
import time
from pathlib import Path

import httpx
from dotenv import load_dotenv
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "spikes" / "out"
OUT.mkdir(exist_ok=True)
load_dotenv(ROOT / ".env")
KEY = os.environ["NACE_API_KEY"].strip()
URL = "https://console.nace.ai/v1/systemone"
HDR = {"Authorization": f"Bearer {KEY}", "Content-Type": "application/json", "X-Nace-Client": "second-thoughts/0.1"}


def dump(name: str, obj) -> None:
    (OUT / f"{name}.json").write_text(json.dumps(obj, indent=2, default=str))


def jpeg_data_url(path: Path, max_side: int = 1024) -> str:
    im = Image.open(path).convert("RGB")
    im.thumbnail((max_side, max_side))
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=85)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


BUDGET_STATE = """Agent: Budget You. Today is Sat Nov 14, 2026.
Checking balance: $2,480.00 (bank statement p.1).
Scheduled before next payday: savings transfer $140 on Nov 15; phone $65 on Nov 18; rent $1,850 on Nov 20.
Free cash before payday after scheduled bills: $425.00. Next payday: Nov 27, 2026.
Proposed purchase: {item} for ${price:.2f}."""

QUESTIONS = {
    "regret": {"type": "noul", "instructions": "Will this purchase be regretted or cause a money problem within 30 days?",
               "criteria": {"true": "The purchase leaves too little money for scheduled bills or essentials, or clearly strains the budget",
                            "false": "The purchase fits comfortably within free cash after scheduled bills"}},
    "bill_unpayable": {"type": "noul", "instructions": "If this purchase is made today, will a scheduled bill become unpayable before the next payday?",
                       "criteria": {"true": "Price is greater than free cash before payday",
                                    "false": "Price is less than or equal to free cash before payday"}},
    "stake": {"type": "score", "instructions": "How much does this purchase matter to the budget?",
              "criteria": ["Irrelevant", "Minor", "Noticeable", "Serious", "Critical"]},
    "category": {"type": "choice", "instructions": "What kind of item is being purchased?",
                 "criteria": {"running_gear": "Shoes or apparel for running", "gadget": "Consumer electronics",
                              "computer": "Desktop or laptop computer", "other": None}},
}

ITEMS = [("TrailFlow 5 running shoes", 160.0), ("Sony WH-1000XM6 headphones", 349.0), ("Apple Mac mini M5", 599.0)]


async def drex(client: httpx.AsyncClient, body: dict) -> tuple[dict, float]:
    t = time.perf_counter()
    r = await client.post(URL, headers=HDR, json=body, timeout=30)
    dt = (time.perf_counter() - t) * 1000
    try:
        data = r.json()
    except Exception:
        data = {"raw": r.text}
    if r.status_code != 200:
        data["_http"] = r.status_code
    return data, dt


async def spike1() -> None:
    print("\n=== Spike 1: Drex text (noul + score + choice), drex-v2.0 vs drex-max-v1.1")
    async with httpx.AsyncClient() as c:
        for model in ("drex-v2.0", "drex-max-v1.1"):
            lat, evals = [], []
            for item, price in ITEMS:
                body = {"model": model, "state": BUDGET_STATE.format(item=item, price=price), "questions": QUESTIONS}
                data, dt = await drex(c, body)
                dump(f"s1_{model}_{price:.0f}", data)
                if "_http" in data:
                    print(f"  {model} HTTP {data['_http']}: {json.dumps(data)[:400]}")
                    break
                a = data["answers"]
                lat.append(dt); evals.append(data.get("evaluation_time_ms", 0))
                print(f"  {model:14} ${price:>4.0f}  regret={a['regret']['noul']:.3f}  unpayable={a['bill_unpayable']['noul']:.3f}  "
                      f"stake={a['stake']['score']:.2f}  cat={a['category']['choice']}  rt={dt:.0f}ms eval={data.get('evaluation_time_ms')}ms "
                      f"tok={data['usage']['input_tokens']}")
            # parallel x4 (council round one shape)
            if lat:
                body = {"model": model, "state": BUDGET_STATE.format(item=ITEMS[1][0], price=ITEMS[1][1]), "questions": QUESTIONS}
                t = time.perf_counter()
                res = await asyncio.gather(*[drex(c, body) for _ in range(4)])
                wall = (time.perf_counter() - t) * 1000
                print(f"  {model:14} 4 parallel calls wall={wall:.0f}ms (each: {[round(d) for _, d in res]})  "
                      f"median seq rt={statistics.median(lat):.0f}ms")


async def spike2() -> None:
    print("\n=== Spike 2: Drex Max image -> category (+ try price buckets)")
    async with httpx.AsyncClient() as c:
        for name in ("shoes", "headphones", "macmini"):
            img = ROOT / "data" / "demo_frames" / f"price_tag_{name}.jpg"
            body = {"model": "drex-max-v1.1",
                    "state": "Image 1 shows something the user is about to buy.",
                    "images": [jpeg_data_url(img)],
                    "questions": {
                        "category": {"type": "choice", "instructions": "What item category is shown in Image 1?",
                                     "criteria": {"running_gear": "Running shoes or running apparel", "headphones": "Headphones or earbuds",
                                                  "computer": "Desktop or laptop computer", "other": None}},
                        "price_bucket": {"type": "choice", "instructions": "What price is shown for the item in Image 1?",
                                         "criteria": {"under_100": "Less than $100", "100_199": "$100 to $199.99",
                                                      "200_399": "$200 to $399.99", "400_plus": "$400 or more", "none": "No price visible"}}}}
            data, dt = await drex(c, body)
            dump(f"s2_{name}", data)
            if "_http" in data:
                print(f"  {name}: HTTP {data['_http']}: {json.dumps(data)[:400]}"); continue
            a = data["answers"]
            print(f"  {name:11} category={a['category']['choice']} ({a['category']['confidence']:.2f})  "
                  f"price_bucket={a['price_bucket']['choice']} ({a['price_bucket']['confidence']:.2f})  rt={dt:.0f}ms "
                  f"eval={data.get('evaluation_time_ms')}ms tok={data['usage']}")


async def ndi_extract(client, path: Path, schema: dict, label: str):
    t = time.perf_counter()
    up = await client.documents.upload(path, on_conflict="new_version")
    t_up = time.perf_counter() - t
    job = await client.documents.extract(up.as_source(), schema=schema, wait_seconds=60,
                                         citations={"enabled": True, "include_source_text": True})
    if job.status not in ("succeeded", "failed"):
        job = await client.jobs.wait(job.job_id, timeout=180)
    dt = time.perf_counter() - t
    res = job.model_dump() if hasattr(job, "model_dump") else job.__dict__
    dump(f"ndi_{label}", res)
    return job, t_up, dt


async def spike3() -> None:
    print("\n=== Spike 3: NDI extract on bank statement (console key via nace-sdk)")
    from nace_sdk import AsyncNaceClient
    schema = {"type": "object", "properties": {
        "available_balance": {"type": "number", "description": "Available balance at statement end"},
        "account_last4": {"type": "string", "description": "Last 4 digits of the account number"},
        "scheduled_payments": {"type": "array", "description": "Upcoming scheduled payments", "items": {
            "type": "object", "properties": {"date": {"type": "string"}, "payee": {"type": "string"}, "amount": {"type": "number"}}}},
        "food_delivery_count": {"type": "integer", "description": "Number of DoorDash or UberEats transactions"}},
        "required": ["available_balance", "scheduled_payments"]}
    async with AsyncNaceClient(api_key=KEY) as client:
        try:
            job, t_up, dt = await ndi_extract(client, ROOT / "data/persona/bank_statement.pdf", schema, "bank")
            print(f"  status={job.status} upload={t_up:.1f}s total={dt:.1f}s")
            r = job.result or {}
            print("  data:", json.dumps(r.get("data"), default=str)[:600])
            for f in (r.get("fields") or [])[:3]:
                print("  field:", json.dumps(f, default=str)[:400])
        except Exception as e:  # noqa: BLE001
            print(f"  FAILED: {type(e).__name__}: {str(e)[:500]}")


async def spike4() -> None:
    print("\n=== Spike 4: NDI extract price from a price-tag photo")
    from nace_sdk import AsyncNaceClient
    schema = {"type": "object", "properties": {"product_name": {"type": "string"}, "price": {"type": "number", "description": "Price in USD"}},
              "required": ["price"]}
    async with AsyncNaceClient(api_key=KEY) as client:
        try:
            job, t_up, dt = await ndi_extract(client, ROOT / "data/demo_frames/price_tag_headphones.jpg", schema, "price_tag")
            print(f"  status={job.status} upload={t_up:.1f}s total={dt:.1f}s data={json.dumps((job.result or {}).get('data'))}")
        except Exception as e:  # noqa: BLE001
            print(f"  FAILED: {type(e).__name__}: {str(e)[:500]}")


if __name__ == "__main__":
    which = sys.argv[1:] or ["1", "2", "3", "4"]
    async def main():
        # Drex spikes are fast; run NDI spikes concurrently with them.
        tasks = [globals()[f"spike{w}"]() for w in which]
        for t in tasks:
            await t
    asyncio.run(main())
