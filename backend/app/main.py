"""Second Thoughts API. See docs/API.md for the contract."""

from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles

from . import clerk, council, facts as F, ledger
from .agents import deal
from .agents.base import Item
from .config import CROPS, FRAMES

_last: dict = {}


async def _prefetch_deals() -> None:
    for d in council.DEMO_ITEMS.values():
        try:
            await deal.gather(Item(d["name"], d["category"], d["price"]))
        except Exception:  # noqa: BLE001
            pass


@asynccontextmanager
async def lifespan(app: FastAPI):
    ledger.load_history()
    await F.load()                       # NDI extracts, cached by file hash
    asyncio.create_task(_prefetch_deals())  # warm Keenable cache for demo items
    yield


app = FastAPI(title="Second Thoughts", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.mount("/files/demo_frames", StaticFiles(directory=FRAMES), name="frames")
app.mount("/files/crops", StaticFiles(directory=CROPS), name="crops")


@app.get("/api/health")
async def health():
    return {"ok": True, "facts_loaded": F.loaded, "errors": F._errors}


@app.get("/api/demo_items")
async def demo_items():
    return [{"id": k, "name": v["name"], "price": v["price"], "category": v["category"],
             "frame_url": f"/files/demo_frames/{v['frame']}"} for k, v in council.DEMO_ITEMS.items()]


@app.get("/api/persona")
async def persona():
    p = F.persona
    return {"name": p.name, "free_cash": p.free_cash, "balance": p.balance, "next_payday": p.next_payday,
            "hourly": p.hourly, "scheduled": p.scheduled,
            "japan": {"target": p.japan_target, "saved": p.japan_saved, "monthly": p.japan_monthly, "date": p.japan_date},
            "rules": p.rules, "rules_source": p.rules_source,
            "owned": {"item": p.owned_item, "price": p.owned_price, "date": p.owned_date},
            "facts": [{"id": f.id, "agent": f.agent, "text": f.text, "doc_label": f.doc_label, "status": f.status}
                      for f in F.all_facts()]}


@app.get("/api/ledger")
async def get_ledger():
    return ledger.snapshot()


@app.post("/api/ingest")
async def ingest(refresh: bool = False):
    return await F.load(use_cache=not refresh)


@app.post("/api/verdict")
async def verdict(req: dict):
    if not (req.get("demo_item") or req.get("frame")):
        raise HTTPException(422, "send demo_item or frame")

    async def gen():
        votes = []
        try:
            async for ev in council.run(req):
                if ev["type"] == "vote":
                    votes.append(ev)
                if ev["type"] == "verdict":
                    _last.clear()
                    _last.update({"verdict": ev, "votes": votes})
                yield json.dumps(ev) + "\n"
        except Exception as e:  # noqa: BLE001
            yield json.dumps({"type": "error", "message": f"{type(e).__name__}: {str(e)[:300]}"}) + "\n"

    return StreamingResponse(gen(), media_type="application/x-ndjson",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.post("/api/explain")
async def explain():
    """Intern (the Clerk) explains the most recent verdict in one paragraph."""
    if not _last:
        raise HTTPException(404, "no verdict yet")
    return await clerk.explain(_last["verdict"], _last["votes"])


@app.post("/api/clerk/setup")
async def clerk_setup():
    return await clerk.setup_summary()
