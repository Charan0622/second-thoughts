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


TUNNEL_HEADERS = ("cf-connecting-ip", "cf-ray", "x-forwarded-for", "x-forwarded-host")
PHONE_ONLY = ("/phone", "/api/phone/frame")


def _via_tunnel(request: Request) -> bool:
    return any(h in request.headers for h in TUNNEL_HEADERS)


def _local_only(request: Request) -> None:
    if _via_tunnel(request) or (request.client.host if request.client else "") not in ("127.0.0.1", "::1", "localhost"):
        raise HTTPException(403, "admin endpoint: localhost only")


@app.middleware("http")
async def tunnel_guard(request: Request, call_next):
    """Through the public phone tunnel, ONLY the phone page and photo upload are reachable — never documents,
    persona data, crops or anything that spends API credit."""
    if _via_tunnel(request) and request.url.path not in PHONE_ONLY:
        from fastapi.responses import JSONResponse
        return JSONResponse({"detail": "not available through the phone link"}, status_code=403)
    return await call_next(request)
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
    mode = F.get_mode()
    return {"mode": mode, "name": p.name or "You", "free_cash": p.free_cash, "balance": p.balance, "next_payday": p.next_payday,
            "hourly": p.hourly, "scheduled": p.scheduled,
            "japan": {"target": p.japan_target, "saved": p.japan_saved, "monthly": p.japan_monthly if p.has_goal else 0,
                      "date": p.japan_date},
            "has_goal": p.has_goal and p.japan_target > 0,
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
ALLOWED = {".pdf", ".jpg", ".jpeg", ".png", ".webp", ".heic", ".xlsx", ".xls", ".csv", ".eml", ".txt", ".docx"}
_docs_lock = asyncio.Lock()


@app.get("/api/docs")
async def docs_status():
    return F.summary()


@app.get("/api/mode")
async def get_mode():
    return {"mode": F.get_mode()}


@app.post("/api/mode")
async def set_mode(req: dict):
    """Pick whose documents the council uses: "demo" (Maya), "mine" (your uploads only) or "none" (onboarding)."""
    mode = req.get("mode")
    if mode not in F.MODES:
        raise HTTPException(422, f"mode must be one of {list(F.MODES)}")
    async with _docs_lock:
        F.set_mode(mode)
        return await F.load()


@app.post("/api/docs/{slot}")
async def upload_doc(slot: str, files: list[UploadFile] = File(...)):
    """Replace one slot (bank | paystub | savings | receipts | rules) with your file(s); NDI extracts them now."""
    if slot not in F.DEMO_DOCS:
        raise HTTPException(404, f"unknown slot '{slot}'")
    d = F.MY_DOCS / slot
    blobs = []
    for i, f in enumerate(files[:5]):  # validate everything before touching the slot
        name = Path(f.filename or f"upload_{i}").name
        ext = Path(name).suffix.lower()
        if ext not in ALLOWED:
            raise HTTPException(415, f"{name}: unsupported file type {ext}")
        data = await f.read()
        if len(data) > 20 * 1024 * 1024:
            raise HTTPException(413, f"{name}: larger than 20 MB")
        safe = "".join(c if c.isalnum() or c in "._-" else "_" for c in name)[:80] or f"upload_{i}{ext}"
        blobs.append((safe, data))
    async with _docs_lock:
        shutil.rmtree(d, ignore_errors=True)
        d.mkdir(parents=True, exist_ok=True)
        for safe, data in blobs:
            (d / safe).write_bytes(data)
        F.set_mode("mine")          # any upload switches to "your documents only"
        return await F.load()


@app.delete("/api/docs")
async def reset_docs(slot: str | None = None):
    """Remove one slot's uploads (mode stays), or all of them (mode → "none": back to onboarding)."""
    async with _docs_lock:
        if slot:
            shutil.rmtree(F.MY_DOCS / slot, ignore_errors=True)
        else:
            shutil.rmtree(F.MY_DOCS, ignore_errors=True)
            F.MY_DOCS.mkdir(exist_ok=True)
            F.set_mode("none")
        return await F.load()


NO_MODE_MSG = "Choose your documents or the demo persona first"


@app.post("/api/verdict")
async def verdict(req: dict):
    if F.get_mode() == "none":
        msg = json.dumps({"type": "error", "message": NO_MODE_MSG, "needs_input": True}) + "\n"
        return StreamingResponse(iter([msg]), media_type="application/x-ndjson")
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
