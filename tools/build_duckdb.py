#!/usr/bin/env python3
"""
Build `data/wc2026.duckdb` end-to-end from data/derived/ parquets and
db/masters/ CSVs.

Pipeline phases (v1 — Unit 3 of the DuckDB MDM plan):
  1. raw      load every in-scope parquet into raw.<name>
  2. curated  load each master CSV into curated.dim_<name> via db/sql/curated/

Future phases (added by Units 4 and 5):
  3. match    resolve player_id for every raw stats row → staging.matched_*
              and quarantine.unmatched_*
  4. facts    build curated.fact_player_xg and curated.fact_team_rating

Idempotent (CREATE OR REPLACE everywhere). Safe to re-run on a freshly
cloned repo with parquets and masters in place.

Usage:
    python3 tools/build_duckdb.py
    python3 tools/build_duckdb.py --db-path data/wc2026.duckdb
    python3 tools/build_duckdb.py --skip-raw   # rebuild dims only
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB = ROOT / "data" / "wc2026.duckdb"
DEFAULT_DATA_DIR = ROOT / "data" / "derived"
DEFAULT_MASTERS_DIR = ROOT / "db" / "masters"
CURATED_SQL_DIR = ROOT / "db" / "sql" / "curated"


# (parquet_filename, raw_table_name)
RAW_TABLES = [
    ("squad_xg_ratings.parquet", "squad_xg_ratings"),
    ("team_attack_ratings.parquet", "team_attack_ratings"),
    ("team_defensive_ratings.parquet", "team_defensive_ratings"),
    ("team_ratings_all_models.parquet", "team_ratings_all_models"),
    ("team_attack_ratings_wc2022.parquet", "team_attack_ratings_wc2022"),
    ("team_defense_ratings_wc2022.parquet", "team_defense_ratings_wc2022"),
    ("team_xga_pedigree.parquet", "team_xga_pedigree"),
    ("defensive_ratings_tournament.parquet", "defensive_ratings_tournament"),
    ("defensive_ratings_club_2526.parquet", "defensive_ratings_club_2526"),
    ("statsbomb_player_xg.parquet", "statsbomb_player_xg"),
    ("statsbomb_team_xg.parquet", "statsbomb_team_xg"),
    ("sb_player_stats.parquet", "sb_player_stats"),
    ("sb_player_summary.parquet", "sb_player_summary"),
    ("sb_player_summary_pre_wc22.parquet", "sb_player_summary_pre_wc22"),
    ("sb_player_stats_pedigree.parquet", "sb_player_stats_pedigree"),
    ("squad_wc2022_proxy.parquet", "squad_wc2022_proxy"),
    ("understat_player_xg.parquet", "understat_player_xg"),
    ("understat_player_xg_raw.parquet", "understat_player_xg_raw"),
    ("understat_2122_players.parquet", "understat_2122_players"),
    ("understat_2526_players.parquet", "understat_2526_players"),
]

# Curated dim SQL files, in dependency order (dims have no inter-deps; sorted for stable behavior)
DIM_SQL_FILES = [
    "dim_player.sql",
    "dim_team.sql",
    "dim_tournament.sql",
    "dim_model.sql",
]


def ensure_schemas(con: duckdb.DuckDBPyConnection) -> None:
    for schema in ("raw", "curated", "staging", "quarantine"):
        con.execute(f"CREATE SCHEMA IF NOT EXISTS {schema}")


def load_raw(con: duckdb.DuckDBPyConnection, data_dir: Path) -> int:
    total = 0
    for parquet, name in RAW_TABLES:
        src = data_dir / parquet
        if not src.exists():
            print(f"ERROR: missing parquet {src.relative_to(ROOT) if src.is_relative_to(ROOT) else src}", file=sys.stderr)
            return -1
        con.execute(
            f"CREATE OR REPLACE TABLE raw.{name} AS SELECT * FROM read_parquet(?)",
            [str(src)],
        )
        count = con.execute(f"SELECT COUNT(*) FROM raw.{name}").fetchone()[0]
        total += count
        print(f"[raw] {name}: {count:,} rows")
    print(f"[raw] {len(RAW_TABLES)} tables loaded, {total:,} total rows")
    return total


def strip_line_comments(sql: str) -> str:
    """Strip `-- ...` line comments. Each line is processed independently so
    semicolons embedded in comments don't confuse the statement splitter."""
    out_lines = []
    for line in sql.splitlines():
        idx = line.find("--")
        if idx >= 0:
            line = line[:idx]
        out_lines.append(line)
    return "\n".join(out_lines)


def load_dims(con: duckdb.DuckDBPyConnection) -> int:
    total = 0
    for sql_file in DIM_SQL_FILES:
        path = CURATED_SQL_DIR / sql_file
        if not path.exists():
            print(f"ERROR: missing SQL file {path.relative_to(ROOT)}", file=sys.stderr)
            return -1
        sql = strip_line_comments(path.read_text())
        for stmt in [s.strip() for s in sql.split(";") if s.strip()]:
            con.execute(stmt)
        # Derive table name from filename: dim_<name>.sql → curated.dim_<name>
        table_name = sql_file.replace(".sql", "")
        count = con.execute(f"SELECT COUNT(*) FROM curated.{table_name}").fetchone()[0]
        total += count
        print(f"[dim] {table_name}: {count:,} rows")
    print(f"[dim] {len(DIM_SQL_FILES)} dim tables loaded, {total:,} total rows")
    return total


def parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    p.add_argument("--db-path", type=Path, default=DEFAULT_DB)
    p.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    p.add_argument("--masters-dir", type=Path, default=DEFAULT_MASTERS_DIR)
    p.add_argument("--skip-raw", action="store_true", help="Skip raw layer; rebuild dims only")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)

    args.db_path.parent.mkdir(parents=True, exist_ok=True)
    print(f"Building DuckDB at {args.db_path.relative_to(ROOT) if args.db_path.is_relative_to(ROOT) else args.db_path}")

    con = duckdb.connect(str(args.db_path))
    try:
        ensure_schemas(con)

        if not args.skip_raw:
            n = load_raw(con, args.data_dir)
            if n < 0:
                return 1

        n = load_dims(con)
        if n < 0:
            return 1
    finally:
        con.close()

    print(f"[done] {args.db_path.relative_to(ROOT) if args.db_path.is_relative_to(ROOT) else args.db_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
