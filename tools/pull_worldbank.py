#!/usr/bin/env python3
"""
Pull World Bank GDP per capita (current US$) and total population
for all WC2026 qualifiers with an ISO-2 code, for the last 40 years.

Source: World Bank Indicators API v2 (public, no auth required).
  https://datahelpdesk.worldbank.org/knowledgebase/articles/889392

Indicators:
  NY.GDP.PCAP.CD  -- GDP per capita (current US$)
  SP.POP.TOTL     -- Population, total

Output (immutable dated snapshots):
  data/raw/worldbank/<YYYY-MM-DD>/gdp_per_capita.json
  data/raw/worldbank/<YYYY-MM-DD>/population.json

Country list is derived from db/masters/teams.csv (is_wc2026_qualifier=true).
Scotland (SCO) is excluded -- no World Bank entity (rolled into GBR).

Bulk request: one HTTP call per indicator covers all qualifiers via the
semicolon-delimited country syntax. Two HTTP calls total.

Usage:
    python3 tools/pull_worldbank.py
    python3 tools/pull_worldbank.py --date 2026-05-14
    python3 tools/pull_worldbank.py --start-year 1986 --end-year 2025
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
import urllib.request
import urllib.error
from datetime import date as _date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TEAMS_CSV = ROOT / "db" / "masters" / "teams.csv"
RAW_DIR = ROOT / "data" / "raw" / "worldbank"

API_BASE = "https://api.worldbank.org/v2/country"
INDICATORS = {
    "gdp_per_capita": "NY.GDP.PCAP.CD",
    "population": "SP.POP.TOTL",
}
USER_AGENT = "fulbol-mundial-26/worldbank-fetcher (+https://github.com/) python-urllib"


def load_wc2026_iso2() -> list[str]:
    """Return ISO-2 codes for every WC2026 qualifier with a non-empty iso2_code.

    Scotland is the only known qualifier without an ISO-2 (it doesn't have a
    sovereign one; it rolls into GBR for World Bank purposes).
    """
    iso2: list[str] = []
    skipped: list[str] = []
    with TEAMS_CSV.open(newline="") as f:
        for row in csv.DictReader(f):
            if row["is_wc2026_qualifier"].strip().lower() != "true":
                continue
            code = (row["iso2_code"] or "").strip()
            if code:
                iso2.append(code)
            else:
                skipped.append(row["team_code"])
    if skipped:
        print(f"[warn] skipping {len(skipped)} qualifier(s) without iso2_code: {sorted(skipped)}", file=sys.stderr)
    return iso2


def fetch_indicator(iso2_codes: list[str], indicator: str, start_year: int, end_year: int) -> list:
    """Fetch one World Bank indicator for the given countries and year range.

    Returns the parsed JSON (a 2-element list: [metadata_dict, data_rows_or_None]).
    Raises on HTTP error or invalid JSON; raw payload preserved by caller.
    """
    countries = ";".join(iso2_codes)
    url = (
        f"{API_BASE}/{countries}/indicator/{indicator}"
        f"?date={start_year}:{end_year}&format=json&per_page=20000"
    )
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=60) as resp:
        if resp.status >= 500:
            raise RuntimeError(f"World Bank 5xx for {indicator}: HTTP {resp.status}")
        body = resp.read().decode("utf-8")
    payload = json.loads(body)
    # World Bank wraps errors as a single-element list with a 'message' key.
    if isinstance(payload, list) and payload and isinstance(payload[0], dict) and "message" in payload[0]:
        raise RuntimeError(f"World Bank API error for {indicator}: {payload[0]['message']}")
    return payload


def write_snapshot(payload: list, out_path: Path) -> int:
    """Write the raw JSON payload verbatim. Returns the data-row count for logging."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    # Pretty-print so dated snapshots diff cleanly across builds.
    out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False))
    rows = payload[1] if isinstance(payload, list) and len(payload) > 1 and isinstance(payload[1], list) else []
    return len(rows)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--date", default=_date.today().isoformat(),
                   help="Snapshot date dir (default: today). Format: YYYY-MM-DD.")
    p.add_argument("--start-year", type=int, default=1986,
                   help="First year inclusive (default: 1986 = 40 years back).")
    p.add_argument("--end-year", type=int, default=2025,
                   help="Last year inclusive (default: 2025 = last fully-reported year).")
    args = p.parse_args()

    iso2 = load_wc2026_iso2()
    if not iso2:
        print("[error] no WC2026 qualifier ISO-2 codes found", file=sys.stderr)
        return 1
    print(f"[info] fetching {len(iso2)} countries for years {args.start_year}-{args.end_year}")

    out_dir = RAW_DIR / args.date
    out_dir.mkdir(parents=True, exist_ok=True)
    for label, indicator in INDICATORS.items():
        out_path = out_dir / f"{label}.json"
        try:
            payload = fetch_indicator(iso2, indicator, args.start_year, args.end_year)
        except urllib.error.HTTPError as e:
            print(f"[error] {indicator} HTTP {e.code}: {e.reason}", file=sys.stderr)
            return 2
        except urllib.error.URLError as e:
            print(f"[error] {indicator} network: {e.reason}", file=sys.stderr)
            return 2
        n_rows = write_snapshot(payload, out_path)
        print(f"[ok] {label}: {n_rows:,} rows -> {out_path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
