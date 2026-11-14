"""Offline unit tests for the council math (logit/pool/band) and the trade-off offer set.

No network: the default in-memory Persona is used and no agent/Drex calls are made.
"""

import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # backend/

import pytest

from app import council, tradeoffs, facts  # noqa: F401  (facts import pins F.persona to the default)
from app.agents.base import Item


# ---------------------------------------------------------------- logit / pool
def test_equal_probabilities_pool_to_same_probability():
    ps = {"a": 0.3, "b": 0.3, "c": 0.3, "d": 0.3}
    assert council.pool(ps, {a: 1.0 for a in ps}) == pytest.approx(0.3, abs=1e-9)


def test_equal_probabilities_pool_to_same_probability_regardless_of_weights():
    ps = {"a": 0.42, "b": 0.42, "c": 0.42}
    assert council.pool(ps, {"a": 0.5, "b": 7.0, "c": 10.0}) == pytest.approx(0.42, abs=1e-9)


def test_higher_stake_pulls_pool_toward_its_own_p():
    ps = {"cautious": 0.2, "alarmed": 0.9}
    equal = council.pool(ps, {"cautious": 1.0, "alarmed": 1.0})
    # 0.5 is where the pooled value would sit on the probability scale under
    # symmetric logit pulls; the pool with equal stakes is already past the
    # simple arithmetic midpoint toward 0.9, which anchors the comparison.
    assert 0.5 < equal < 0.9
    weighted = council.pool(ps, {"cautious": 1.0, "alarmed": 10.0})
    assert weighted > equal            # higher-stake 0.9 voter pulls the pool up
    assert weighted < 0.9              # ...but never past the voter's own p
    assert abs(weighted - 0.9) < abs(equal - 0.9)


def test_single_voter_pool_is_its_own_p():
    assert council.pool({"a": 0.71}, {"a": 3.0}) == pytest.approx(0.71, abs=1e-9)


def test_logit_is_monotone_and_invertible():
    lo, hi = council.logit(0.2), council.logit(0.8)
    assert lo < 0 < hi
    assert 1 / (1 + math.exp(-lo)) == pytest.approx(0.2, abs=1e-6)


# ---------------------------------------------------------------- band
def test_band_low():
    assert council.band(0.2) == "buy"


def test_band_mid():
    assert council.band(0.5) == "buy_with_condition"


def test_band_high():
    assert council.band(0.8) == "wait"


def test_band_boundaries_behave_as_documented():
    # Bands are documented as: < 0.35 Buy, 0.35-0.65 Buy with condition, > 0.65 Wait.
    # So the boundaries themselves fall in the middle band.
    assert council.band(0.35) == "buy_with_condition"
    assert council.band(0.65) == "buy_with_condition"
    assert council.band(0.35 - 1e-9) == "buy"
    assert council.band(0.65 + 1e-9) == "wait"


# ---------------------------------------------------------------- tradeoffs
def test_headphones_offer_ids_include_resell_and_topup():
    item = Item("Sony WH-1000XM6 Headphones", "headphones", 349.0)
    ids = [o.id for o in tradeoffs.offers(item)]
    assert "resell_and_topup" in ids
    # A 349 headphones buy also breaks the $200 rule, so the rule-specific
    # offers survive as well.
    assert "top_up_japan" in ids
    assert "resell_earbuds" in ids


def test_running_gear_drops_resell_and_topup_offers():
    item = Item("ASICS Gel-Nimbus 27 Running Shoes", "running_gear", 160.0)
    ids = [o.id for o in tradeoffs.offers(item)]
    assert "resell_earbuds" not in ids
    assert "top_up_japan" not in ids
    assert "resell_and_topup" not in ids
    # The generic offers still make it through, in fixed order.
    assert ids[:3] == ["wait_payday", "skip_takeout_2", "skip_takeout_4"]


def test_offer_ids_are_stable_and_unique():
    item = Item("Sony WH-1000XM6 Headphones", "headphones", 349.0)
    ids = [o.id for o in tradeoffs.offers(item)]
    assert len(ids) == len(set(ids))
    assert ids == [o.id for o in tradeoffs.offers(item)]  # fixed order, re-call stable
