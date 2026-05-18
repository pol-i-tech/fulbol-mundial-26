#!/usr/bin/env python3
"""
Transform raw country-context snapshots into curated parquets keyed by team_code.

Inputs (latest dated snapshots under data/raw/):
  data/raw/worldbank/<date>/gdp_per_capita.json    -- World Bank NY.GDP.PCAP.CD
  data/raw/worldbank/<date>/population.json        -- World Bank SP.POP.TOTL
  data/raw/fifa_rankings/<date>/ranking_module.json -- Wikipedia FIFA ranking module

Outputs (data/derived/):
  country_gdp_per_capita.parquet    (team_code, year, gdp_per_capita_usd, source_iso2, notes)
  country_population.parquet        (team_code, year, population,         source_iso2, notes)
  fifa_world_ranking_current.parquet (team_code, rank, points, rank_change,
                                      ranking_date, fetched_at)

Master-data-management: rows whose team is not in db/masters/teams.csv are
quarantined to data/derived/<source>_quarantine.csv with a `reason` column,
never silently dropped.

Invariants enforced at write time:
  R7 uniqueness — (team_code, year) unique in WB parquets; team_code unique in FIFA.
  R8 last-5-years coverage — every WC2026 qualifier with iso2_code has a non-null
     measure value for each of the 5 most-recent reported years. The 5-year window
     is computed as [max_reported_year - 4 .. max_reported_year], so when World
     Bank publishes a new year of data the window auto-shifts.

Scotland (SCO) is exempt from the non-null check because the World Bank has no
Scotland entity (rolled into GBR); SCO rows are still emitted with NULL measures
and a populated `notes` column so the time-series grain stays explicit.

Usage:
    python3 tools/build_country_features.py
    python3 tools/build_country_features.py --date 2026-05-14
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from datetime import date as _date, datetime
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
TEAMS_CSV = ROOT / "db" / "masters" / "teams.csv"
RAW_WORLDBANK = ROOT / "data" / "raw" / "worldbank"
RAW_FIFA = ROOT / "data" / "raw" / "fifa_rankings"
DERIVED = ROOT / "data" / "derived"

# Wikipedia FIFA ranking uses some names not in tools/weekly_pull.py:NAME_TO_FIFA3.
# Extend with the few that differ (Türkiye/Turkey, Côte d'Ivoire, etc.).
# The keys here are exact spellings as they appear in
# Module:SportsRankings/data/FIFA_World_Rankings.
WIKI_NAME_TO_FIFA3 = {
    "France": "FRA", "Spain": "ESP", "Argentina": "ARG", "England": "ENG",
    "Portugal": "POR", "Brazil": "BRA", "Netherlands": "NED", "Morocco": "MAR",
    "Belgium": "BEL", "Germany": "GER", "Croatia": "CRO", "Italy": "ITA",
    "Colombia": "COL", "Senegal": "SEN", "Mexico": "MEX", "USA": "USA",
    "Uruguay": "URU", "Japan": "JPN", "Switzerland": "SUI", "Denmark": "DEN",
    "IR Iran": "IRI", "Türkiye": "TUR", "Turkey": "TUR", "Ecuador": "ECU",
    "Austria": "AUT", "Korea Republic": "KOR", "Nigeria": "NGA", "Australia": "AUS",
    "Algeria": "ALG", "Egypt": "EGY", "Canada": "CAN", "Norway": "NOR",
    "Ukraine": "UKR", "Panama": "PAN", "Côte d'Ivoire": "CIV", "Ivory Coast": "CIV",
    "Poland": "POL", "Russia": "RUS", "Wales": "WAL", "Sweden": "SWE",
    "Serbia": "SRB", "Paraguay": "PAR", "Czechia": "CZE", "Czech Republic": "CZE",
    "Hungary": "HUN", "Scotland": "SCO", "Tunisia": "TUN", "Cameroon": "CMR",
    "Congo DR": "COD", "DR Congo": "COD", "Greece": "GRE", "Slovakia": "SVK",
    "Venezuela": "VEN", "Uzbekistan": "UZB", "Costa Rica": "CRC", "Mali": "MLI",
    "Peru": "PER", "Chile": "CHI", "Romania": "ROU", "Republic of Ireland": "IRL",
    "Ireland": "IRL", "Cape Verde": "CPV", "Cabo Verde": "CPV", "Jamaica": "JAM",
    "Bosnia and Herzegovina": "BIH", "Saudi Arabia": "KSA", "Iraq": "IRQ",
    "Jordan": "JOR", "Qatar": "QAT", "South Africa": "RSA",
    "New Zealand": "NZL", "Aotearoa New Zealand": "NZL",
    "Haiti": "HAI", "Curaçao": "CUW", "Curacao": "CUW", "Ghana": "GHA",
}


def load_teams_master() -> tuple[pd.DataFrame, dict[str, str], set[str]]:
    """Return (teams_df, iso2_to_team_code, wc2026_codes)."""
    df = pd.read_csv(TEAMS_CSV, dtype=str)
    df["is_wc2026_qualifier"] = df["is_wc2026_qualifier"].str.lower() == "true"
    iso2_map = {
        row["iso2_code"]: row["team_code"]
        for _, row in df.iterrows()
        if isinstance(row["iso2_code"], str) and row["iso2_code"]
    }
    wc_codes = set(df.loc[df["is_wc2026_qualifier"], "team_code"])
    return df, iso2_map, wc_codes


def latest_snapshot_dir(parent: Path) -> Path:
    """Return the most recent YYYY-MM-DD subdir under `parent`."""
    candidates = sorted(p for p in parent.iterdir() if p.is_dir() and re.match(r"\d{4}-\d{2}-\d{2}$", p.name))
    if not candidates:
        raise FileNotFoundError(f"no dated snapshot dirs under {parent}")
    return candidates[-1]


def transform_worldbank(
    raw_path: Path,
    measure_col: str,
    iso2_map: dict[str, str],
    wc_codes: set[str],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Parse a World Bank indicator JSON into (matched_df, quarantine_df).

    matched_df columns: team_code, year, <measure_col>, source_iso2, notes
    quarantine_df columns: country_id, country_value, year, value, reason
    """
    payload = json.loads(raw_path.read_text())
    # World Bank returns [metadata, rows]; rows is None when total=0.
    rows = payload[1] if isinstance(payload, list) and len(payload) > 1 else None
    if not rows:
        raise RuntimeError(f"empty World Bank payload at {raw_path}")

    matched, quarantine = [], []
    for r in rows:
        iso2 = r["country"]["id"]
        team_code = iso2_map.get(iso2)
        if team_code is None:
            quarantine.append({
                "country_id": iso2,
                "country_value": r["country"]["value"],
                "year": int(r["date"]),
                "value": r["value"],
                "reason": f"iso2 '{iso2}' not in db/masters/teams.csv",
            })
            continue
        matched.append({
            "team_code": team_code,
            "year": int(r["date"]),
            measure_col: r["value"],  # may be None
            "source_iso2": iso2,
            "notes": None,
        })

    # Append Scotland null-block (no World Bank entity; rolled into GBR).
    if "SCO" in wc_codes:
        years = sorted({m["year"] for m in matched})
        for y in years:
            matched.append({
                "team_code": "SCO",
                "year": y,
                measure_col: None,
                "source_iso2": None,
                "notes": "no World Bank entity; rolled into GBR upstream",
            })

    return pd.DataFrame(matched), pd.DataFrame(quarantine)


