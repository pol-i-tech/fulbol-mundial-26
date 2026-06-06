"""Tests for the match-character classifier (tools/lib/match_character.py)."""
from tools.lib.match_character import (
    classify_match,
    COMFORTABLE_MARGIN,
    COMPETITIVE_MARGIN,
)


def test_clear_favorite_open_game():
    # pH=0.70 vs pA=0.18, high expected goals (3.2 total), all models pick home.
    c = classify_match(0.70, 0.12, 0.18, 2.4, 0.8, ("H", "H", "H"))
    assert c.favorite == "home"
    assert c.decisiveness == "comfortable"
    assert c.openness == "open"
    assert c.confidence_band == "golden-zone"


def test_three_way_split_is_coin_flip_penalties():
    # Near-even 1X2, each model picks a different outcome, knockout context.
    c = classify_match(0.34, 0.33, 0.33, 1.0, 1.0, ("H", "D", "A"), knockout=True)
    assert c.confidence_band == "3-way-split"
    assert c.decisiveness == "coin-flip"
    assert "penalties" in c.descriptor


def test_low_scoring_tight_competitive():
    # Modest home lean, low expected goals → grind, competitive.
    c = classify_match(0.45, 0.15, 0.40, 0.7, 0.6, ("H", "D", "H"))
    assert c.openness == "low-scoring grind"
    assert c.decisiveness == "competitive"
    assert c.confidence_band == "2-way-split"


def test_golden_zone_at_modest_confidence():
    # All three models agree even though confidence is only ~0.52.
    c = classify_match(0.52, 0.20, 0.28, 1.5, 1.1, ("H", "H", "H"))
    assert c.confidence_band == "golden-zone"
    assert c.favorite == "home"


def test_even_favorite_when_gap_below_deadband():
    # Win probs within the even dead-band → favorite reported as 'even'.
    c = classify_match(0.40, 0.21, 0.39, 1.3, 1.2, ("H", "D", "A"))
    assert c.favorite == "even"


def test_margin_threshold_boundaries_are_deterministic():
    # Exactly on COMFORTABLE_MARGIN → comfortable (>= boundary).
    pa = 0.20
    ph = pa + COMFORTABLE_MARGIN
    c = classify_match(ph, 1 - ph - pa, pa, 1.5, 1.2, ("H", "H", "A"))
    assert c.decisiveness == "comfortable"

    # Exactly on COMPETITIVE_MARGIN → competitive (>= boundary), not coin-flip.
    ph2 = pa + COMPETITIVE_MARGIN
    c2 = classify_match(ph2, 1 - ph2 - pa, pa, 1.5, 1.2, ("H", "H", "A"))
    assert c2.decisiveness == "competitive"


def test_knockout_wording_differs_from_group():
    picks = ("H", "D", "A")
    ko = classify_match(0.34, 0.33, 0.33, 1.0, 1.0, picks, knockout=True)
    grp = classify_match(0.34, 0.33, 0.33, 1.0, 1.0, picks, knockout=False)
    assert "penalties" in ko.descriptor
    assert "penalties" not in grp.descriptor
    assert "level" in grp.descriptor
