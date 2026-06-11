"""Tests for the WC2026 narrative report generator.

Skipped automatically if the built database or simulator artifacts are absent.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "tools"))

DB = ROOT / "data" / "wc2026.duckdb"
OUT = ROOT / "results" / "wc2026-sim-duckdb"
ARTIFACTS = [OUT / "probabilities.csv", OUT / "per_game.csv", OUT / "modal_bracket.json"]

pytestmark = pytest.mark.skipif(
    not DB.exists() or not all(a.exists() for a in ARTIFACTS),
    reason="DB or simulator artifacts not present",
)


@pytest.fixture(scope="module")
def report():
    import build_wc2026_report as mod
    probs, per_game, modal, T = mod.load()
    con = mod.connect()
    try:
        text = "\n\n".join(s.rstrip() for s in [
            mod.headline_section(probs),
            mod.group_section(con, T, per_game, modal),
            mod.knockout_section(per_game, probs),
            mod.final_section(con, per_game, modal, probs),
            mod.limitations_section(con, probs),
            mod.caveats_section(),
        ])
    finally:
        con.close()
    return text, probs, modal, T


def test_all_twelve_groups_present(report):
    text, _, _, T = report
    for g in T["groups"]:
        assert f"### Group {g['id']}" in text


def test_all_knockout_rounds_present(report):
    text, _, _, _ = report
    for title in ("Round of 32", "Round of 16", "Quarter-finals", "Semi-finals", "Final"):
        assert title in text


def test_headline_champion_matches_probabilities_and_modal(report):
    """The named champion must be the probabilities.csv leader AND the modal champion."""
    text, probs, modal, _ = report
    import build_wc2026_report as mod
    top = max(probs.items(), key=lambda kv: kv[1]["p_champion"])[0]
    assert modal["champion"] == top, "modal champion disagrees with MC leader"
    assert f"Model's pick: **{mod.name(top)}**" in text
    assert f"The model's favorite: **{mod.name(top)}**" in text


def test_final_numbers_match_per_game_row(report):
    """The Final section's 1X2 must match the per_game FINAL row."""
    text, _, _, _ = report
    import build_wc2026_report as mod
    fr = next(r for r in mod.load()[1] if r["stage"] == "FINAL")
    assert mod.pct(float(fr["p_home"])) in text
    assert mod.pct(float(fr["p_away"])) in text
    assert mod.name(fr["home"]) in text and mod.name(fr["away"]) in text


def test_limitations_section_present_with_durable_caveats(report):
    """The honesty section must always exist and name the durable caveats.

    The per-team 'under-rated here' callout is data-conditional (it fires only
    when a FIFA-elite team still sits below the contender median — which the 2026
    roster refresh resolved), so it is intentionally NOT asserted here."""
    text, _, _, _ = report
    assert "## Known limitations" in text
    # Durable caveats, independent of the current ratings:
    assert "frozen at their peak" in text          # national-only aging stars
    assert "no recent club data" in text
    assert "structural gap" in text.lower()        # Understat league coverage


def test_report_mentions_seed_and_run_size(report):
    text, _, _, _ = report
    assert "seed 42" in text
    assert "20,000" in text


def test_no_thumb_callout_shows_hunch_numbers(report):
    """The honesty callout must surface the popular contenders' real odds."""
    text, _, _, _ = report
    assert "No thumb on the scale" in text
    assert "Spain" in text and "Netherlands" in text


def test_full_generation_writes_file(tmp_path, monkeypatch, report):
    import build_wc2026_report as mod
    written = {}
    real_write = Path.write_text

    def capture(self, content, *a, **k):
        written["text"] = content
        return real_write(self, content, *a, **k)

    monkeypatch.setattr(Path, "write_text", capture)
    mod.main()
    assert written["text"].startswith("# WC2026")
    assert written["text"].endswith("\n")
