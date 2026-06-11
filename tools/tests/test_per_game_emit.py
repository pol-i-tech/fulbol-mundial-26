"""Tests for the per-game probability emitter in simulate_wc2026_duckdb.py.

These exercise the deterministic per-game layer against the live DuckDB ratings.
Skipped automatically if the built database isn't present.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "tools"))

DB = ROOT / "data" / "wc2026.duckdb"

pytestmark = pytest.mark.skipif(
    not DB.exists(), reason="data/wc2026.duckdb not built in this environment"
)


@pytest.fixture(scope="module")
def sim():
    import simulate_wc2026_duckdb as mod
    return mod


@pytest.fixture(scope="module")
def context(sim):
    ratings = sim.load_ratings()
    T = json.loads(sim.TJ.read_text())
    modal = sim.modal_path(T, ratings)
    rows = sim.per_game_rows(T, ratings, modal)
    return ratings, T, modal, rows


def test_all_72_group_fixtures_present(context):
    _, T, _, rows = context
    group_rows = [r for r in rows if r["stage"] == "group"]
    expected = sum(len(g["matches"]) for g in T["groups"])
    assert expected == 72  # 12 groups x 6 matches
    assert len(group_rows) == expected


def test_every_team_code_resolves(context):
    ratings, _, _, rows = context
    for r in rows:
        assert r["home"] in ratings, f"unknown home {r['home']}"
        assert r["away"] in ratings, f"unknown away {r['away']}"


def test_probabilities_normalized(context):
    _, _, _, rows = context
    for r in rows:
        s = r["p_home"] + r["p_draw"] + r["p_away"]
        assert abs(s - 1.0) < 1e-3, f"{r['home']}-{r['away']} sums to {s}"


def test_no_nan_probabilities(context):
    _, _, _, rows = context
    for r in rows:
        for k in ("p_home", "p_draw", "p_away", "lam_home", "lam_away"):
            v = r[k]
            assert v == v, f"NaN in {k} for {r['home']}-{r['away']}"  # NaN != NaN


def test_knockout_matchups_match_modal_bracket(context):
    """R32 matchups in per_game must equal the modal bracket's R32 ties."""
    _, _, modal, rows = context
    pg_r32 = {(r["home"], r["away"]) for r in rows if r["stage"] == "R32"}
    modal_r32 = {(k["t1"], k["t2"]) for k in modal["ko_results"] if k["round"] == "R32"}
    assert pg_r32 == modal_r32


def test_character_fields_populated(context):
    _, _, _, rows = context
    for r in rows:
        assert r["character"], "empty character descriptor"
        assert r["confidence_band"] in {"golden-zone", "2-way-split", "3-way-split"}
        assert r["openness"] in {"open", "balanced", "low-scoring grind"}
        assert r["decisiveness"] in {"comfortable", "competitive", "coin-flip"}
