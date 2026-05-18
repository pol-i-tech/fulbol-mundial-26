"""DuckDB-layer tests for the country-context facts and the dim_team_current view.

Asserts the invariants enforced by the build / verify pipeline directly via
SQL, so a developer can run pytest as a confidence check without parsing
verify_duckdb.py output.
"""
from __future__ import annotations

from pathlib import Path

import duckdb
import pytest

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "data" / "wc2026.duckdb"


@pytest.fixture(scope="module")
def con() -> duckdb.DuckDBPyConnection:
    if not DB_PATH.exists():
        pytest.skip(f"{DB_PATH} not built yet; run tools/build_duckdb.py")
    c = duckdb.connect(str(DB_PATH), read_only=True)
    yield c
    c.close()


# ---------- table presence ----------


def test_tables_exist(con: duckdb.DuckDBPyConnection) -> None:
    expected = {
        ("raw", "country_gdp_per_capita"),
        ("raw", "country_population"),
        ("raw", "fifa_world_ranking_current"),
        ("curated", "fact_team_economics"),
        ("curated", "fact_team_fifa_ranking"),
        ("curated", "dim_team_current"),
        ("quarantine", "unmatched_team_economics"),
        ("quarantine", "unmatched_team_fifa_ranking"),
    }
    rows = set(
        con.sql(
            "SELECT table_schema, table_name FROM information_schema.tables "
            "WHERE table_schema IN ('raw', 'curated', 'quarantine')"
        ).fetchall()
    )
    missing = expected - rows
    assert not missing, f"missing tables: {missing}"


# ---------- R10: no duplicate keys ----------


def test_fact_team_economics_pk_unique(con: duckdb.DuckDBPyConnection) -> None:
    n = con.sql(
        "SELECT COUNT(*) FROM (SELECT team_code, year, COUNT(*) AS n "
        "FROM curated.fact_team_economics GROUP BY 1, 2 HAVING n > 1)"
    ).fetchone()[0]
    assert n == 0, f"duplicate (team_code, year) keys in fact_team_economics: {n}"


def test_fact_team_fifa_ranking_pk_unique(con: duckdb.DuckDBPyConnection) -> None:
    n = con.sql(
        "SELECT COUNT(*) - COUNT(DISTINCT team_code) FROM curated.fact_team_fifa_ranking"
    ).fetchone()[0]
    assert n == 0, f"duplicate team_code in fact_team_fifa_ranking: {n}"


def test_dim_team_current_pk_unique(con: duckdb.DuckDBPyConnection) -> None:
    n = con.sql(
        "SELECT COUNT(*) - COUNT(DISTINCT team_code) FROM curated.dim_team_current"
    ).fetchone()[0]
    assert n == 0, f"duplicate team_code in dim_team_current view: {n}"


# ---------- FK integrity (no orphan facts) ----------


def test_fact_economics_fk(con: duckdb.DuckDBPyConnection) -> None:
    orphans = con.sql(
        "SELECT COUNT(*) FROM curated.fact_team_economics f "
        "LEFT JOIN curated.dim_team t USING (team_code) WHERE t.team_code IS NULL"
    ).fetchone()[0]
    assert orphans == 0


def test_fact_fifa_fk(con: duckdb.DuckDBPyConnection) -> None:
    orphans = con.sql(
        "SELECT COUNT(*) FROM curated.fact_team_fifa_ranking f "
        "LEFT JOIN curated.dim_team t USING (team_code) WHERE t.team_code IS NULL"
    ).fetchone()[0]
    assert orphans == 0


# ---------- R11: last-5-years coverage ----------


