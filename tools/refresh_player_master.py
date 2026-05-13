#!/usr/bin/env python3
"""
Refresh the player master at `db/masters/players.csv`.

The master is the system of record for player identity in this project.
Each player carries a stable surrogate key `player_id` (`P######`) that is
never reused and never reassigned. New players get new IDs; existing
players retain theirs across refreshes; players who drop out are flagged
`is_active = false` but never deleted.

Sources (in priority order):
  1. data/raw/squads/wc2026_squads_confirmed.json — the official roster
     JSON. v1 of this file only contains a "pending" country list (no
     player records); the parquet fallback below is used until FIFA
     finalizes squads (~Jun 4 2026).
  2. data/derived/squad_xg_ratings.parquet — the current canonical player
     pool (1,275 WC2026-candidate rows with nation/player/position/
     club/league). Used as the master source while the roster JSON is
     empty.

Matching policy (for ID preservation across refreshes):
  - Exact (normalized_name, country_code, birth_year) when DOB available.
  - Exact (normalized_name, country_code) otherwise.
  - Ambiguous matches (multiple master rows match) are logged and skipped
    — never silently merged. Manual edits to players.csv resolve those.

Idempotent. Safe to re-run. Output is sorted by player_id for stable diffs.

Usage:
    python3 tools/refresh_player_master.py
    python3 tools/refresh_player_master.py --dry-run
    python3 tools/refresh_player_master.py --master-path db/masters/players.csv
    python3 tools/refresh_player_master.py --roster-path data/raw/squads/wc2026_squads_confirmed.json
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

from lib.player_normalize import normalize, normalize_country, derive_birth_year  # noqa: E402


DEFAULT_MASTER = ROOT / "db" / "masters" / "players.csv"
DEFAULT_ROSTER_JSON = ROOT / "data" / "raw" / "squads" / "wc2026_squads_confirmed.json"
DEFAULT_SQUAD_PARQUET = ROOT / "data" / "derived" / "squad_xg_ratings.parquet"


MASTER_COLUMNS = [
    "player_id",
    "display_name",
    "normalized_name",
    "country_code",
    "nation_name",
    "birth_date",
    "birth_year",
    "position",
    "current_club",
    "current_league",
    "statsbomb_name",
    "understat_id",
    "understat_name",
    "is_active",
    "first_seen_at",
    "last_updated_at",
]


def empty_master() -> pd.DataFrame:
    return pd.DataFrame({col: pd.Series(dtype="object") for col in MASTER_COLUMNS})


def load_master(path: Path) -> pd.DataFrame:
    if not path.exists():
        return empty_master()
    df = pd.read_csv(path, dtype="object")
    # Ensure all expected columns exist
    for col in MASTER_COLUMNS:
        if col not in df.columns:
            df[col] = ""
    return df[MASTER_COLUMNS].copy()


def next_id_number(master: pd.DataFrame) -> int:
    if master.empty:
        return 1
    ids = master["player_id"].dropna().astype(str)
    nums = [int(s[1:]) for s in ids if s.startswith("P") and s[1:].isdigit()]
    return (max(nums) + 1) if nums else 1


def format_id(n: int) -> str:
    return f"P{n:06d}"


def load_source_from_parquet(path: Path) -> list[dict]:
    """Load player rows from squad_xg_ratings.parquet.

    Returns list of dicts with: display_name, country_code, nation_name,
    birth_date, position, current_club, current_league.
    """
    if not path.exists():
        return []
    df = pd.read_parquet(path)
    rows: list[dict] = []
    for _, r in df.iterrows():
        nation = str(r.get("nation", "") or "").strip()
        player = str(r.get("player", "") or "").strip()
        if not player or not nation:
            continue
        cc = normalize_country(nation)
        rows.append(
            {
                "display_name": player,
                "country_code": cc,
                "nation_name": nation,
                "birth_date": None,
                "position": str(r.get("position", "") or "").strip() or None,
                "current_club": str(r.get("club", "") or "").strip() or None,
                "current_league": str(r.get("league", "") or "").strip() or None,
            }
        )
    return rows


def load_source_from_json(path: Path) -> list[dict]:
    """Load roster from the WC2026 squad JSON.

    The expected post-Jun-4 structure is:
        {"<country_name>": [{"name": "...", "dob": "YYYY-MM-DD", "position": "...", "club": "..."}, ...], ...}

    v1 placeholder only contains {"pending": [...country names...]}; in
    that case this returns an empty list and the caller falls back to the
    parquet source.
    """
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text())
    except json.JSONDecodeError:
        return []

    if not isinstance(data, dict):
        return []

    rows: list[dict] = []
    for country_name, value in data.items():
        if country_name == "pending":
            continue
        if not isinstance(value, list):
            continue
        cc = normalize_country(country_name)
        for player_entry in value:
            if not isinstance(player_entry, dict):
                continue
            name = player_entry.get("name") or player_entry.get("player")
            if not name:
                continue
            rows.append(
                {
                    "display_name": str(name).strip(),
                    "country_code": cc,
                    "nation_name": country_name,
                    "birth_date": player_entry.get("dob") or player_entry.get("birth_date"),
                    "position": player_entry.get("position"),
                    "current_club": player_entry.get("club"),
                    "current_league": player_entry.get("league"),
                }
            )
    return rows


def find_existing(
    master: pd.DataFrame, normalized_name: str, country_code: Optional[str], birth_year: Optional[int]
) -> pd.Index:
    if master.empty:
        return master.index[:0]
    mask = master["normalized_name"] == normalized_name
    if country_code:
        mask = mask & (master["country_code"] == country_code)
    if birth_year is not None:
        # Only constrain by birth_year when both sides have it
        by_str = str(birth_year)
        mask = mask & (
            (master["birth_year"].fillna("").astype(str) == by_str)
            | (master["birth_year"].fillna("").astype(str) == "")
        )
    return master.index[mask]


def update_master_row(
    master: pd.DataFrame, idx: int, src_row: dict, today: str
) -> bool:
    """Update master row in place. Returns True if any field changed."""
    changed = False
    updates = {
        "display_name": src_row.get("display_name"),
        "position": src_row.get("position"),
        "current_club": src_row.get("current_club"),
        "current_league": src_row.get("current_league"),
    }
    if src_row.get("birth_date"):
        updates["birth_date"] = src_row["birth_date"]
        by = derive_birth_year(src_row["birth_date"])
        if by:
            updates["birth_year"] = str(by)

    for col, val in updates.items():
        if val is None or val == "":
            continue
        if str(master.at[idx, col] or "") != str(val):
            master.at[idx, col] = val
            changed = True

    # Always mark active when seen in the source
    if str(master.at[idx, "is_active"]).lower() != "true":
        master.at[idx, "is_active"] = "true"
        changed = True

    if changed:
        master.at[idx, "last_updated_at"] = today
    return changed


def append_new_player(master: pd.DataFrame, src_row: dict, new_id: str, today: str) -> pd.DataFrame:
    by = derive_birth_year(src_row.get("birth_date"))
    new_row = {
        "player_id": new_id,
        "display_name": src_row.get("display_name", ""),
        "normalized_name": normalize(src_row.get("display_name", "")),
        "country_code": src_row.get("country_code") or "",
        "nation_name": src_row.get("nation_name", ""),
        "birth_date": src_row.get("birth_date") or "",
        "birth_year": str(by) if by else "",
        "position": src_row.get("position") or "",
        "current_club": src_row.get("current_club") or "",
        "current_league": src_row.get("current_league") or "",
        "statsbomb_name": "",
        "understat_id": "",
        "understat_name": "",
        "is_active": "true",
        "first_seen_at": today,
        "last_updated_at": today,
    }
    return pd.concat([master, pd.DataFrame([new_row])], ignore_index=True)


def refresh(master: pd.DataFrame, source_rows: list[dict], today: str) -> tuple[pd.DataFrame, dict]:
    """Apply source rows to master. Returns (updated_master, stats_dict)."""
    stats = {
        "new": 0,
        "updated": 0,
        "unchanged": 0,
        "ambiguous": 0,
        "missing_country": 0,
        "inactive_marked": 0,
    }
    next_n = next_id_number(master)
    touched_ids: set[str] = set()

    for src in source_rows:
        norm = normalize(src.get("display_name", ""))
        if not norm:
            continue
        cc = src.get("country_code")
        if not cc:
            stats["missing_country"] += 1
            continue
        by = derive_birth_year(src.get("birth_date"))

        hits = find_existing(master, norm, cc, by)
        if len(hits) == 0:
            new_id = format_id(next_n)
            next_n += 1
            master = append_new_player(master, src, new_id, today)
            touched_ids.add(new_id)
            stats["new"] += 1
        elif len(hits) == 1:
            idx = hits[0]
            changed = update_master_row(master, idx, src, today)
            touched_ids.add(str(master.at[idx, "player_id"]))
            stats["updated"] += 1 if changed else 0
            stats["unchanged"] += 0 if changed else 1
        else:
            print(
                f"WARN: ambiguous match for '{src.get('display_name')}' ({cc}): "
                f"{len(hits)} existing rows. Skipping.",
                file=sys.stderr,
            )
            stats["ambiguous"] += 1

    # Mark untouched rows inactive (preserving everything else)
    if not master.empty:
        for idx in master.index:
            pid = str(master.at[idx, "player_id"])
            if pid not in touched_ids and str(master.at[idx, "is_active"]).lower() == "true":
                master.at[idx, "is_active"] = "false"
                master.at[idx, "last_updated_at"] = today
                stats["inactive_marked"] += 1

    return master, stats


def parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    p.add_argument("--master-path", type=Path, default=DEFAULT_MASTER)
    p.add_argument(
        "--roster-path",
        type=Path,
        default=DEFAULT_ROSTER_JSON,
        help="WC2026 roster JSON (preferred when populated; falls back to parquet otherwise)",
    )
    p.add_argument(
        "--squad-parquet",
        type=Path,
        default=DEFAULT_SQUAD_PARQUET,
        help="Fallback player source when the roster JSON has no player records",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Compute the refresh and print summary, but do not write players.csv",
    )
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    today = str(date.today())

    master = load_master(args.master_path)
    print(f"[master] loaded {len(master)} existing rows from {args.master_path.relative_to(ROOT) if args.master_path.is_relative_to(ROOT) else args.master_path}")

    # Try JSON first, fall back to parquet
    source = load_source_from_json(args.roster_path)
    source_label = "json"
    if not source:
        source = load_source_from_parquet(args.squad_parquet)
        source_label = "parquet"
    if not source:
        print("ERROR: no player rows in either roster JSON or squad parquet", file=sys.stderr)
        return 1
    print(f"[master] loaded {len(source)} player rows from source ({source_label})")

    master, stats = refresh(master, source, today)

    print(
        f"[master] {len(master)} total | "
        f"new={stats['new']} updated={stats['updated']} unchanged={stats['unchanged']} "
        f"inactive_marked={stats['inactive_marked']} ambiguous={stats['ambiguous']} "
        f"missing_country={stats['missing_country']}"
    )

    if args.dry_run:
        print("[master] dry-run: not writing players.csv")
        return 0

    args.master_path.parent.mkdir(parents=True, exist_ok=True)
    master = master.sort_values("player_id", kind="stable").reset_index(drop=True)
    master.to_csv(args.master_path, index=False, lineterminator="\n")
    print(f"[master] wrote {args.master_path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