def parse_fifa_module(raw_path: Path) -> tuple[list[dict], dict]:
    """Parse the Wikipedia FIFA Rankings module wikitext.

    Returns (rows, meta) where rows is a list of {name, rank, change, points}
    and meta carries the updated/previous/next dates and source url.
    """
    payload = json.loads(raw_path.read_text())
    wt = payload["parse"]["wikitext"]["*"]

    # Extract data.updated = { day=..., month='...', year=... }
    def extract_date(field: str) -> str | None:
        m = re.search(
            rf"data\.{field}\s*=\s*\{{\s*day\s*=\s*(\d+)\s*,\s*month\s*=\s*'(\w+)'\s*,\s*year\s*=\s*(\d+)",
            wt,
        )
        if not m:
            return None
        day, month, year = m.group(1), m.group(2), m.group(3)
        try:
            return datetime.strptime(f"{day} {month} {year}", "%d %B %Y").date().isoformat()
        except ValueError:
            return None

    meta = {
        "updated": extract_date("updated"),
        "previous": extract_date("previous"),
        "next": extract_date("next"),
    }
    url_m = re.search(r'url\s*=\s*"([^"]+)"', wt)
    meta["source_url"] = url_m.group(1) if url_m else None

    # Extract { "Name", rank, change, points } tuples
    rows: list[dict] = []
    pattern = re.compile(r'\{\s*"([^"]+)"\s*,\s*(\d+)\s*,\s*(-?\d+)\s*,\s*([\d.]+)\s*\}')
    for m in pattern.finditer(wt):
        rows.append({
            "name": m.group(1),
            "rank": int(m.group(2)),
            "change": int(m.group(3)),
            "points": float(m.group(4)),
        })
    if not rows:
        raise RuntimeError("no rankings parsed from FIFA module wikitext")
    return rows, meta


