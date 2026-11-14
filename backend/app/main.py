"""Second Thoughts API. See docs/API.md for the contract."""

from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager

import shutil
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
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
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
                   allow_methods=["*"], allow_headers=["*"])


def _local_only(request: Request) -> None:
    if (request.client.host if request.client else "") not in ("127.0.0.1", "::1", "localhost"):
        raise HTTPException(403, "admin endpoint: localhost only")
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
            "rules": p.rules, "rules_source": p.rules_source, "goal_name": p.goal_name, "goal_short": p.goal_short,
            "flags": p.flags, "sources": {k: v["owner"] for k, v in F.summary()["slots"].items()},
            "owned": {"item": p.owned_item, "price": p.owned_price, "date": p.owned_date},
            "facts": [{"id": f.id, "agent": f.agent, "text": f.text, "doc_label": f.doc_label, "status": f.status}
                      for f in F.all_facts()]}


@app.get("/api/ledger")
async def get_ledger():
    return ledger.snapshot()


@app.post("/api/ingest")
async def ingest(request: Request, refresh: bool = False):
    _local_only(request)
    return await F.load(use_cache=not refresh)


# ---------------------------------------------------------------- your documents
ALLOWED = {".pdf", ".jpg", ".jpeg", ".png", ".webp", ".heic", ".xlsx", ".xls", ".csv", ".eml", ".txt", ".docx", ".m4a", ".mp3", ".wav"}
_docs_lock = asyncio.Lock()


@app.get("/api/docs")
async def docs_status():
    return F.summary()


@app.post("/api/docs/{slot}")
async def upload_doc(slot: str, files: list[UploadFile] = File(...)):
    """Replace one slot (bank | paystub | savings | receipts | rules) with your file(s); NDI extracts them now."""
    if slot not in F.DEMO_DOCS:
        raise HTTPException(404, f"unknown slot '{slot}'")
    d = F.MY_DOCS / slot
    async with _docs_lock:
        shutil.rmtree(d, ignore_errors=True)
        d.mkdir(parents=True, exist_ok=True)
        for i, f in enumerate(files[:5]):
            name = Path(f.filename or f"upload_{i}").name
            ext = Path(name).suffix.lower()
            if ext not in ALLOWED:
                raise HTTPException(415, f"{name}: unsupported file type {ext}")
            data = await f.read()
            if len(data) > 20 * 1024 * 1024:
                raise HTTPException(413, f"{name}: larger than 20 MB")
            safe = "".join(c if c.isalnum() or c in "._-" else "_" for c in name)[:80] or f"upload_{i}{ext}"
            (d / safe).write_bytes(data)
        return await F.load()


@app.delete("/api/docs")
async def reset_docs(slot: str | None = None):
    """Back to the demo persona (all slots, or one)."""
    async with _docs_lock:
        if slot:
            shutil.rmtree(F.MY_DOCS / slot, ignore_errors=True)
        else:
            shutil.rmtree(F.MY_DOCS, ignore_errors=True)
            F.MY_DOCS.mkdir(exist_ok=True)
        return await F.load()


@app.post("/api/verdict")
async def verdict(req: dict):
    if not (req.get("demo_item") or req.get("frame")):
        raise HTTPException(422, "send demo_item or frame")
    if req.get("price") is not None:
        try:
            pr = float(req["price"])
        except (TypeError, ValueError):
            raise HTTPException(422, "price must be a number") from None
        if not (0 < pr < 1_000_000):
            raise HTTPException(422, "price must be between $0 and $1,000,000")

    async def gen():
        votes = []
        try:
            async for ev in council.run(req):
                if ev["type"] == "vote":
                    votes.append(ev)
                if ev["type"] == "verdict":
                    _last.clear()
                    _last.update({"verdict": ev, "votes": votes})
                    if ev["band"] == "buy_with_condition" or ev.get("tally", {}).get("wait", 0) not in (0, len(votes)):
                        _last["task"] = asyncio.create_task(clerk.explain(ev, votes))
                yield json.dumps({k: v for k, v in ev.items() if not k.startswith("_")}) + "\n"
        except Exception as e:  # noqa: BLE001
            yield json.dumps({"type": "error", "message": f"{type(e).__name__}: {str(e)[:300]}"}) + "\n"

    return StreamingResponse(gen(), media_type="application/x-ndjson",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.post("/api/explain")
async def explain():
    """Intern (the Clerk) explains the most recent verdict in one paragraph."""
    if not _last:
        raise HTTPException(404, "no verdict yet")
    task = _last.get("task")
    if task is None or (task.done() and not task.cancelled() and not (task.result() or {}).get("ok")):
        task = asyncio.create_task(clerk.explain(_last["verdict"], _last["votes"]))
    _last["task"] = task
    try:
        return await asyncio.wait_for(asyncio.shield(task), 80)
    except asyncio.TimeoutError:
        return {"ok": False, "text": "The Clerk (Intern) is still writing — try again in a moment."}


@app.post("/api/clerk/setup")
async def clerk_setup(request: Request):
    _local_only(request)
    return await clerk.setup_summary()

from . import phone  # noqa: E402
app.include_router(phone.router)
