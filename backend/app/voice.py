"""DeepInfra (Qwen) writes ONE natural sentence for the verdict. It never decides anything; template fallback."""

from __future__ import annotations

import re
import time

import httpx

from . import ledger
from .config import DEEPINFRA_API_KEY, QWEN_MODEL

URL = "https://api.deepinfra.com/v1/openai/chat/completions"


def template(verdict: dict, votes: dict) -> str:
    item = verdict["item"]["name"]
    if verdict["veto"]:
        return f"Budget You vetoed the {item}: it would leave rent short — wait until payday."
    if verdict["band"] == "buy":
        return f"All your selves are comfortable — go ahead with the {item}."
    if verdict["band"] == "buy_with_condition":
        return f"You can get the {item}, but only if you {verdict['condition'][0].lower() + verdict['condition'][1:]}."
    return f"Your future selves say wait on the {item}."


async def sentence(verdict: dict, votes: dict) -> dict:
    fallback = template(verdict, votes)
    if not DEEPINFRA_API_KEY:
        return {"type": "sentence", "text": fallback, "source": "template"}
    lines = [f"- {v.label}: {'BUY' if v.stance == 'buy' else 'WAIT'} — {v.headline}" for v in votes.values()]
    from . import facts as F
    n = F.persona.first_name
    prompt = (f"{n} is about to buy {verdict['item']['name']} for ${verdict['item']['price']:,.0f}. "
              f"Her spending council decided: {verdict['title']}"
              + (f" (condition: {verdict['condition']})" if verdict.get("condition") else "")
              + ". Votes:\n" + "\n".join(lines)
              + f"\n\nThere are exactly {len(votes)} selves; if you mention them, use their names exactly as written above. "
                f"The FINAL decision is: {verdict['title']}. Your sentence MUST recommend exactly that final decision (the votes above are the first round, before any compromise). "
                f"Write ONE warm, plain-English sentence (max 30 words) speaking directly to {n} that explains the verdict. "
                "Use only the facts above; do not invent numbers or voices. No preamble, no quotes.")
    t = time.perf_counter()
    ok = False
    try:
        async with httpx.AsyncClient(timeout=6.0) as c:
            r = await c.post(URL, headers={"Authorization": f"Bearer {DEEPINFRA_API_KEY}"}, json={
                "model": QWEN_MODEL, "messages": [{"role": "user", "content": prompt + " /no_think"}],
                "max_tokens": 400, "temperature": 0.4,
                "chat_template_kwargs": {"enable_thinking": False}})
        r.raise_for_status()
        text = r.json()["choices"][0]["message"]["content"] or ""
        text = re.sub(r"<think>.*?</think>", "", text, flags=re.S).strip().strip('"')
        ok = bool(text)
        tokens = r.json().get("usage", {}).get("total_tokens", 0)
        return {"type": "sentence", "text": text if ok else fallback, "source": "deepinfra" if ok else "template"}
    except Exception:  # noqa: BLE001
        tokens = 0
        return {"type": "sentence", "text": fallback, "source": "template"}
    finally:
        ledger.record("deepinfra", (time.perf_counter() - t) * 1000, ok, tokens, note="verdict sentence")