def transform_fifa(
    raw_path: Path,
    wc_codes: set[str],
) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """Parse FIFA module → (matched_df, quarantine_df, meta).

    matched_df is filtered to WC2026 qualifiers only (one row per qualifier).
    quarantine_df captures any qualifier whose Wikipedia name fails to resolve
    AND any non-qualifier names not in WIKI_NAME_TO_FIFA3 (the latter is the
    common case and only emits a low-noise warning row).
    """
    rows, meta = parse_fifa_module(raw_path)
    ranking_date = meta["updated"] or _date.today().isoformat()
    fetched_at = datetime.utcnow().isoformat(timespec="seconds") + "Z"

    matched, quarantine = [], []
    for r in rows:
        team_code = WIKI_NAME_TO_FIFA3.get(r["name"])
        if team_code is None:
            quarantine.append({
                "source_name": r["name"],
                "rank": r["rank"],
                "points": r["points"],
                "reason": "name not in WIKI_NAME_TO_FIFA3",
                "is_wc2026_qualifier": False,
            })
            continue
        if team_code not in wc_codes:
            # Non-qualifier — drop quietly (we don't emit a parquet row for them).
            continue
        matched.append({
            "team_code": team_code,
            "rank": r["rank"],
            "points": r["points"],
            "rank_change": r["change"],
            "ranking_date": ranking_date,
            "fetched_at": fetched_at,
        })

    # Promote any WC2026 qualifier missing from the parse to a hard quarantine row.
    matched_codes = {m["team_code"] for m in matched}
    missing_qualifiers = wc_codes - matched_codes
    for code in sorted(missing_qualifiers):
        quarantine.append({
            "source_name": None,
            "rank": None,
            "points": None,
            "reason": f"WC2026 qualifier {code} not present in FIFA ranking module",
            "is_wc2026_qualifier": True,
        })

    return pd.DataFrame(matched), pd.DataFrame(quarantine), meta


# ---------- invariant enforcement (R7 uniqueness, R8 last-5-years coverage) ----------


def assert_unique_pk(df: pd.DataFrame, key_cols: list[str], label: str) -> None:
    if df.empty:
        raise AssertionError(f"{label}: empty dataframe")
    dupes = df.groupby(key_cols).size()
    over = dupes[dupes > 1]
    if not over.empty:
        raise AssertionError(
            f"{label}: duplicate keys for {key_cols} -> {over.head(10).to_dict()}"
        )


