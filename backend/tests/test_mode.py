"""Persona mode (none | demo | mine): offline. NDI is faked for user uploads; demo docs come from the NDI cache."""

import asyncio
import copy
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # backend/

import httpx
import pytest

from app import facts as F, ndi

STATE = ("persona", "BASE", "mode", "loaded")
DICTS = ("facts", "_slot_docs", "_slot_owner", "_paths", "_results", "_errors", "_doc_labels")


@pytest.fixture
def iso(tmp_path, monkeypatch):
    """Redirect mode.json / my_docs / facts.sqlite to tmp and restore the module state afterwards."""
    saved = {k: getattr(F, k) for k in STATE}
    saved_d = {k: copy.copy(getattr(F, k)) for k in DICTS}
    monkeypatch.setattr(F, "MODE_FILE", tmp_path / "mode.json")
    monkeypatch.setattr(F, "MY_DOCS", tmp_path / "my_docs")
    monkeypatch.setattr(F, "DB", tmp_path / "facts.sqlite")
    (tmp_path / "my_docs").mkdir()

    real = ndi.extract

    async def fake(path, schema, **kw):
        if Path(path).parent.parent == tmp_path / "my_docs":  # a user upload: pretend NDI read only a balance
            return {"data": {"available_balance": 900.0},
                    "fields": [{"path": "/available_balance", "status": "found", "value": 900.0, "citations": []}]}
        return await real(path, schema, **kw)

    monkeypatch.setattr(ndi, "extract", fake)
    yield tmp_path
    for k, v in saved.items():
        setattr(F, k, v)
    for k, v in saved_d.items():
        d = getattr(F, k)
        d.clear()
        d.update(v)


def test_default_mode_is_none(iso):
    assert F.get_mode() == "none"
    F.MODE_FILE.write_text("{not json")
    assert F.get_mode() == "none"
    with pytest.raises(ValueError):
        F.set_mode("maya")


def test_demo_mode_is_maya_and_ignores_uploads(iso):
    (F.MY_DOCS / "bank").mkdir()
    (F.MY_DOCS / "bank" / "mine.txt").write_text("balance 900")
    F.set_mode("demo")
    s = asyncio.run(F.load())
    assert s["mode"] == "demo"
    assert all(v["owner"] == "demo" for v in s["slots"].values())
    p = F.persona
    assert p.name == "Maya Chen" and p.balance == 2480.0 and p.free_cash == 425.0 and p.next_payday == "2026-11-27"
    assert p.goal_name == "Japan trip" and p.flags == []


def test_mine_mode_never_uses_demo_values(iso):
    from datetime import date, timedelta
    (F.MY_DOCS / "bank").mkdir()
    (F.MY_DOCS / "bank" / "statement.pdf").write_bytes(b"%PDF-fake")
    F.set_mode("mine")
    s = asyncio.run(F.load())
    assert s["slots"]["bank"]["owner"] == "yours"
    assert all(s["slots"][k]["owner"] == "missing" for k in ("paystub", "savings", "receipts", "rules"))
    p = F.persona
    assert p.name != "Maya Chen" and p.balance == 900.0 and p.scheduled == [] and p.free_cash == 900.0
    assert p.next_payday == (date.today() + timedelta(days=14)).isoformat()
    assert p.rules == [] and p.owned == [] and not p.owned_item
    assert p.goal_name == "savings goal" and p.japan_target == 0 and not p.has_goal
    assert any("No pay stub uploaded" in f and "payday unknown" in f for f in p.flags)
    assert any("No savings goal yet" in f for f in p.flags)
    texts = " ".join(f.text for f in F.all_facts())
    assert "Maya" not in texts and "Japan" not in texts and "Parkside" not in texts
    assert any(f.status == "missing" and f.agent == "goals" for f in F.all_facts())
    # values the agents divide by stay safe
    assert p.rent["amount"] == 0.0 and p.net_hourly > 0 and p.days_to_payday >= 1


def test_api_mode_flow(iso, monkeypatch):
    from app import main

    async def go():
        t = httpx.ASGITransport(app=main.app, client=("127.0.0.1", 1234))
        async with httpx.AsyncClient(transport=t, base_url="http://test") as c:
            assert (await c.get("/api/mode")).json() == {"mode": "none"}
            r = await c.post("/api/verdict", json={"demo_item": "shoes"})
            ev = [json.loads(x) for x in r.text.splitlines() if x.strip()]
            assert ev[0]["type"] == "error" and "Choose your documents or the demo persona first" in ev[0]["message"]
            assert (await c.post("/api/mode", json={"mode": "bogus"})).status_code == 422
            assert (await c.post("/api/mode", json={"mode": "demo"})).json()["mode"] == "demo"
            assert (await c.get("/api/persona")).json()["name"] == "Maya Chen"
            r = await c.post("/api/docs/rules", files={"files": ("memo.m4a", b"x", "audio/mp4")})
            assert r.status_code == 415                      # audio is no longer accepted
            assert F.get_mode() == "demo"                    # rejected upload changes nothing
            r = await c.post("/api/docs/bank", files={"files": ("statement.pdf", b"%PDF-fake", "application/pdf")})
            assert r.status_code == 200 and r.json()["mode"] == "mine"
            pj = (await c.get("/api/persona")).json()
            assert pj["mode"] == "mine" and pj["japan"]["monthly"] == 0 and pj["has_goal"] is False
            assert (await c.delete("/api/docs")).json()["mode"] == "none"
            led = (await c.get("/api/ledger")).json()
            assert "adobe" not in led["tools"]

    asyncio.run(go())
