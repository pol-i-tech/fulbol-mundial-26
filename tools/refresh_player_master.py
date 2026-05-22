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
DEFAULT_CLEAN_PARQUET = ROOT / "data" / "derived" / "wc2026_squads_clean.parquet"


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
    "espn_player_id",
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


def load_source_from_clean_parquet(path: Path) -> list[dict]:
    """Load roster from the ESPN-authoritative clean parquet.

    Produced by `tools/build_wc2026_squads_clean.py`. Carries
    espn_player_id (nullable; ESPN only anchors well-known players),
    position_bucket (GK/DF/MF/FW), and announce_type ('final' or
    'preliminary'). Birth date is currently always NULL — Unit 2 enrichment
    populates it from Wikipedia later.
    """
    if not path.exists():
        return []
    df = pd.read_parquet(path)
    rows: list[dict] = []
    for _, r in df.iterrows():
        name = str(r.get("display_name", "") or "").strip()
        cc = str(r.get("country_code", "") or "").strip() or None
        if not name or not cc:
            continue
        rows.append(
            {
                "display_name": name,
                "country_code": cc,
                "nation_name": str(r.get("nation", "") or "").strip(),
                "birth_date": r.get("birth_date") or None,
                "position": str(r.get("position_bucket", "") or "").strip() or None,
                "current_club": str(r.get("club", "") or "").strip() or None,
                "current_league": None,
                "espn_player_id": (
                    str(r.get("espn_player_id")).strip()
                    if pd.notna(r.get("espn_player_id"))
                    else None
                ),
            }
        )
    return rows


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


def find_by_espn_id(master: pd.DataFrame, espn_id: Optional[str]) -> pd.Index:
    """Tier 0: stable third-party ID lookup. Returns 0, 1, or 2+ matches."""
    if master.empty or not espn_id:
        return master.index[:0]
    return master.index[master["espn_player_id"].fillna("") == str(espn_id)]


def find_fuzzy(
    master: pd.DataFrame, normalized_name: str, country_code: str, threshold: int = 90
) -> pd.Index:
    """Tier 3: rapidfuzz token_set_ratio ≥ threshold within the same country.

    Handles the common 'short common-use name' (ESPN) vs 'full legal name'
    (StatsBomb-style master) case. Returns master indices; caller must
    verify single match.
    """
    if master.empty:
        return master.index[:0]
    try:
        from rapidfuzz import fuzz, process
    except ImportError:
        return master.index[:0]

    pool = master[master["country_code"] == country_code]
    if pool.empty:
        return master.index[:0]
    choices = pool["normalized_name"].fillna("").tolist()
    hits = process.extract(
        normalized_name, choices,
        scorer=fuzz.token_set_ratio, score_cutoff=threshold, limit=5,
    )
    if not hits:
        return master.index[:0]
    matched_positions = [h[2] for h in hits]
    return pool.index[matched_positions]


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

    # Persist espn_player_id on the master when the source carries one.
    # Never overwrite a non-blank existing ID with a different value —
    # that's a real collision needing human review.
    src_eid = src_row.get("espn_player_id")
    if src_eid:
        cur_eid = str(master.at[idx, "espn_player_id"] or "")
        if not cur_eid:
            master.at[idx, "espn_player_id"] = str(src_eid)
            changed = True
        elif cur_eid != str(src_eid):
            print(
                f"WARN: espn_player_id collision on {master.at[idx, 'player_id']} "
                f"({master.at[idx, 'display_name']!r}): existing={cur_eid}, "
                f"source={src_eid}. Keeping existing.",
                file=sys.stderr,
            )

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
        "espn_player_id": src_row.get("espn_player_id") or "",
        "is_active": "true",
        "first_seen_at": today,
        "last_updated_at": today,
    }
    return pd.concat([master, pd.DataFrame([new_row])], ignore_index=True)