def assert_last5_coverage(
    df: pd.DataFrame,
    measure_col: str,
    wc_codes: set[str],
    label: str,
    exempt_codes: set[str] = frozenset(),
) -> None:
    """Every WC2026 qualifier (except `exempt_codes`) must have non-null
    measure values for the 5 most-recent reported years."""
    non_null = df[df[measure_col].notna()]
    if non_null.empty:
        raise AssertionError(f"{label}: no non-null rows at all")
    max_year = int(non_null["year"].max())
    window = set(range(max_year - 4, max_year + 1))
    print(f"  [coverage] window for {label}: {sorted(window)}")

    missing: list[tuple[str, int]] = []
    for code in sorted(wc_codes - exempt_codes):
        team_years = set(non_null.loc[non_null["team_code"] == code, "year"].astype(int))
        for y in window:
            if y not in team_years:
                missing.append((code, y))
    if missing:
        raise AssertionError(
            f"{label}: {len(missing)} missing (team, year) cells in last-5-years window "
            f"(first 10: {missing[:10]})"
        )


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--date", default=None,
                   help="Snapshot date to consume (default: latest under data/raw/).")
    args = p.parse_args()

    teams_df, iso2_map, wc_codes = load_teams_master()
    print(f"[info] loaded {len(teams_df)} teams; {len(wc_codes)} WC2026 qualifiers; {len(iso2_map)} iso2 codes")

    # ---- World Bank ----
    wb_dir = (RAW_WORLDBANK / args.date) if args.date else latest_snapshot_dir(RAW_WORLDBANK)
    print(f"[info] World Bank source: {wb_dir.relative_to(ROOT)}")

    gdp_df, gdp_q = transform_worldbank(wb_dir / "gdp_per_capita.json",
                                         "gdp_per_capita_usd", iso2_map, wc_codes)
    pop_df, pop_q = transform_worldbank(wb_dir / "population.json",
                                         "population", iso2_map, wc_codes)

    assert_unique_pk(gdp_df, ["team_code", "year"], "country_gdp_per_capita")
    assert_unique_pk(pop_df, ["team_code", "year"], "country_population")
    assert_last5_coverage(gdp_df, "gdp_per_capita_usd", wc_codes,
                          "country_gdp_per_capita", exempt_codes={"SCO"})
    assert_last5_coverage(pop_df, "population", wc_codes,
                          "country_population", exempt_codes={"SCO"})

    # ---- FIFA ----
    fifa_dir = (RAW_FIFA / args.date) if args.date else latest_snapshot_dir(RAW_FIFA)
    print(f"[info] FIFA source: {fifa_dir.relative_to(ROOT)}")
    fifa_df, fifa_q, fifa_meta = transform_fifa(fifa_dir / "ranking_module.json", wc_codes)

    assert_unique_pk(fifa_df, ["team_code"], "fifa_world_ranking_current")
    matched_qualifiers = set(fifa_df["team_code"])
    missing_qualifiers = wc_codes - matched_qualifiers
    if missing_qualifiers:
        raise AssertionError(
            f"fifa_world_ranking_current: {len(missing_qualifiers)} WC2026 qualifiers missing from FIFA "
            f"ranking (see quarantine): {sorted(missing_qualifiers)}"
        )

    # ---- write parquets ----
    DERIVED.mkdir(parents=True, exist_ok=True)
    paths = {
        "country_gdp_per_capita.parquet": gdp_df,
        "country_population.parquet": pop_df,
        "fifa_world_ranking_current.parquet": fifa_df,
    }
    for name, df in paths.items():
        out = DERIVED / name
        df.to_parquet(out, index=False)
        print(f"[ok] {name}: {len(df):,} rows -> {out.relative_to(ROOT)}")

    # ---- write quarantine (if any) ----
    if not gdp_q.empty:
        gdp_q.to_csv(DERIVED / "country_gdp_quarantine.csv", index=False)
        print(f"[warn] gdp quarantine: {len(gdp_q)} rows -> data/derived/country_gdp_quarantine.csv")
    if not pop_q.empty:
        pop_q.to_csv(DERIVED / "country_population_quarantine.csv", index=False)
        print(f"[warn] population quarantine: {len(pop_q)} rows -> data/derived/country_population_quarantine.csv")
    if not fifa_q.empty:
        fifa_q.to_csv(DERIVED / "fifa_ranking_quarantine.csv", index=False)
        qcrit = fifa_q[fifa_q["is_wc2026_qualifier"] == True]
        if not qcrit.empty:
            print(f"[error] {len(qcrit)} WC2026 qualifier(s) failed FIFA resolution", file=sys.stderr)

    print(f"[ok] FIFA ranking date: {fifa_meta['updated']}; next update: {fifa_meta['next']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
