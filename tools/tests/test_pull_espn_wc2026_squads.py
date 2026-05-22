"""Tests for tools/pull_espn_wc2026_squads.py.

Integration tests parse the real cached HTML at
data/raw/squads/espn/2026-05-22/page.html. Unit tests use small synthetic
fixtures to cover edge cases (not-yet-announced, missing club, dup IDs,
plain-text players without anchors).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "tools"))

from pull_espn_wc2026_squads import (  # noqa: E402
    _find_announced_in_text,
    _find_manager_in_text,
    _parse_player_list,
    main,
    parse_squads,
)

FIXTURE_HTML = ROOT / "data" / "raw" / "squads" / "espn" / "2026-05-22" / "page.html"


# ---------- announce / manager parsing ----------

@pytest.mark.parametrize(
    "text, expected",
    [
        ("Final squad was announced May 18", ("May 18", "final")),
        ("Roster announced on May 21", ("May 21", "final")),
        ("Roster announced May 19", ("May 19", "final")),
        ("Preliminary squad was announced May 12", ("May 12", "preliminary")),
        ("Preliminary roster announced on May 11", ("May 11", "preliminary")),
        ("Provisional toster announced on May 21", ("May 21", "preliminary")),  # ESPN typo
        ("Roster yet to be announced", (None, None)),
        ("", (None, None)),
    ],
)
def test_find_announced_in_text(text, expected):
    assert _find_announced_in_text(text) == expected


def test_find_manager_in_text():
    assert _find_manager_in_text("Manager: Javier Aguirre") == "Javier Aguirre"
    assert _find_manager_in_text("foo Manager: Hugo Broos\n") == "Hugo Broos"
    assert _find_manager_in_text("no coach listed") is None


# ---------- player list parsing ----------

def test_parse_player_list_simple_pairs():
    text = "Alisson (Liverpool), Ederson (Fenerbahce), Weverton (Gremio)"
    rows = _parse_player_list(text, {}, "GK")
    assert [r["name"] for r in rows] == ["Alisson", "Ederson", "Weverton"]
    assert [r["club"] for r in rows] == ["Liverpool", "Fenerbahce", "Gremio"]
    assert all(r["espn_player_id"] is None for r in rows)
    assert all(r["position_bucket"] == "GK" for r in rows)


def test_parse_player_list_fills_espn_id_from_anchor_map():
    text = "Alisson (Liverpool), Ederson (Fenerbahce)"
    rows = _parse_player_list(text, {"Alisson": "12345"}, "GK")
    assert rows[0]["espn_player_id"] == "12345"
    assert rows[1]["espn_player_id"] is None


def test_parse_player_list_handles_club_with_comma():
    # Some clubs ESPN renders inline could conceivably contain commas;
    # the parser must split on top-level commas only.
    text = "Player A (Foo, Inc.), Player B (Bar)"
    rows = _parse_player_list(text, {}, "MF")
    assert [r["name"] for r in rows] == ["Player A", "Player B"]
    assert [r["club"] for r in rows] == ["Foo, Inc.", "Bar"]


def test_parse_player_list_player_without_club():
    text = "Lone Wolf, Pair Mate (Real Club)"
    rows = _parse_player_list(text, {}, "FW")
    assert rows[0]["name"] == "Lone Wolf"
    assert rows[0]["club"] is None
    assert rows[1]["club"] == "Real Club"


# ---------- synthetic HTML parse ----------

SYNTHETIC_HTML = """
<html><body><div class="article-body">
<h2>GROUP A</h2>
<h2>Mexico</h2>
<p><em>Final squad was announced May 18</em></p>
<p><strong>Goalkeepers</strong>: <a href="http://espn.com/soccer/player/_/id/100/x">Alpha</a> (Club A), Beta (Club B)</p>
<p><strong>Defenders</strong>: Gamma (Club C)</p>
<p><strong>Midfielders</strong>: Delta (Club D)</p>
<p><strong>Forwards</strong>: Epsilon (Club E)</p>
<p>Manager: Coach One</p>
<h2>South Africa</h2>
<p>Roster yet to be announced</p>
<p><strong>Goalkeepers</strong>:</p>
<p><strong>Defenders</strong>:</p>
<p><strong>Midfielders</strong>:</p>
<p><strong>Forwards</strong>:</p>
<p>Manager: Coach Two</p>
<h2>GROUP B</h2>
<h2>Brazil</h2>
<p><em>Final squad was announced May 18</em></p>
<p><strong>Goalkeepers</strong>: <a href="http://espn.com/soccer/player/_/id/200/y">Zeta</a> (Club F)</p>
<p>Manager: Coach Three</p>
</div></body></html>
"""


def test_parse_squads_synthetic_basic():
    teams = parse_squads(SYNTHETIC_HTML)
    nations = [t["nation"] for t in teams]
    assert nations == ["Mexico", "Brazil"]  # South Africa skipped (not announced)
    mex = teams[0]
    assert mex["group"] == "GROUP A"
    assert mex["announced_date"] == "May 18"
    assert mex["announce_type"] == "final"
    assert mex["manager"] == "Coach One"
    assert len(mex["players"]) == 5
    assert mex["players"][0] == {
        "espn_player_id": "100",
        "name": "Alpha",
        "position_bucket": "GK",
        "club": "Club A",
    }
    assert mex["players"][1]["espn_player_id"] is None  # plain-text player


def test_parse_squads_skips_not_yet_announced():
    teams = parse_squads(SYNTHETIC_HTML)
    assert "South Africa" not in [t["nation"] for t in teams]


def test_parse_squads_dedups_within_team_by_espn_id():
    html = """
    <div class="article-body">
    <h2>GROUP A</h2>
    <h2>Test</h2>
    <p><em>Final squad was announced May 1</em></p>
    <p><strong>Forwards</strong>:
      <a href="http://espn.com/soccer/player/_/id/55/a">Twin</a> (Club A),
      <a href="http://espn.com/soccer/player/_/id/55/a">Twin</a> (Club A)
    </p>
    </div>
    """
    teams = parse_squads(html)
    assert len(teams) == 1
    assert len(teams[0]["players"]) == 1


def test_parse_squads_manager_line_not_extracted_as_player():
    """Regression: 'Manager: X' must not appear as a forward."""
    teams = parse_squads(SYNTHETIC_HTML)
    mex = teams[0]
    fws = [p for p in mex["players"] if p["position_bucket"] == "FW"]
    assert len(fws) == 1
    assert fws[0]["name"] == "Epsilon"


def test_parse_squads_team_anchors_not_misidentified_as_players():
    """Regression: <a href='/soccer/team/_/id/N'> is NOT a player."""
    html = """
    <div class="article-body">
    <h2>GROUP A</h2>
    <h2>Test</h2>
    <p><em>Final squad was announced May 1</em></p>
    <p><strong>Forwards</strong>:
      <a href="http://espn.com/soccer/player/_/id/1/p">Real Player</a>
      (<a href="/soccer/team/_/id/999">Big Club</a>)
    </p>
    </div>
    """
    teams = parse_squads(html)
    assert len(teams[0]["players"]) == 1
    assert teams[0]["players"][0]["espn_player_id"] == "1"
    assert teams[0]["players"][0]["club"] == "Big Club"


# ---------- integration: real cached HTML ----------

@pytest.mark.skipif(not FIXTURE_HTML.exists(), reason="cached ESPN HTML fixture not present")
def test_integration_real_html_smoke():
    html = FIXTURE_HTML.read_text(encoding="utf-8")
    teams = parse_squads(html)

    assert len(teams) >= 17, "expected at least 17 announced teams (May 21 baseline)"
    finals = [t for t in teams if t["announce_type"] == "final"]
    assert len(finals) >= 17, "expected at least 17 final squads"
    # FIFA caps rosters at 26, but ESPN's listing is occasionally off-by-one
    # (Germany 25 due to a duplicate Elias Saad; Portugal 27 due to an extra
    # GK). The raw scraper captures what's published; downstream cleaning
    # decides whether to reconcile. Tolerate 25-27 here; require the strong
    # majority to be exactly 26.
    for t in finals:
        n = len(t["players"])
        assert 25 <= n <= 27, f"{t['nation']} expected ~26-man final squad, got {n}"
    exact_26 = sum(1 for t in finals if len(t["players"]) == 26)
    assert exact_26 >= len(finals) - 2, (
        f"only {exact_26}/{len(finals)} finals are exactly 26"
    )


@pytest.mark.skipif(not FIXTURE_HTML.exists(), reason="cached ESPN HTML fixture not present")
def test_integration_real_html_groups_covered():
    html = FIXTURE_HTML.read_text(encoding="utf-8")
    teams = parse_squads(html)
    groups = {t["group"] for t in teams}
    # ESPN article spans GROUP A..L; at least most groups must have ≥1 team
    expected = {f"GROUP {c}" for c in "ABCDEFGHIJKL"}
    assert len(groups & expected) >= 9, f"only saw groups: {sorted(groups)}"


@pytest.mark.skipif(not FIXTURE_HTML.exists(), reason="cached ESPN HTML fixture not present")
def test_integration_real_html_known_player_id():
    """Carlos Acevedo (Mexico GK) carries ESPN player id 236368."""
    html = FIXTURE_HTML.read_text(encoding="utf-8")
    teams = parse_squads(html)
    mex = next(t for t in teams if t["nation"] == "Mexico")
    acevedo = next(p for p in mex["players"] if p["name"] == "Carlos Acevedo")
    assert acevedo["espn_player_id"] == "236368"
    assert acevedo["club"] == "Santos Laguna"
    assert acevedo["position_bucket"] == "GK"


# ---------- CLI / output shape ----------

def test_main_writes_expected_json_shape(tmp_path, monkeypatch):
    """End-to-end: monkeypatch the cache + URL fetch to use SYNTHETIC_HTML."""
    import pull_espn_wc2026_squads as mod

    monkeypatch.setattr(mod, "BASE_DIR", tmp_path)
    monkeypatch.setattr(mod, "fetch_html", lambda out_dir: (
        out_dir.mkdir(parents=True, exist_ok=True),
        (out_dir / "page.html").write_text(SYNTHETIC_HTML),
        SYNTHETIC_HTML,
    )[-1])

    rc = main(["--date", "2026-05-22"])
    assert rc == 0

    out = tmp_path / "2026-05-22" / "wc2026_squads.json"
    assert out.exists()
    payload = json.loads(out.read_text())
    assert payload["as_of_date"] == "2026-05-22"
    assert "source_url" in payload
    assert {t["nation"] for t in payload["teams"]} == {"Mexico", "Brazil"}


def test_main_bad_date_returns_2(tmp_path, monkeypatch):
    import pull_espn_wc2026_squads as mod
    monkeypatch.setattr(mod, "BASE_DIR", tmp_path)
    assert main(["--date", "not-a-date"]) == 2


def test_main_empty_html_returns_1(tmp_path, monkeypatch):
    import pull_espn_wc2026_squads as mod
    monkeypatch.setattr(mod, "BASE_DIR", tmp_path)
    monkeypatch.setattr(mod, "fetch_html", lambda out_dir: "")  # no headings
    assert main(["--date", "2026-05-22"]) == 1


def test_main_parser_finds_zero_teams_returns_1(tmp_path, monkeypatch):
    """HTML with headings but no recognized group/team structure → exit 1."""
    import pull_espn_wc2026_squads as mod
    monkeypatch.setattr(mod, "BASE_DIR", tmp_path)
    monkeypatch.setattr(
        mod,
        "fetch_html",
        lambda out_dir: "<html><body><h1>Lorem</h1><p>ipsum</p></body></html>",
    )
    assert main(["--date", "2026-05-22"]) == 1