def refresh(master: pd.DataFrame, source_rows: list[dict], today: str) -> tuple[pd.DataFrame, dict]:
    """Apply source rows to master. Returns (updated_master, stats_dict).

    Matching order per source row:
      Tier 0  espn_player_id (stable third-party ID)
      Tier 1  (normalized_name, country_code, birth_year) when DOB available
      Tier 2  (normalized_name, country_code)

    Inactive sweep is scoped to nations the current source actually covers;
    pending nations' candidate-pool rows keep their existing is_active flag.
    """
    stats = {
        "new": 0,
        "updated": 0,
        "unchanged": 0,
        "ambiguous": 0,
        "missing_country": 0,
        "inactive_marked": 0,
        "tier0_hits": 0,
    }
    next_n = next_id_number(master)
    touched_ids: set[str] = set()
    covered_countries: set[str] = set()

    for src in source_rows:
        norm = normalize(src.get("display_name", ""))
        if not norm:
            continue
        cc = src.get("country_code")
        if not cc:
            stats["missing_country"] += 1
            continue
        covered_countries.add(cc)
        by = derive_birth_year(src.get("birth_date"))

        # TIER 0: ESPN ID. Fastest, immune to name drift.
        tier0 = find_by_espn_id(master, src.get("espn_player_id"))
        if len(tier0) == 1:
            idx = tier0[0]
            changed = update_master_row(master, idx, src, today)
            touched_ids.add(str(master.at[idx, "player_id"]))
            stats["updated"] += 1 if changed else 0
            stats["unchanged"] += 0 if changed else 1
            stats["tier0_hits"] += 1
            continue
        if len(tier0) > 1:
            print(
                f"WARN: espn_player_id={src.get('espn_player_id')} matches "
                f"{len(tier0)} master rows. Skipping.",
                file=sys.stderr,
            )
            stats["ambiguous"] += 1
            continue

        # TIER 1/2: exact name + country (+ optional birth year)
        hits = find_existing(master, norm, cc, by)

        # TIER 3: fuzzy. ESPN uses common names ('alisson'); the
        # StatsBomb-derived candidate pool uses full legal names
        # ('alisson ramses becker'). token_set_ratio ≥ 90 within the same
        # country bridges the gap. Excludes rows already touched by an
        # earlier ESPN player to avoid two ESPN names collapsing onto one
        # master row.
        if len(hits) == 0:
            fuzzy = find_fuzzy(master, norm, cc, threshold=90)
            fuzzy = [i for i in fuzzy
                     if str(master.at[i, "player_id"]) not in touched_ids]
            if len(fuzzy) == 1:
                hits = pd.Index(fuzzy)
                stats.setdefault("tier3_fuzzy_hits", 0)
                stats["tier3_fuzzy_hits"] += 1
            elif len(fuzzy) > 1:
                print(
                    f"WARN: fuzzy-ambiguous '{src.get('display_name')}' ({cc}): "
                    f"{len(fuzzy)} candidates. Treating as new.",
                    file=sys.stderr,
                )

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

    # Inactive sweep scoped to covered nations only. Pending-nation rows
    # (e.g., teams ESPN hasn't published) keep their existing is_active flag.
    if not master.empty and covered_countries:
        for idx in master.index:
            pid = str(master.at[idx, "player_id"])
            if pid in touched_ids:
                continue
            row_cc = str(master.at[idx, "country_code"] or "")
            if row_cc not in covered_countries:
                continue
            if str(master.at[idx, "is_active"]).lower() == "true":
                master.at[idx, "is_active"] = "false"
                master.at[idx, "last_updated_at"] = today
                stats["inactive_marked"] += 1

    return master, stats


def parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    p.add_argument("--master-path", type=Path, default=DEFAULT_MASTER)
    p.add_argument(
        "--clean-parquet",
        type=Path,
        default=DEFAULT_CLEAN_PARQUET,
        help="ESPN-derived clean squad parquet (primary source)",
    )
    p.add_argument(
        "--roster-path",
        type=Path,
        default=DEFAULT_ROSTER_JSON,
        help="WC2026 Wikipedia roster JSON (fallback if clean parquet is empty)",
    )
    p.add_argument(
        "--squad-parquet",
        type=Path,
        default=DEFAULT_SQUAD_PARQUET,
        help="Candidate-pool parquet (final fallback)",
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

    # Source priority: ESPN-authoritative clean parquet > Wikipedia JSON > candidate pool.
    source = load_source_from_clean_parquet(args.clean_parquet)
    source_label = "clean_parquet"
    if not source:
        source = load_source_from_json(args.roster_path)
        source_label = "wiki_json"
    if not source:
        source = load_source_from_parquet(args.squad_parquet)
        source_label = "candidate_parquet"
    if not source:
        print("ERROR: no player rows in any configured source", file=sys.stderr)
        return 1
    print(f"[master] loaded {len(source)} player rows from source ({source_label})")

    master, stats = refresh(master, source, today)

    print(
        f"[master] {len(master)} total | "
        f"new={stats['new']} updated={stats['updated']} unchanged={stats['unchanged']} "
        f"tier0_hits={stats['tier0_hits']} "
        f"tier3_fuzzy_hits={stats.get('tier3_fuzzy_hits', 0)} "
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
