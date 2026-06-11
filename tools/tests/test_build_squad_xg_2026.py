"""Tests for the 2026-roster attack-rating recompute (tools/build_squad_xg_2026.py)."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "tools"))

DB = ROOT / "data" / "wc2026.duckdb"


def _grp(blends, clubs):
    """Synthetic per-player frame with the columns team_aggregate needs."""
    n = len(blends)
    return pd.DataFrame({
        "blended_xg90": blends,
        "nat_xg_per_90": [0.3] * n,
        "club_xg_per_90": clubs,
        "nat_key_passes_per_90": [0.5] * n,
        "nat_prog_passes_per_90": [1.0] * n,
        "nat_pressures_per_90": [10.0] * n,
        "nat_minutes": [300] * n,
        "found": [c is not None and not np.isnan(c) for c in clubs],
    })


def test_attack_rating_is_mean_of_top5_blended():
    import build_squad_xg_2026 as mod
    grp = _grp([0.9, 0.8, 0.7, 0.6, 0.5, 0.1], [0.9, 0.8, 0.7, 0.6, 0.5, 0.1])
    agg = mod.team_aggregate("Testland", grp)
    # top-5 = 0.9..0.5 → mean 0.7; the 0.1 is excluded.
    assert agg["attack_rating"] == pytest.approx(0.70, abs=1e-6)
    assert agg["squad_players"] == 6
    assert agg["matched_to_club"] == 6


def test_club_only_none_when_no_club_matches():
    import build_squad_xg_2026 as mod
    grp = _grp([0.4, 0.3, 0.3, 0.2, 0.2], [np.nan] * 5)
    agg = mod.team_aggregate("Testland", grp)
    assert agg["matched_to_club"] == 0
    assert agg["attack_club_only"] is None       # no crash on all-NaN club xG
    assert agg["attack_rating"] == pytest.approx(0.28, abs=1e-6)


@pytest.mark.skipif(not DB.exists(), reason="DB not present")
def test_label_maps_cover_all_qualifiers():
    import build_squad_xg_2026 as mod
    team_old = pd.read_parquet(ROOT / "data/derived/team_attack_ratings.parquet")
    qual, code2sblabels, code2label = mod.load_label_maps(team_old)
    assert len(qual) == 48                         # full WC2026 field
    # every qualifier resolves to an output label build_duckdb can join on
    assert all(code2label.get(c) for c in qual)


@pytest.mark.skipif(not DB.exists(), reason="DB not present")
def test_recompute_covers_all_qualifiers_on_one_scale():
    """Engine input must carry one consistent scale across the full field."""
    import build_squad_xg_2026 as mod
    team_old = pd.read_parquet(ROOT / "data/derived/team_attack_ratings.parquet")
    qual, _, code2label = mod.load_label_maps(team_old)
    labels = set(team_old["nation"])
    covered = sum(1 for c in qual if code2label.get(c) in labels)
    assert covered == 48                           # no qualifier left on median fallback
