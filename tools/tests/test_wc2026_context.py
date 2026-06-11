"""Tests for the read-only narrative-context extractors."""
from __future__ import annotations

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
def con():
    from lib.wc2026_context import connect
    c = connect()
    yield c
    c.close()


def test_top_players_sorted_descending(con):
    from lib.wc2026_context import top_players
    players = top_players(con, "ESP", n=3)
    assert 0 < len(players) <= 3
    xgs = [p.xg90 for p in players if p.xg90 is not None]
    assert xgs == sorted(xgs, reverse=True)
    assert all(p.name for p in players)


def test_top_players_unknown_team_returns_empty(con):
    from lib.wc2026_context import top_players
    assert top_players(con, "ZZZ", n=3) == []


def test_team_econ_populated_for_contender(con):
    from lib.wc2026_context import team_econ
    e = team_econ(con, "ARG")
    assert e is not None
    assert e.team_name
    assert e.gdp_per_capita_usd and e.gdp_per_capita_usd > 0
    assert e.population and e.population > 0
    assert e.fifa_rank and e.fifa_rank >= 1


def test_team_econ_unknown_team_returns_none(con):
    from lib.wc2026_context import team_econ
    assert team_econ(con, "ZZZ") is None


def test_extractors_are_read_only(con):
    """A read-only connection must reject writes — proves we can't mutate state."""
    import duckdb
    with pytest.raises(duckdb.Error):
        con.execute("CREATE TABLE curated.__should_fail (x INT)")
