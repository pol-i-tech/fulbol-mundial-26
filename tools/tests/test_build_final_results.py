"""Tests for the consolidated final-results file (tools/build_final_results.py)."""
from __future__ import annotations

import csv
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "tools"))

OUT = ROOT / "results" / "wc2026-sim-duckdb"
NEEDED = [OUT / "modal_bracket.json", OUT / "per_game.csv",
          ROOT / "data/wc2026/tournament.json"]


def test_most_likely_score_respects_outcome():
    import build_final_results as mod
    h, a = mod.most_likely_score(1.8, 1.2, "H")
    assert h > a
    h, a = mod.most_likely_score(1.2, 1.8, "A")
    assert h < a
    h, a = mod.most_likely_score(1.5, 1.5, "D")
    assert h == a


@pytest.mark.skipif(not all(p.exists() for p in NEEDED), reason="sim artifacts absent")
def test_generated_file_is_complete_and_consistent():
    import build_final_results as mod
    mod.main()
    rows = list(csv.DictReader(open(OUT / "final_results.csv")))

    assert len(rows) == 103                         # 72 group + 31 knockout
    assert {"stage", "date", "home_team", "away_team", "score", "winner"} == set(rows[0])

    for r in rows:
        assert r["date"], f"missing date: {r}"
        sh, sa = (int(v) for v in r["score"].split("-"))
        expected = r["home_team"] if sh > sa else (r["away_team"] if sa > sh else "Draw")
        assert r["winner"] == expected, f"winner/score mismatch: {r}"

    # Knockouts must be decisive (no draws); groups may draw.
    ko = [r for r in rows if not r["stage"].startswith("Group")]
    assert len(ko) == 31
    assert all(r["winner"] != "Draw" for r in ko)
