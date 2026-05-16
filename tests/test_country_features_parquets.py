"""Quality gates on the curated country-context parquets.

These tests assert the invariants R7 (no duplicate keys) and R8 (every WC2026
qualifier has measure values for the 5 most-recent reported years) on the
artifacts produced by ``tools/build_country_features.py``.

The tests read the live parquets at ``data/derived/`` -- they are the post-build
contract, equivalent to "verify_duckdb" but for the parquet layer.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
DERIVED = ROOT / "data" / "derived"
TEAMS_CSV = ROOT / "db" / "masters" / "teams.csv"

GDP_PATH = DERIVED / "country_gdp_per_capita.parquet"
POP_PATH = DERIVED / "country_population.parquet"
FIFA_PATH = DERIVED / "fifa_world_ranking_current.parquet"

# Scotland has no World Bank entity (rolls into GBR). Its rows are emitted with
# NULL measure values intentionally; tests exempt SCO from non-null assertions.
NO_WORLDBANK_ENTITY = {"SCO"}


@pytest.fixture(scope="module")
def teams() -> pd.DataFrame:
    df = pd.read_csv(TEAMS_CSV, dtype=str)
    df["is_wc2026_qualifier"] = df["is_wc2026_qualifier"].str.lower() == "true"
    return df


@pytest.fixture(scope="module")
def wc_codes(teams: pd.DataFrame) -> set[str]:
    return set(teams.loc[teams["is_wc2026_qualifier"], "team_code"])


@pytest.fixture(scope="module")
def gdp() -> pd.DataFrame:
    if not GDP_PATH.exists():
        pytest.skip(f"{GDP_PATH} not built yet; run tools/build_country_features.py")
    return pd.read_parquet(GDP_PATH)


@pytest.fixture(scope="module")
def pop() -> pd.DataFrame:
    if not POP_PATH.exists():
        pytest.skip(f"{POP_PATH} not built yet; run tools/build_country_features.py")
    return pd.read_parquet(POP_PATH)


@pytest.fixture(scope="module")
def fifa() -> pd.DataFrame:
    if not FIFA_PATH.exists():
        pytest.skip(f"{FIFA_PATH} not built yet; run tools/build_country_features.py")
    return pd.read_parquet(FIFA_PATH)


# ---------- R7: uniqueness (no duplicate primary-key combinations) ----------


def test_gdp_pk_unique(gdp: pd.DataFrame) -> None:
    dupes = gdp.groupby(["team_code", "year"]).size()
    assert dupes.max() == 1, f"duplicate (team_code, year) rows in GDP parquet: {dupes[dupes > 1].head().to_dict()}"


def test_pop_pk_unique(pop: pd.DataFrame) -> None:
    dupes = pop.groupby(["team_code", "year"]).size()
    assert dupes.max() == 1, f"duplicate (team_code, year) rows in population parquet: {dupes[dupes > 1].head().to_dict()}"


def test_fifa_pk_unique(fifa: pd.DataFrame) -> None:
    assert fifa["team_code"].is_unique, "duplicate team_code in FIFA ranking parquet"


# ---------- R8: last-5-years coverage on the most-recent reported window ----------


def _last5_window(df: pd.DataFrame, measure_col: str) -> set[int]:
    """The 5 most-recent years for which at least one row reports a non-null measure."""
    non_null = df[df[measure_col].notna()]
    assert not non_null.empty, "no non-null measure rows at all"
    max_year = int(non_null["year"].max())
    return set(range(max_year - 4, max_year + 1))


def test_gdp_last5_coverage(gdp: pd.DataFrame, wc_codes: set[str]) -> None:
    window = _last5_window(gdp, "gdp_per_capita_usd")
    non_null = gdp[gdp["gdp_per_capita_usd"].notna()]
    missing: list[tuple[str, int]] = []
    for code in sorted(wc_codes - NO_WORLDBANK_ENTITY):
        years = set(non_null.loc[non_null["team_code"] == code, "year"].astype(int))
        for y in window:
            if y not in years:
                missing.append((code, y))
    assert not missing, f"missing GDP rows in window {sorted(window)}: {missing[:10]}"


def test_pop_last5_coverage(pop: pd.DataFrame, wc_codes: set[str]) -> None:
    window = _last5_window(pop, "population")
    non_null = pop[pop["population"].notna()]
    missing: list[tuple[str, int]] = []
    for code in sorted(wc_codes - NO_WORLDBANK_ENTITY):
        years = set(non_null.loc[non_null["team_code"] == code, "year"].astype(int))
        for y in window:
            if y not in years:
                missing.append((code, y))
    assert not missing, f"missing population rows in window {sorted(window)}: {missing[:10]}"


def test_fifa_full_coverage(fifa: pd.DataFrame, wc_codes: set[str]) -> None:
    fifa_codes = set(fifa["team_code"])
    missing = wc_codes - fifa_codes
    assert not missing, f"WC2026 qualifiers missing from FIFA ranking: {sorted(missing)}"
    assert fifa["points"].notna().all(), "some FIFA ranking rows have null points"


# ---------- additional schema sanity ----------


def test_gdp_schema(gdp: pd.DataFrame) -> None:
    expected = {"team_code", "year", "gdp_per_capita_usd", "source_iso2", "notes"}
    assert expected.issubset(set(gdp.columns)), f"GDP columns: {set(gdp.columns)}"
    assert (gdp["team_code"].str.len() == 3).all(), "team_code must be 3 chars"
    assert gdp["year"].between(1986, 2025).all(), "year must be in [1986, 2025]"


def test_pop_schema(pop: pd.DataFrame) -> None:
    expected = {"team_code", "year", "population", "source_iso2", "notes"}
    assert expected.issubset(set(pop.columns)), f"population columns: {set(pop.columns)}"
    non_null_pop = pop[pop["population"].notna()]
    assert (non_null_pop["population"] > 0).all(), "population must be positive when present"


def test_fifa_schema(fifa: pd.DataFrame) -> None:
    expected = {"team_code", "rank", "points", "rank_change", "ranking_date", "fetched_at"}
    assert expected.issubset(set(fifa.columns)), f"FIFA columns: {set(fifa.columns)}"
    assert (fifa["rank"] > 0).all(), "FIFA rank must be positive"
    assert (fifa["points"] > 0).all(), "FIFA points must be positive"


def test_scotland_null_block_present(gdp: pd.DataFrame, pop: pd.DataFrame) -> None:
    """SCO should appear in both World Bank parquets with NULL measure but
    populated notes -- explicit-null discipline, not silent drop."""
    sco_gdp = gdp[gdp["team_code"] == "SCO"]
    sco_pop = pop[pop["team_code"] == "SCO"]
    assert not sco_gdp.empty, "Scotland missing from GDP parquet"
    assert not sco_pop.empty, "Scotland missing from population parquet"
    assert sco_gdp["gdp_per_capita_usd"].isna().all(), "Scotland GDP should be all NULL"
    assert sco_pop["population"].isna().all(), "Scotland population should be all NULL"
    assert sco_gdp["notes"].notna().all(), "Scotland rows should carry a notes value"
