#!/usr/bin/env python3
"""
Sanity-check the built DuckDB database.

Runs a list of named assertions against `data/wc2026.duckdb`. Each
assertion produces `[PASS]` or `[FAIL]` (or `[WARN]` for non-fatal
checks). Exit code is the number of FAILs.

Use after `tools/build_duckdb.py` to confirm the DB is healthy, or as a
CI gate before declaring a build successful.

Usage:
    python3 tools/verify_duckdb.py
    python3 tools/verify_duckdb.py --db-path data/wc2026.duckdb
"""
from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import duckdb

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB = ROOT / "data" / "wc2026.duckdb"


@dataclass
class Assertion:
    name: str
    sql: str
    predicate: Callable[[Any], bool]
    severity: str = "FAIL"  # "FAIL" or "WARN"
    explain: str = ""


# Bounds tuned to current data (2026-05-13). When new sources land or
# squad rosters change, ranges may need widening — the actual value is
# always logged so a [FAIL] message is informative.
ASSERTIONS: list[Assertion] = [
    # --- Schema presence ---
    Assertion("schema:raw exists", "SELECT COUNT(*) FROM information_schema.schemata WHERE schema_name='raw'", lambda n: n == 1),
    Assertion("schema:curated exists", "SELECT COUNT(*) FROM information_schema.schemata WHERE schema_name='curated'", lambda n: n == 1),
    Assertion("schema:staging exists", "SELECT COUNT(*) FROM information_schema.schemata WHERE schema_name='staging'", lambda n: n == 1),
    Assertion("schema:quarantine exists", "SELECT COUNT(*) FROM information_schema.schemata WHERE schema_name='quarantine'", lambda n: n == 1),

    # --- Dim row count ranges ---
    Assertion("dim_player row count in [1100, 1500]", "SELECT COUNT(*) FROM curated.dim_player", lambda n: 1100 <= n <= 1500),
    Assertion("dim_team row count in [60, 250]", "SELECT COUNT(*) FROM curated.dim_team", lambda n: 60 <= n <= 250),
    Assertion("dim_tournament row count in [3, 20]", "SELECT COUNT(*) FROM curated.dim_tournament", lambda n: 3 <= n <= 20),
    Assertion("dim_model row count > 0", "SELECT COUNT(*) FROM curated.dim_model", lambda n: n > 0),

    # --- PK no-NULL ---
    Assertion("dim_player.player_id is non-null for every row", "SELECT COUNT(*) FROM curated.dim_player WHERE player_id IS NULL OR player_id = ''", lambda n: n == 0),
    Assertion("dim_team.team_code is non-null for every row", "SELECT COUNT(*) FROM curated.dim_team WHERE team_code IS NULL OR team_code = ''", lambda n: n == 0),
    Assertion("dim_tournament.tournament_id is non-null for every row", "SELECT COUNT(*) FROM curated.dim_tournament WHERE tournament_id IS NULL", lambda n: n == 0),

    # --- PK uniqueness ---
    Assertion(
        "dim_player.player_id is unique",
        "SELECT COUNT(*) - COUNT(DISTINCT player_id) FROM curated.dim_player",
        lambda n: n == 0,
    ),
    Assertion(
        "dim_team.team_code is unique",
        "SELECT COUNT(*) - COUNT(DISTINCT team_code) FROM curated.dim_team",
        lambda n: n == 0,
    ),

    # --- player_id format hygiene ---
    Assertion(
        "every dim_player.player_id matches P###### format",
        "SELECT COUNT(*) FROM curated.dim_player WHERE NOT regexp_matches(player_id, '^P[0-9]{6}$')",
        lambda n: n == 0,
    ),

    # --- Registry hygiene: no duplicate (normalized_name, country_code, birth_year) on active players ---
    Assertion(
        "no duplicate (normalized_name, country_code, birth_year) among active players",
        "SELECT COUNT(*) FROM (SELECT normalized_name, country_code, birth_year, COUNT(*) AS n "
        "FROM curated.dim_player WHERE is_active GROUP BY 1, 2, 3 HAVING n > 1)",
        lambda n: n == 0,
        explain="If > 0, the master has accumulated duplicate rows — review db/masters/players.csv",
    ),

    # --- FK integrity ---
    Assertion(
        "every fact_player_xg.player_id exists in dim_player",
        "SELECT COUNT(*) FROM curated.fact_player_xg f "
        "LEFT JOIN curated.dim_player p USING (player_id) WHERE p.player_id IS NULL",
        lambda n: n == 0,
    ),
    Assertion(
        "every non-null fact_player_xg.team_code exists in dim_team",
        "SELECT COUNT(*) FROM curated.fact_player_xg f "
        "LEFT JOIN curated.dim_team t USING (team_code) WHERE f.team_code IS NOT NULL AND t.team_code IS NULL",
        lambda n: n == 0,
    ),
    Assertion(
        "every fact_team_rating.team_code exists in dim_team",
        "SELECT COUNT(*) FROM curated.fact_team_rating f "
        "LEFT JOIN curated.dim_team t USING (team_code) WHERE t.team_code IS NULL",
        lambda n: n == 0,
    ),

    # --- Source coverage (raw tables non-empty) ---
    Assertion("raw.squad_xg_ratings non-empty", "SELECT COUNT(*) FROM raw.squad_xg_ratings", lambda n: n > 0),
    Assertion("raw.sb_player_summary non-empty", "SELECT COUNT(*) FROM raw.sb_player_summary", lambda n: n > 0),
    Assertion("raw.understat_player_xg non-empty", "SELECT COUNT(*) FROM raw.understat_player_xg", lambda n: n > 0),
    Assertion("raw.team_ratings_all_models non-empty", "SELECT COUNT(*) FROM raw.team_ratings_all_models", lambda n: n > 0),

    # --- Match rate floors (drift sentinels) ---
    Assertion(
        "sb_player_summary match rate ≥ 90%",
        "SELECT 100.0 * (SELECT COUNT(*) FROM staging.matched_sb_player_summary) / "
        "(SELECT COUNT(*) FROM raw.sb_player_summary)",
        lambda n: n >= 90.0,
        severity="WARN",
        explain="A canonical squad source should hit ≥ 90%; lower suggests dim_player drift",
    ),

    # --- Quarantine surface (informational) ---
    Assertion(
        "quarantine.unmatched_understat_player_xg <= 7000 rows",
        "SELECT COUNT(*) FROM quarantine.unmatched_understat_player_xg",
        lambda n: n <= 7000,
        severity="WARN",
        explain="Understat universe is large; high quarantine count is expected, not pathological",
    ),

    # --- Facts non-empty ---
    Assertion("fact_player_xg non-empty", "SELECT COUNT(*) FROM curated.fact_player_xg", lambda n: n > 0),
    Assertion("fact_team_rating non-empty", "SELECT COUNT(*) FROM curated.fact_team_rating", lambda n: n > 0),

    # --- Spot-check: at least one player has multi-source coverage ---
    Assertion(
        "at least 50 players have both StatsBomb and Understat xG rows",
        "SELECT COUNT(*) FROM (SELECT player_id FROM curated.fact_player_xg "
        "GROUP BY player_id HAVING COUNT(DISTINCT source) >= 2)",
        lambda n: n >= 50,
    ),
]