def test_economics_last5_gdp(con: duckdb.DuckDBPyConnection) -> None:
    sql = """
    WITH reported AS (
        SELECT year FROM curated.fact_team_economics WHERE gdp_per_capita_usd IS NOT NULL
    ),
    report_window AS (
        SELECT year FROM reported WHERE year >= (SELECT MAX(year) FROM reported) - 4 GROUP BY year
    ),
    qualifiers AS (
        SELECT team_code FROM curated.dim_team WHERE is_wc2026_qualifier AND team_code <> 'SCO'
    ),
    expected AS (
        SELECT q.team_code, w.year FROM qualifiers q CROSS JOIN report_window w
    )
    SELECT COUNT(*) FROM expected e
    LEFT JOIN curated.fact_team_economics f
      ON f.team_code = e.team_code AND f.year = e.year AND f.gdp_per_capita_usd IS NOT NULL
    WHERE f.team_code IS NULL
    """
    missing = con.sql(sql).fetchone()[0]
    assert missing == 0, f"missing GDP rows in last-5-year window: {missing}"


def test_economics_last5_pop(con: duckdb.DuckDBPyConnection) -> None:
    sql = """
    WITH reported AS (
        SELECT year FROM curated.fact_team_economics WHERE population IS NOT NULL
    ),
    report_window AS (
        SELECT year FROM reported WHERE year >= (SELECT MAX(year) FROM reported) - 4 GROUP BY year
    ),
    qualifiers AS (
        SELECT team_code FROM curated.dim_team WHERE is_wc2026_qualifier AND team_code <> 'SCO'
    ),
    expected AS (
        SELECT q.team_code, w.year FROM qualifiers q CROSS JOIN report_window w
    )
    SELECT COUNT(*) FROM expected e
    LEFT JOIN curated.fact_team_economics f
      ON f.team_code = e.team_code AND f.year = e.year AND f.population IS NOT NULL
    WHERE f.team_code IS NULL
    """
    missing = con.sql(sql).fetchone()[0]
    assert missing == 0, f"missing population rows in last-5-year window: {missing}"


# ---------- view sanity ----------


def test_dim_team_current_row_count_matches_dim_team(con: duckdb.DuckDBPyConnection) -> None:
    delta = con.sql(
        "SELECT (SELECT COUNT(*) FROM curated.dim_team_current) - (SELECT COUNT(*) FROM curated.dim_team)"
    ).fetchone()[0]
    assert delta == 0


def test_view_fifa_populated_for_qualifiers(con: duckdb.DuckDBPyConnection) -> None:
    missing = con.sql(
        "SELECT COUNT(*) FROM curated.dim_team_current "
        "WHERE is_wc2026_qualifier AND fifa_points IS NULL"
    ).fetchone()[0]
    assert missing == 0


def test_view_gdp_populated_for_qualifiers(con: duckdb.DuckDBPyConnection) -> None:
    missing = con.sql(
        "SELECT COUNT(*) FROM curated.dim_team_current "
        "WHERE is_wc2026_qualifier AND team_code <> 'SCO' AND gdp_per_capita_usd_latest IS NULL"
    ).fetchone()[0]
    assert missing == 0


def test_quarantine_empty_for_qualifiers(con: duckdb.DuckDBPyConnection) -> None:
    """Whatever lands in quarantine must not be a WC2026 qualifier (any year)."""
    econ_q = con.sql(
        "SELECT COUNT(*) FROM quarantine.unmatched_team_economics q "
        "JOIN curated.dim_team t ON t.team_code = q.team_code "
        "WHERE t.is_wc2026_qualifier"
    ).fetchone()[0]
    fifa_q = con.sql(
        "SELECT COUNT(*) FROM quarantine.unmatched_team_fifa_ranking q "
        "JOIN curated.dim_team t ON t.team_code = q.team_code "
        "WHERE t.is_wc2026_qualifier"
    ).fetchone()[0]
    assert econ_q == 0, f"economics quarantine for qualifiers: {econ_q}"
    assert fifa_q == 0, f"FIFA quarantine for qualifiers: {fifa_q}"


def test_example_query_returns_48_qualifiers(con: duckdb.DuckDBPyConnection) -> None:
    """The canonical model-facing read returns exactly 48 rows with FIFA rank."""
    rows = con.sql(
        "SELECT COUNT(*), COUNT(fifa_rank) FROM curated.dim_team_current WHERE is_wc2026_qualifier"
    ).fetchone()
    assert rows == (48, 48), f"expected (48, 48), got {rows}"
