"""Offline tests for perception price resolution (manual > NDI > vision > cache, sanity-checked vs Drex bucket)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # backend/

import pytest

from app import council, vision
from app.council import NeedsInput, resolve_price


def V(price, cur="USD", conf=0.95):
    return {"price": price, "currency": cur, "confidence": conf}


def test_manual_always_wins_even_against_bucket():
    assert resolve_price(100.0, V(1.79), V(1.79), "under_5") == (100.0, "manual", None)


def test_ndi_preferred_when_it_agrees():
    assert resolve_price(None, V(1.79), V(1.89), "under_5")[:2] == (1.79, "ndi")


def test_vision_used_when_ndi_unavailable():
    assert resolve_price(None, {}, V(1.79), "under_5")[:2] == (1.79, "vision")


def test_belvita_bug_ndi_misread_loses_to_vision_that_matches_bucket():
    assert resolve_price(None, V(100.0), V(1.79), "under_5")[:2] == (1.79, "vision")


def test_no_source_agrees_asks_user():
    with pytest.raises(NeedsInput, match=r"I read \$100\.00 .*less than \$5.*type the price"):
        resolve_price(None, V(100.0), None, "under_5")


def test_no_bucket_info_falls_back_to_order():
    for b in ("none", "non_usd", None, "garbage"):
        assert resolve_price(None, V(100.0), V(1.79), b)[:2] == (100.0, "ndi")


def test_bucket_slack_tolerates_edges():
    assert resolve_price(None, None, V(5.49), "under_5")[:2] == (5.49, "vision")
    assert resolve_price(None, None, V(44.0), "50_99")[:2] == (44.0, "vision")
    with pytest.raises(NeedsInput):
        resolve_price(None, None, V(12.0), "under_5")


def test_low_confidence_vision_ignored():
    with pytest.raises(NeedsInput, match="couldn't read a price"):
        resolve_price(None, {}, V(1.79, conf=0.1), "under_5")


def test_vision_null_price_means_no_price():
    with pytest.raises(NeedsInput, match="couldn't read a price"):
        resolve_price(None, {}, vision.normalize({"price": None, "confidence": 0.9}), "none")


def test_eur_converted_and_checked_in_usd():
    p, src, note = resolve_price(None, {}, V(139.95, "EUR"), "non_usd")
    assert src == "vision" and p == pytest.approx(139.95 * council.FX_TO_USD["EUR"], abs=0.01)
    assert "EUR" in note


def test_unknown_currency_asks_only_if_nothing_else():
    with pytest.raises(NeedsInput, match="XYZ"):
        resolve_price(None, V(10.0, "XYZ"), None, "5_24")
    assert resolve_price(None, V(10.0, "XYZ"), V(9.99), "5_24")[:2] == (9.99, "vision")


def test_demo_cache_used_last_and_wins_when_reads_disagree_with_bucket():
    assert resolve_price(None, {}, None, "200_399", cache=349.0)[:2] == (349.0, "cache")
    assert resolve_price(None, V(349.0), None, "200_399", cache=349.0)[:2] == (349.0, "ndi")
    assert resolve_price(None, V(3.49), None, "200_399", cache=349.0)[:2] == (349.0, "cache")


def test_every_ranged_bucket_is_a_drex_choice_or_legacy():
    assert set(council.BUCKET_RANGE) - set(council.BUCKETS) <= {"under_25"}


def test_vision_normalize_and_name():
    r = vision.normalize({"product_name": "Crunchy Oats & Honey", "brand": "belVita", "price": "$1.79",
                          "currency": "usd", "was_price": "null", "confidence": "0.9"})
    assert r["price"] == 1.79 and r["currency"] == "USD" and r["was_price"] is None and r["confidence"] == 0.9
    assert vision.display_name(r) == "belVita Crunchy Oats & Honey"
    assert vision.display_name({"brand": "Sony", "product_name": "Sony WH-1000XM6"}) == "Sony WH-1000XM6"
    assert vision.normalize({"price": "89,95", "currency": "EUR"})["price"] == 89.95
    assert vision.normalize({"price": 0})["price"] is None