def run_assertion(con: duckdb.DuckDBPyConnection, a: Assertion) -> tuple[str, Any]:
    try:
        result = con.sql(a.sql).fetchone()
        val = result[0] if result else None
        ok = a.predicate(val)
        if ok:
            return "PASS", val
        return a.severity, val
    except Exception as e:
        return "ERROR", str(e)


def parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    p.add_argument("--db-path", type=Path, default=DEFAULT_DB)
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)

    if not args.db_path.exists():
        print(f"ERROR: DB not found: {args.db_path}. Run tools/build_duckdb.py first.", file=sys.stderr)
        return 1

    con = duckdb.connect(str(args.db_path), read_only=True)
    fail_count = 0
    warn_count = 0
    pass_count = 0

    print(f"Verifying {args.db_path.relative_to(ROOT) if args.db_path.is_relative_to(ROOT) else args.db_path}\n")
    for a in ASSERTIONS:
        status, val = run_assertion(con, a)
        prefix = f"[{status:<5}]"
        if status == "PASS":
            print(f"  {prefix} {a.name}  =>  {val}")
            pass_count += 1
        elif status == "WARN":
            print(f"  {prefix} {a.name}  =>  {val}  {('— ' + a.explain) if a.explain else ''}")
            warn_count += 1
        elif status == "FAIL":
            print(f"  {prefix} {a.name}  =>  {val}  {('— ' + a.explain) if a.explain else ''}")
            fail_count += 1
        else:  # ERROR
            print(f"  {prefix} {a.name}  =>  {val}")
            fail_count += 1

    con.close()

    print(f"\nSummary: {pass_count} PASS, {warn_count} WARN, {fail_count} FAIL")
    return fail_count


if __name__ == "__main__":
    sys.exit(main())
