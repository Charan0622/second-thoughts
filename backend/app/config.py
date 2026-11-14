from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")

DATA = ROOT / "data"
PERSONA = DATA / "persona"
FRAMES = DATA / "demo_frames"
PRIVATE = DATA / "private"          # gitignored: caches, crops, ledger
CROPS = PRIVATE / "crops"
for d in (PRIVATE, CROPS):
    d.mkdir(parents=True, exist_ok=True)

NACE_API_KEY = os.environ.get("NACE_API_KEY", "").strip()
DEEPINFRA_API_KEY = os.environ.get("DEEPINFRA_API_KEY", "").strip()

DREX_URL = "https://console.nace.ai/v1/systemone"
DREX_MODEL = os.environ.get("DREX_MODEL", "drex-max-v1.1")
QWEN_MODEL = os.environ.get("QWEN_MODEL", "Qwen/Qwen3.8-27B")

# Council constants
VETO_THRESHOLD = 0.93
BAND_LOW, BAND_HIGH = 0.35, 0.65
TODAY = "Saturday, November 14, 2026"
