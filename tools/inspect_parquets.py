#!/usr/bin/env python3
"""
Inspect every parquet in `data/derived/` and emit a deterministic schema report.

Two modes:
  default      Print one block per parquet: columns, dtypes, row count, 3 sample rows.
  --player-names
               Sample player-name columns across the player-grain parquets so the
               naming-convention differences between StatsBomb, Understat, and the
               squad-xg parquet are inspectable side-by-side.

Used by `docs/plans/2026-05-13-001-feat-build-duckdb-database-curated-models-plan.md`
(Unit 1) to ground the data-model design doc in real parquet shapes.

Read-only. Idempotent: same parquets in, same output.

Usage:
    python3 tools/inspect_parquets.py
    python3 tools/inspect_parquets.py --player-names
    python3 tools/inspect_parquets.py --data-dir data/derived
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DATA_DIR = ROOT / "data" / "derived"

PLAYER_PARQUETS = (
    "statsbomb_player_xg.parquet",
    "understat_player_xg.parquet",
    "squad_xg_ratings.parquet",
)

NAME_COL_CANDIDATES = (
    "player",
    "player_name",
    "name",
    "display_name",
    "player_display_name",
)


def list_parquets(data_dir: Path) -> list[Path]:
    return sorted(data_dir.glob("*.parquet"))


def inspect_one(path: Path) -> None:
    rel = path.relative_to(ROOT)
    df = pd.read_parquet(path)
    print(f"\n=== {rel} ===")
    print(f"  rows: {len(df):,}")
    print(f"  cols: {len(df.columns)}")
    print("  schema:")
    for col, dtype in df.dtypes.items():
        print(f"    {col:<40} {dtype}")
    print("  sample (first 3 rows):")
    sample = df.head(3).to_string(index=False, max_colwidth=40)
    for line in sample.splitlines():
        print(f"    {line}")


def find_name_col(df: pd.DataFrame) -> str | None:
    for candidate in NAME_COL_CANDIDATES:
        if candidate in df.columns:
            return candidate
    for col in df.columns:
        if df[col].dtype == object:
            return col
    return None


def sample_player_names(data_dir: Path, n: int = 20) -> None:
    print(f"\n=== player name samples ({n} per source, deterministic) ===\n")
    samples: dict[str, list[str]] = {}
    for parquet in PLAYER_PARQUETS:
        path = data_dir / parquet
        if not path.exists():
            print(f"  [skip] {parquet}: file not found")
            continue
        df = pd.read_parquet(path)
        name_col = find_name_col(df)
        if name_col is None:
            print(f"  [skip] {parquet}: no string column found")
            continue
        unique_names = sorted(df[name_col].dropna().astype(str).unique())
        step = max(1, len(unique_names) // n)
        picks = unique_names[::step][:n]
        samples[f"{parquet} :: {name_col}"] = picks
        print(f"  {parquet} :: {name_col}  ({len(unique_names):,} distinct)")

    if not samples:
        return

    max_rows = max(len(v) for v in samples.values())
    headers = list(samples.keys())
    print()
    print("  " + " | ".join(f"{h[:38]:<38}" for h in headers))
    print("  " + "-+-".join("-" * 38 for _ in headers))
    for i in range(max_rows):
        cells = []
        for h in headers:
            vals = samples[h]
            cell = vals[i] if i < len(vals) else ""
            cells.append(f"{cell[:38]:<38}")
        print("  " + " | ".join(cells))


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=DEFAULT_DATA_DIR,
        help=f"directory containing parquets (default: {DEFAULT_DATA_DIR.relative_to(ROOT)})",
    )
    parser.add_argument(
        "--player-names",
        action="store_true",
        help="sample player-name columns side-by-side across player parquets",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)

    if not args.data_dir.exists():
        print(f"ERROR: data dir not found: {args.data_dir}", file=sys.stderr)
        return 1

    parquets = list_parquets(args.data_dir)
    if not parquets:
        print(f"ERROR: no parquets found in {args.data_dir}", file=sys.stderr)
        return 1

    if args.player_names:
        sample_player_names(args.data_dir)
        return 0

    print(f"Inspecting {len(parquets)} parquet(s) in {args.data_dir.relative_to(ROOT)}")
    for path in parquets:
        inspect_one(path)
    print(f"\nDone. {len(parquets)} parquet(s) inspected.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
