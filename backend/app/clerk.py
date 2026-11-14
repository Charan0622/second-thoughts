"""The Clerk: Intern (Nace harness) run headless. It summarizes the persona at setup and explains split verdicts.

Intern never votes or decides; it writes prose. Every run is logged in the ledger.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import shutil
import time

from . import ledger
from .config import DEEPINFRA_API_KEY, NACE_API_KEY, PRIVATE, ROOT

SUMMARY = PRIVATE / "clerk_summary.md"
CACHE = PRIVATE / "clerk_cache.json"  # explanations keyed by the exact prompt (same votes → same paragraph)
SYSTEM1 = "drex-latest"
SYSTEM2 = "deepinfra/Qwen/Qwen3.8-27B"


QUICK = PRIVATE / "clerk_ws"
QUICK.mkdir(exist_ok=True)


async def run(prompt: str, *, timeout: float = 120.0, note: str = "", quick: bool = False) -> dict:
    exe = shutil.which("intern") or os.path.expanduser("~/.local/bin/intern")
    env = {**os.environ, "NACE_API_KEY": NACE_API_KEY, "DEEPINFRA_API_KEY": DEEPINFRA_API_KEY}
    t = time.perf_counter()
    ok = False
    try:
        args = [exe, "--system1", SYSTEM1, "--system2", SYSTEM2, "-p", "--json"]
        if quick:  # prose only: empty workspace, no repo context, two turns max
            args += ["--cwd", str(QUICK), "--no-context-files", "--max-turns", "2", "--no-session", "--no-memory"]
        proc = await asyncio.create_subprocess_exec(
            *args, "--", prompt,
            cwd=str(QUICK if quick else ROOT), env=env, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        out, err = await asyncio.wait_for(proc.communicate(), timeout)
        text = out.decode(errors="replace")
        ok = proc.returncode == 0
        result = _final_text(text)
        return {"ok": ok, "text": result, "raw": text[-4000:], "stderr": err.decode(errors="replace")[-1000:]}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "text": "", "error": f"{type(e).__name__}: {e}"}
    finally:
        ledger.record("intern", (time.perf_counter() - t) * 1000, ok, note=note)


def _final_text(out: str) -> str:
    """Intern --json emits JSONL events; the answer is the last assistant `message` (fallback: joined text_deltas)."""
    last, deltas = "", []
    for line in out.splitlines():
        try:
            ev = json.loads(line)
        except Exception:  # noqa: BLE001
            continue
        if ev.get("type") == "message" and (ev.get("message") or {}).get("role") == "assistant":
            m = ev["message"]
            txt = m.get("text") or (m.get("content") if isinstance(m.get("content"), str) else "")
            if txt and txt.strip():
                last = txt
        elif ev.get("type") == "text_delta":
            deltas.append(ev.get("text", ""))
    return (last or "".join(deltas)).strip()


async def setup_summary() -> dict:
    prompt = ("Read the files in data/persona (a fictional demo persona: bank statement, pay stub, savings tracker, "
              "receipts). Write a concise facts summary in markdown to data/private/clerk_summary.md with sections: "
              "Money before payday, Goals and rules, Things already owned. Quote exact amounts and dates. "
              "Do not modify any other file.")
    res = await run(prompt, timeout=240, note="setup: persona facts summary")
    return {**res, "summary_exists": SUMMARY.exists()}


async def explain(verdict: dict, votes: list[dict]) -> dict:
    lines = "\n".join(f"- {v['label']}: {v['stance'].upper()} (p_regret {v['p_regret']:.2f}, stake {v['stake']:.1f}) — "
                      f"{v['headline']} [cites: {v['citation'].get('doc_label')}: {v['citation'].get('quote', '')[:120]}]"
                      for v in votes)
    from . import facts as F
    prompt = (f"You are the Clerk of a spending council. The council's verdict on {verdict['item']['name']} "
              f"(${verdict['item']['price']:,.0f}) was '{verdict['title']}'"
              + (f" with condition '{verdict['condition']}'" if verdict.get("condition") else "")
              + f". Votes:\n{lines}\n\nWrite one short paragraph (max 80 words) for {F.persona.first_name} explaining why the selves disagreed "
                "and why the condition resolves it. Only use the facts given. Reply with the paragraph only; do not create files.")
    # Key on what decides the paragraph (item, verdict, condition, each self's stance + headline) — not on the
    # probabilities, which wobble in the 2nd decimal between runs.
    sig = [verdict["item"]["name"], verdict["title"], verdict.get("condition") or ""] + sorted(
        f"{v['agent']}:{v['stance']}:{v['headline']}" for v in votes)
    key = hashlib.sha256("|".join(sig).encode()).hexdigest()[:20]
    cache = json.loads(CACHE.read_text()) if CACHE.exists() else {}
    if key in cache:
        return {"ok": True, "text": cache[key], "cached": True}
    res = await run(prompt, timeout=180, note="explain split verdict", quick=True)
    if res.get("ok") and res.get("text"):
        cache = json.loads(CACHE.read_text()) if CACHE.exists() else {}
        cache[key] = res["text"]
        tmp = CACHE.with_suffix(".tmp")
        tmp.write_text(json.dumps(cache, indent=1))
        os.replace(tmp, CACHE)
    return res
