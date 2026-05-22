#!/usr/bin/env python3
"""
Build `data/derived/wc2026_squads_clean.parquet` from the latest ESPN raw
snapshot under `data/raw/squads/espn/<date>/wc2026_squads.json`.

Outputs (idempotent, deterministic row order):
  data/derived/wc2026_squads_clean.parquet
  data/derived/wc2026_squads_clean.csv
  data/derived/wc2026_squads_clean_collisions.csv  (empty when no collisions)

Per-player columns:
  nation, country_code, confederation, group,
  announce_type, announced_date, manager,
  espn_player_id, display_name, normalized_name,
  position_bucket, club,
  birth_date, birth_year, wiki_dob_match,   (v1: all NULL/false; Unit 2 enrichment)
  as_of_date, source_date

Dedup contract: within a team, `(espn_player_id or normalized_name)` must
be unique. Collisions (two distinct ESPN IDs normalize to the same name in
the same country) are emitted to the collisions CSV for human review.

Usage:
  python3 tools/build_wc2026_squads_clean.py
  python3 tools/build_wc2026_squads_clean.py --raw-json data/raw/squads/espn/2026-05-22/wc2026_squads.json
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path
from typing import Optional

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

from lib.confederation import (  # noqa: E402
    CONFEDERATION_BY_NATION,
    ESPN_NATION_ALIASES,
)
from lib.player_normalize import normalize, normalize_country  # noqa: E402

DEFAULT_ESPN_DIR = ROOT / "data" / "raw" / "squads" / "espn"
DEFAULT_DERIVED = ROOT / "data" / "derived"

OUTPUT_COLUMNS = [
    "nation",
    "country_code",
    "confederation",
    "group",
    "announce_type",
    "announced_date",
    "manager",
    "espn_player_id",
    "display_name",
    "normalized_name",
    "position_bucket",
    "club",
    "birth_date",
    "birth_year",
    "wiki_dob_match",
    "as_of_date",
    "source_date",
]


def find_latest_snapshot(espn_dir: Path) -> Optional[Path]:
    """Return the JSON path under the most recent YYYY-MM-DD subdir."""
    if not espn_dir.exists():
        return None
    candidates = sorted(
        [d for d in espn_dir.iterdir() if d.is_dir() and len(d.name) == 10],
        reverse=True,
    )
    for d in candidates:
        p = d / "wc2026_squads.json"
        if p.exists():
            return p
    return None


def resolve_country_code(nation: str) -> Optional[str]:
    canonical = ESPN_NATION_ALIASES.get(nation, nation)
    return normalize_country(canonical)


def explode_to_rows(payload: dict, today: str) -> tuple[list[dict], list[str]]:
    """Return (rows, unresolved_nations)."""
    rows: list[dict] = []
    unresolved: list[str] = []

    source_date = payload.get("as_of_date") or ""

    for team in payload.get("teams", []):
        nation = team.get("nation")
        if not nation:
            continue

        cc = resolve_country_code(nation)
        if cc is None:
            unresolved.append(nation)
            continue
        confederation = CONFEDERATION_BY_NATION.get(
            ESPN_NATION_ALIASES.get(nation, nation)
        ) or CONFEDERATION_BY_NATION.get(nation)

        group = team.get("group")
        announce_type = team.get("announce_type")
        announced_date = team.get("announced_date")
        manager = team.get("manager")

        for p in team.get("players", []):
            name = (p.get("name") or "").strip()
            if not name:
                continue
            norm = normalize(name)
            if not norm:
                continue
            rows.append(
                {
                    "nation": nation,
                    "country_code": cc,
                    "confederation": confederation,
                    "group": group,
                    "announce_type": announce_type,
                    "announced_date": announced_date,
                    "manager": manager,
                    "espn_player_id": p.get("espn_player_id"),
                    "display_name": name,
                    "normalized_name": norm,
                    "position_bucket": p.get("position_bucket"),
                    "club": p.get("club"),
                    "birth_date": None,
                    "birth_year": None,
                    "wiki_dob_match": False,
                    "as_of_date": today,
                    "source_date": source_date,
                }
            )

    return rows, unresolved


def detect_collisions(df: pd.DataFrame) -> pd.DataFrame:
    """Two distinct espn_player_ids that normalize to the same name within a country."""
    with_id = df[df["espn_player_id"].notna()].copy()
    if with_id.empty:
        return with_id.iloc[0:0]
    grouped = (
        with_id.groupby(["country_code", "normalized_name"])
        .agg(
            espn_ids=("espn_player_id", lambda s: sorted(set(s))),
            n=("espn_player_id", "nunique"),
        )
        .reset_index()
    )
    collisions = grouped[grouped["n"] > 1].copy()
    if collisions.empty:
        return collisions
    collisions["espn_player_ids"] = collisions["espn_ids"].apply(",".join)
    return collisions[["country_code", "normalized_name", "n", "espn_player_ids"]]


def parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    p.add_argument(
        "--raw-json",
        type=Path,
        default=None,
        help="ESPN raw JSON snapshot (default: latest under data/raw/squads/espn/<date>/)",
    )
    p.add_argument(
        "--espn-dir",
        type=Path,
        default=DEFAULT_ESPN_DIR,
        help="Root directory holding YYYY-MM-DD subdirs",
    )
    p.add_argument("--out-dir", type=Path, default=DEFAULT_DERIVED)
    p.add_argument(
        "--finals-only",
        action="store_true",
        help="Emit only players from teams with announce_type='final' (drops preliminary squads)",
    )
    return p.parse_args(argv)


def main(argv: Optional[list[str]] = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    today = str(date.today())

    snap = args.raw_json or find_latest_snapshot(args.espn_dir)
    if snap is None or not snap.exists():
        print("ERROR: no ESPN snapshot found", file=sys.stderr)
        return 1
    print(f"[clean] reading {snap.relative_to(ROOT) if snap.is_relative_to(ROOT) else snap}")

    payload = json.loads(snap.read_text(encoding="utf-8"))
    rows, unresolved = explode_to_rows(payload, today)

    if unresolved:
        print(
            f"ERROR: {len(unresolved)} ESPN nation(s) could not be mapped to FIFA3: "
            f"{sorted(set(unresolved))}. Update ESPN_NATION_ALIASES in tools/lib/confederation.py.",
            file=sys.stderr,
        )
        return 1

    df = pd.DataFrame(rows, columns=OUTPUT_COLUMNS)

    if args.finals_only:
        before = len(df)
        df = df[df["announce_type"] == "final"].reset_index(drop=True)
        print(f"[clean] filtered to finals: {before} → {len(df)} rows")

    # Detect collisions before deterministic sort (sort doesn't change semantics)
    collisions = detect_collisions(df)

    # Stable order: country_code, position_bucket order GK/DF/MF/FW, then espn_player_id, then name
    bucket_order = {"GK": 0, "DF": 1, "MF": 2, "FW": 3}
    df["_bk"] = df["position_bucket"].map(bucket_order).fillna(9).astype(int)
    df = df.sort_values(
        by=["country_code", "_bk", "espn_player_id", "display_name"],
        kind="stable",
        na_position="last",
    ).drop(columns=["_bk"]).reset_index(drop=True)

    args.out_dir.mkdir(parents=True, exist_ok=True)
    pq = args.out_dir / "wc2026_squads_clean.parquet"
    csv = args.out_dir / "wc2026_squads_clean.csv"
    coll = args.out_dir / "wc2026_squads_clean_collisions.csv"

    df.to_parquet(pq, index=False)
    df.to_csv(csv, index=False, lineterminator="\n")
    collisions.to_csv(coll, index=False, lineterminator="\n")

    finals_n = int((df["announce_type"] == "final").sum())
    prelim_n = int((df["announce_type"] == "preliminary").sum())
    teams_n = df["country_code"].nunique()
    with_id = int(df["espn_player_id"].notna().sum())

    print(f"[clean] {len(df)} rows | {teams_n} nations | "
          f"final={finals_n} prelim={prelim_n} | with_espn_id={with_id}")
    print(f"[clean] wrote {pq.relative_to(ROOT)}")
    if not collisions.empty:
        print(
            f"WARN: {len(collisions)} collisions written to {coll.relative_to(ROOT)}",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
