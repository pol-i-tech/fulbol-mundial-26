#!/usr/bin/env python3
"""
Generate `db/masters/teams.csv` from the project's FIFA-code dictionaries.

Source of truth:
  - tools/weekly_pull.py: NAME_TO_FIFA3, ISO2_TO_FIFA3
  - tools/lib/player_normalize.py: _DB_LAYER_NAME_SUPPLEMENT (non-WC2026
    teams that show up in player parquets)
  - data/derived/team_defensive_ratings.parquet: the 48-team WC2026
    qualifier list (used to populate is_wc2026_qualifier)

Confederation mapping is hand-coded below — FIFA's 6 confederations are
stable, no need to scrape.

Idempotent. Safe to re-run.

Usage:
    python3 tools/refresh_team_master.py
    python3 tools/refresh_team_master.py --dry-run
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

from lib.player_normalize import (  # noqa: E402
    NAME_TO_FIFA3,
    ISO2_TO_FIFA3,
    _DB_LAYER_NAME_SUPPLEMENT,
    normalize_country,
)


DEFAULT_OUTPUT = ROOT / "db" / "masters" / "teams.csv"
WC2026_QUALIFIER_SOURCE = ROOT / "data" / "derived" / "team_defensive_ratings.parquet"


CONFEDERATION = {
    # AFC — Asian Football Confederation
    "AFC": {"AUS", "JPN", "KOR", "PRK", "IRN", "IRI", "IRQ", "KSA", "QAT", "UAE",
            "UZB", "JOR", "BHR", "OMA", "PAK", "IND", "CHN", "THA", "VIE", "PHI",
            "INA", "MAS", "SIN", "TPE", "HKG", "MAC", "MGL", "KGZ", "TJK", "TKM",
            "KAZ"},
    # CAF — Confederation of African Football
    "CAF": {"EGY", "MAR", "SEN", "TUN", "ALG", "CMR", "NGA", "CIV", "GHA", "RSA",
            "COD", "CPV", "AGO", "BEN", "BFA", "BUR", "BDI", "CAF", "TCD", "COM",
            "CGO", "DJI", "ERI", "ETH", "GAB", "GAM", "GNB", "GUI", "EQG", "KEN",
            "LBR", "LBY", "LES", "MAD", "MWI", "MLI", "MRI", "MTN", "MOZ", "NAM",
            "NIG", "RWA", "STP", "SEY", "SLE", "SOM", "SSD", "SDN", "SWZ", "TAN",
            "TOG", "UGA", "ZAM", "ZIM"},
    # CONCACAF — Confederation of North, Central American and Caribbean
    "CONCACAF": {"USA", "MEX", "CAN", "CRC", "HON", "JAM", "CUB", "HAI", "PAN",
                 "TRI", "GUA", "SLV", "NCA", "DOM", "BLZ", "BAH", "BAR", "BER",
                 "BOE", "CAY", "CUW", "DMA", "GLP", "GUF", "GRN", "GUY", "AIA",
                 "ATG", "ARU", "MSR", "PUR", "SKN", "LCA", "MTQ", "VIN", "SXM",
                 "SMA", "SUR", "TCA", "VGB", "VIR"},
    # CONMEBOL — South America
    "CONMEBOL": {"ARG", "BRA", "URU", "COL", "ECU", "PAR", "CHI", "VEN", "BOL",
                 "PER"},
    # OFC — Oceania
    "OFC": {"NZL", "FIJ", "NCL", "SOL", "TAH", "VAN", "PNG", "COK", "SAM", "TON",
            "ASA"},
    # UEFA — Europe
    "UEFA": {"ESP", "FRA", "GER", "ITA", "POR", "ENG", "NED", "BEL", "CRO", "DEN",
             "SUI", "SWE", "NOR", "AUT", "SRB", "CZE", "WAL", "SCO", "UKR", "TUR",
             "BIH", "POL", "ROU", "SVK", "SVN", "HUN", "GRE", "FIN", "ISL", "ISR",
             "ALB", "AND", "ARM", "AZE", "BLR", "BUL", "CYP", "EST", "FRO", "GEO",
             "GIB", "IRL", "KAZ", "KOS", "LIE", "LVA", "LTU", "LUX", "MDA", "MKD",
             "MLT", "MNE", "NIR", "RUS", "SMR", "TUR"},
}


def confederation_for(fifa3: str) -> str:
    for conf, codes in CONFEDERATION.items():
        if fifa3 in codes:
            return conf
    return "UNKNOWN"


def get_wc2026_qualifiers() -> set[str]:
    """Read the 48-team WC2026 qualifier list from team_defensive_ratings."""
    if not WC2026_QUALIFIER_SOURCE.exists():
        return set()
    df = pd.read_parquet(WC2026_QUALIFIER_SOURCE)
    return {
        normalize_country(n)
        for n in df["nation"].dropna().astype(str).unique()
        if normalize_country(n)
    }


def build_team_master() -> pd.DataFrame:
    # Build code → preferred display name
    # Strategy: iterate NAME_TO_FIFA3 + supplement. When multiple display names
    # map to one code (e.g., "Korea Republic" and "South Korea" → KOR), keep
    # the first non-aliased one (preserve insertion order of NAME_TO_FIFA3).
    code_to_name: dict[str, str] = {}
    for name, code in NAME_TO_FIFA3.items():
        code_to_name.setdefault(code, name)
    for name, code in _DB_LAYER_NAME_SUPPLEMENT.items():
        code_to_name.setdefault(code, name)

    # Reverse ISO2_TO_FIFA3
    iso2_for_code: dict[str, str] = {}
    for iso2, code in ISO2_TO_FIFA3.items():
        iso2_for_code.setdefault(code, iso2)

    wc2026 = get_wc2026_qualifiers()

    rows = []
    for code, name in sorted(code_to_name.items()):
        # Skip sentinel entries (NAME_TO_FIFA3 carries "Other" → "OTHER" for
        # misclassified data; not a real team)
        if code == "OTHER" or name == "Other":
            continue
        rows.append(
            {
                "team_code": code,
                "team_name": name,
                "iso2_code": iso2_for_code.get(code, ""),
                "confederation": confederation_for(code),
                "is_wc2026_qualifier": "true" if code in wc2026 else "false",
            }
        )
    return pd.DataFrame(rows)


def parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    p.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    p.add_argument("--dry-run", action="store_true")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    df = build_team_master()

    n_qualifiers = (df["is_wc2026_qualifier"] == "true").sum()
    unknown_conf = (df["confederation"] == "UNKNOWN").sum()
    print(
        f"[team-master] {len(df)} teams total | "
        f"WC2026 qualifiers: {n_qualifiers} | unknown confederation: {unknown_conf}"
    )

    if unknown_conf:
        print("[team-master] teams with unknown confederation (consider adding):")
        for _, r in df[df["confederation"] == "UNKNOWN"].iterrows():
            print(f"    {r['team_code']}  {r['team_name']}")

    if args.dry_run:
        print("[team-master] dry-run: not writing")
        return 0

    args.output.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(args.output, index=False, lineterminator="\n")
    print(f"[team-master] wrote {args.output.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
