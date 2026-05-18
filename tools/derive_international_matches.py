#!/usr/bin/env python3
"""
Derive `data/derived/international_matches.parquet` from the martj42 CSV.

Inputs:
  data/raw/martj42/latest/results.csv  -- the weekly martj42 pull (one row per
                                          completed or scheduled international
                                          match, 1872 to present)

Outputs:
  data/derived/international_matches.parquet  -- typed columns, both team names
                                                 pre-resolved to FIFA3 via
                                                 normalize_country(). Unresolved
                                                 names appear with NULL
                                                 home_team_code / away_team_code
                                                 so Unit 2's quarantine SQL can
                                                 distinguish the failure mode.

Idempotent: rows are sorted by (match_date, home_team_name, away_team_name)
before write, so re-running on an unchanged CSV produces a byte-stable parquet.

Future-fixture rows (scores = 'NA' in the source) read through with NULL scores
and are filtered out at the curated-fact layer (Unit 2's WHERE clause).

Usage:
    python3 tools/derive_international_matches.py
    python3 tools/derive_international_matches.py --source data/raw/martj42/2026-04-28/results.csv
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
from lib.player_normalize import normalize_country  # noqa: E402

DEFAULT_SOURCE = ROOT / "data" / "raw" / "martj42" / "latest" / "results.csv"
DEFAULT_OUTPUT = ROOT / "data" / "derived" / "international_matches.parquet"


def parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    p.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    p.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return p.parse_args(argv)


def derive(source: Path, output: Path) -> int:
    if not source.exists():
        print(f"ERROR: source CSV not found: {source}", file=sys.stderr)
        return 1

    df = pd.read_csv(source, na_values=["NA", ""], keep_default_na=True)

    # Source columns: date,home_team,away_team,home_score,away_score,tournament,city,country,neutral
    required = {"date", "home_team", "away_team", "home_score", "away_score",
                "tournament", "city", "country", "neutral"}
    missing = required - set(df.columns)
    if missing:
        print(f"ERROR: source CSV missing columns: {sorted(missing)}", file=sys.stderr)
        return 1

    out = pd.DataFrame({
        "match_date":      pd.to_datetime(df["date"], format="%Y-%m-%d", errors="coerce").dt.date,
        "home_team_name":  df["home_team"].astype("string"),
        "home_team_code":  df["home_team"].map(normalize_country).astype("string"),
        "away_team_name":  df["away_team"].astype("string"),
        "away_team_code":  df["away_team"].map(normalize_country).astype("string"),
        "home_score":      pd.to_numeric(df["home_score"], errors="coerce").astype("Int64"),
        "away_score":      pd.to_numeric(df["away_score"], errors="coerce").astype("Int64"),
        "tournament":      df["tournament"].astype("string"),
        "city":            df["city"].astype("string"),
        "country":         df["country"].astype("string"),
        "neutral_site":    df["neutral"].astype(str).str.upper().eq("TRUE"),
    })

    bad_dates = out["match_date"].isna().sum()
    if bad_dates:
        print(f"WARN: {bad_dates} rows had unparseable dates and will be dropped", file=sys.stderr)
        out = out.dropna(subset=["match_date"])

    out = out.sort_values(
        by=["match_date", "home_team_name", "away_team_name"], kind="stable"
    ).reset_index(drop=True)

    unresolved_home = out["home_team_code"].isna().sum()
    unresolved_away = out["away_team_code"].isna().sum()
    print(
        f"[derive] {len(out):,} rows | unresolved home={unresolved_home:,} away={unresolved_away:,}",
        file=sys.stderr,
    )

    output.parent.mkdir(parents=True, exist_ok=True)
    out.to_parquet(output, index=False)
    print(f"[derive] wrote {output.relative_to(ROOT) if output.is_relative_to(ROOT) else output}", file=sys.stderr)
    return 0


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    return derive(args.source, args.output)


if __name__ == "__main__":
    sys.exit(main())
