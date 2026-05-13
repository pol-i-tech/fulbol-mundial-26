#!/usr/bin/env python3
"""
Resolve a stable `player_id` for every raw stats row that references a
player. Matched rows land in `staging.matched_<source>`; unmatched rows
land in `quarantine.unmatched_<source>` with a `match_reason` column.

Source → master alignment is one-way. This script never extends
`curated.dim_player` (the master is owned by tools/refresh_player_master.py).
What it DOES write back is the source-specific name/ID columns on the
master (e.g., `statsbomb_name`, `understat_id`) so the next build hits
Tier 0/2 instantly for the same source row.

Sources matched (v1):
  - raw.sb_player_summary       (per-player aggregated StatsBomb)
  - raw.sb_player_stats_pedigree (per-player-per-tournament StatsBomb)
  - raw.understat_player_xg     (per-player aggregated Understat)
  - raw.understat_2526_players  (current 2025-26 season Understat)

Tier order:
  Tier 0  Understat `player_id` already cached on dim_player.understat_id
  Tier 1  exact (normalized_name, country_code, birth_year)   [dormant in v1]
  Tier 2  exact (normalized_name, country_code)
  Tier 3  exact (normalized_name, current_club)               [no-country fallback]
  Tier 4  fuzzy ≥90 token_set_ratio + shared country or club
  else    quarantine

Idempotent. Safe to re-run. Also invoked by `tools/build_duckdb.py`
between the dim phase and the fact phase.

Usage:
    python3 tools/match_sources_to_masters.py
    python3 tools/match_sources_to_masters.py --db-path data/wc2026.duckdb
    python3 tools/match_sources_to_masters.py --no-master-writeback
"""
from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Optional

import duckdb
import pandas as pd
from rapidfuzz import fuzz, process

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

from lib.player_normalize import normalize, normalize_country  # noqa: E402


DEFAULT_DB = ROOT / "data" / "wc2026.duckdb"
DEFAULT_MASTER = ROOT / "db" / "masters" / "players.csv"
FUZZY_THRESHOLD = 90


@dataclass
class SourceConfig:
    """Describes how one raw stats table feeds into the matching pipeline."""
    name: str                       # short name used for staging/quarantine table suffix
    raw_table: str                  # "raw.<name>"
    name_col: str                   # column holding the player display name
    country_col: Optional[str]      # column holding country (national team or nationality); None if not available
    club_col: Optional[str]         # column holding club name; None if not relevant
    understat_id_col: Optional[str] # column holding Understat's internal player_id; None for non-Understat


SOURCES = [
    SourceConfig(
        name="sb_player_summary",
        raw_table="raw.sb_player_summary",
        name_col="player",
        country_col="team",
        club_col=None,
        understat_id_col=None,
    ),
    SourceConfig(
        name="sb_player_stats_pedigree",
        raw_table="raw.sb_player_stats_pedigree",
        name_col="player",
        country_col="team",
        club_col=None,
        understat_id_col=None,
    ),
    SourceConfig(
        name="understat_player_xg",
        raw_table="raw.understat_player_xg",
        name_col="player",
        country_col="nationality",
        club_col="last_team",
        understat_id_col="player_id",
    ),
    SourceConfig(
        name="understat_2526_players",
        raw_table="raw.understat_2526_players",
        name_col="player",
        country_col=None,         # this parquet has no nationality column
        club_col="club",
        understat_id_col=None,    # this parquet has no understat player_id either
    ),
]


def resolve_player_id(
    src_name: str,
    src_country: Optional[str],
    src_club: Optional[str],
    src_understat_id: Optional[str],
    dim_idx: dict,
    dim_by_understat_id: dict,
    dim_normalized_lookup: dict,
    norm_names_pool: list,
) -> tuple[Optional[str], str, str]:
    """Run the tiered matching algorithm. Returns (player_id, tier, reason)."""
    norm = normalize(src_name)
    if not norm:
        return None, "none", "empty_name"

    # Tier 0 — Understat ID cached on dim
    if src_understat_id and src_understat_id in dim_by_understat_id:
        return dim_by_understat_id[src_understat_id], "tier0", "understat_id"

    cc = normalize_country(src_country) if src_country else None

    # Tier 1 (DOB) — dormant in v1, no birth_year on stats side
    # (placeholder; left empty until rosters drop)

    # Tier 2 — exact (normalized_name, country_code)
    if cc:
        candidates = dim_normalized_lookup.get((norm, cc), [])
        if len(candidates) == 1:
            return candidates[0], "tier2", "exact_name_country"
        if len(candidates) > 1:
            return None, "none", f"ambiguous_tier2_{len(candidates)}"

    # Tier 3 — exact (normalized_name, current_club) when country missing
    if not cc and src_club:
        # Look up by (norm_name, current_club) — need a different index
        # Build on the fly: scan dim_idx items (small dim ~1,300 rows)
        hits = [
            pid for pid, row in dim_idx.items()
            if row["normalized_name"] == norm
            and row.get("current_club", "").lower() == src_club.lower()
        ]
        if len(hits) == 1:
            return hits[0], "tier3", "exact_name_club"
        if len(hits) > 1:
            return None, "none", f"ambiguous_tier3_{len(hits)}"

    # Tier 4 — fuzzy ≥90 + context
    matches = process.extract(
        norm, norm_names_pool, scorer=fuzz.token_set_ratio,
        score_cutoff=FUZZY_THRESHOLD, limit=10,
    )
    if not matches:
        return None, "none", "no_match"

    with_context = []
    for matched_name, score, _idx in matches:
        # All players with this normalized name (could be multiple if dupes; rare)
        for pid, row in dim_idx.items():
            if row["normalized_name"] != matched_name:
                continue
            shared_country = cc and row.get("country_code") == cc
            shared_club = src_club and row.get("current_club", "").lower() == (src_club or "").lower()
            if shared_country or shared_club:
                with_context.append(pid)

    if len(set(with_context)) == 1:
        return with_context[0], "tier4", "fuzzy_with_context"
    if len(set(with_context)) > 1:
        return None, "none", f"ambiguous_tier4_{len(set(with_context))}"
    return None, "none", "no_match"


def load_dim_player(con: duckdb.DuckDBPyConnection) -> tuple[dict, dict, dict, list]:
    """Load dim_player into in-memory indexes used by resolve_player_id.

    Returns:
        dim_idx              {player_id: row_dict}
        dim_by_understat_id  {understat_id: player_id}
        dim_normalized_lookup  {(normalized_name, country_code): [player_id, ...]}
        norm_names_pool      [list of normalized_name strings, for fuzzy matching]
    """
    df = con.sql("SELECT * FROM curated.dim_player").df()
    dim_idx: dict[str, dict] = {}
    dim_by_understat_id: dict[str, str] = {}
    dim_normalized_lookup: dict[tuple[str, str], list[str]] = {}
    norm_names_pool: list[str] = []

    for _, row in df.iterrows():
        pid = row["player_id"]
        row_data = {
            "normalized_name": row.get("normalized_name") or "",
            "country_code": row.get("country_code") or "",
            "current_club": row.get("current_club") or "",
        }
        dim_idx[pid] = row_data
        norm_names_pool.append(row_data["normalized_name"])
        understat_id = row.get("understat_id")
        if understat_id and str(understat_id) != "nan":
            dim_by_understat_id[str(understat_id)] = pid
        key = (row_data["normalized_name"], row_data["country_code"])
        dim_normalized_lookup.setdefault(key, []).append(pid)

    return dim_idx, dim_by_understat_id, dim_normalized_lookup, norm_names_pool


def match_source(
    con: duckdb.DuckDBPyConnection,
    cfg: SourceConfig,
    dim_idx: dict,
    dim_by_understat_id: dict,
    dim_normalized_lookup: dict,
    norm_names_pool: list,
    today: str,
) -> dict:
    """Match one raw stats source. Writes staging.matched_<name> and
    quarantine.unmatched_<name>. Returns stats dict."""
    raw_df = con.sql(f"SELECT * FROM {cfg.raw_table}").df()
    if raw_df.empty:
        return {"name": cfg.name, "total": 0, "matched": 0, "quarantined": 0}

    player_ids: list[Optional[str]] = []
    tiers: list[str] = []
    reasons: list[str] = []
    tier_counts: dict[str, int] = {}

    for _, row in raw_df.iterrows():
        src_name = row.get(cfg.name_col)
        src_country = row.get(cfg.country_col) if cfg.country_col else None
        src_club = row.get(cfg.club_col) if cfg.club_col else None
        src_uid = row.get(cfg.understat_id_col) if cfg.understat_id_col else None
        if src_uid is not None:
            src_uid = str(src_uid) if str(src_uid) != "nan" else None
        pid, tier, reason = resolve_player_id(
            src_name, src_country, src_club, src_uid,
            dim_idx, dim_by_understat_id, dim_normalized_lookup, norm_names_pool,
        )
        player_ids.append(pid)
        tiers.append(tier)
        reasons.append(reason)
        tier_counts[tier] = tier_counts.get(tier, 0) + 1

    raw_df = raw_df.copy()
    raw_df["player_id"] = player_ids
    raw_df["match_tier"] = tiers
    raw_df["match_reason"] = reasons
    raw_df["as_of_date"] = today

    # For Understat sources, the raw table already has a column named
    # 'player_id' — rename to avoid collision before writing.
    if cfg.understat_id_col == "player_id":
        # Pull the renamed column up: source's player_id becomes
        # 'understat_source_id'; our resolved player_id replaces it.
        # We need to do this carefully — the column 'player_id' both
        # came from the source AND is what we set above. The set above
        # overwrote it. Restore from the original raw_df.
        original_raw = con.sql(f"SELECT * FROM {cfg.raw_table}").df()
        raw_df.insert(0, "understat_source_id", original_raw["player_id"].astype(str))

    matched_df = raw_df[raw_df["player_id"].notna()].copy()
    unmatched_df = raw_df[raw_df["player_id"].isna()].drop(columns=["player_id"]).copy()

    con.execute(f"DROP TABLE IF EXISTS staging.matched_{cfg.name}")
    if not matched_df.empty:
        con.execute(f"CREATE TABLE staging.matched_{cfg.name} AS SELECT * FROM matched_df")
    else:
        # Create empty table with the right schema
        con.execute(
            f"CREATE TABLE staging.matched_{cfg.name} AS SELECT * FROM matched_df WHERE 1=0"
        )

    con.execute(f"DROP TABLE IF EXISTS quarantine.unmatched_{cfg.name}")
    if not unmatched_df.empty:
        con.execute(f"CREATE TABLE quarantine.unmatched_{cfg.name} AS SELECT * FROM unmatched_df")
    else:
        con.execute(
            f"CREATE TABLE quarantine.unmatched_{cfg.name} AS SELECT * FROM unmatched_df WHERE 1=0"
        )

    stats = {
        "name": cfg.name,
        "total": len(raw_df),
        "matched": len(matched_df),
        "quarantined": len(unmatched_df),
        "tier_counts": tier_counts,
    }
    return stats


def update_dim_player_source_names(
    con: duckdb.DuckDBPyConnection, master_path: Path
) -> int:
    """For each matched source, set the source-specific name/ID column on
    dim_player. Then write back to the master CSV.

    Returns: count of dim_player rows updated.
    """
    updates_by_player: dict[str, dict[str, str]] = {}

    # StatsBomb name from sb_player_summary matches
    rows = con.sql(
        "SELECT DISTINCT player_id, player "
        "FROM staging.matched_sb_player_summary "
        "WHERE player_id IS NOT NULL"
    ).fetchall()
    for pid, name in rows:
        updates_by_player.setdefault(pid, {})["statsbomb_name"] = name

    # Understat name + id from understat_player_xg matches
    rows = con.sql(
        "SELECT DISTINCT player_id, player, understat_source_id "
        "FROM staging.matched_understat_player_xg "
        "WHERE player_id IS NOT NULL"
    ).fetchall()
    for pid, name, uid in rows:
        d = updates_by_player.setdefault(pid, {})
        d["understat_name"] = name
        if uid and str(uid) != "nan":
            # Understat IDs are integers; preserve as plain digits, no trailing ".0"
            uid_str = str(uid).strip()
            if uid_str.endswith(".0"):
                uid_str = uid_str[:-2]
            d["understat_id"] = uid_str

    if not updates_by_player:
        return 0

    # Apply updates to dim_player and write back to master CSV
    master_df = pd.read_csv(master_path, dtype="object")
    today = str(date.today())
    rows_changed = 0
    for pid, cols in updates_by_player.items():
        idx_match = master_df.index[master_df["player_id"] == pid]
        if len(idx_match) != 1:
            continue
        idx = idx_match[0]
        changed = False
        for col, val in cols.items():
            if val and str(master_df.at[idx, col] or "") != str(val):
                master_df.at[idx, col] = val
                changed = True
        if changed:
            master_df.at[idx, "last_updated_at"] = today
            rows_changed += 1

    if rows_changed:
        master_df = master_df.sort_values("player_id", kind="stable").reset_index(drop=True)
        master_df.to_csv(master_path, index=False, lineterminator="\n")

    # Also refresh curated.dim_player so the in-DB view reflects the updates
    con.execute(
        "CREATE OR REPLACE TABLE curated.dim_player AS "
        "SELECT * FROM read_csv(?, header=true, delim=',', nullstr='', columns={"
        "'player_id':'VARCHAR','display_name':'VARCHAR','normalized_name':'VARCHAR',"
        "'country_code':'VARCHAR','nation_name':'VARCHAR','birth_date':'DATE',"
        "'birth_year':'INTEGER','position':'VARCHAR','current_club':'VARCHAR',"
        "'current_league':'VARCHAR','statsbomb_name':'VARCHAR','understat_id':'VARCHAR',"
        "'understat_name':'VARCHAR','is_active':'BOOLEAN','first_seen_at':'DATE',"
        "'last_updated_at':'DATE'})",
        [str(master_path)],
    )

    return rows_changed


def parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    p.add_argument("--db-path", type=Path, default=DEFAULT_DB)
    p.add_argument("--master-path", type=Path, default=DEFAULT_MASTER)
    p.add_argument(
        "--no-master-writeback",
        action="store_true",
        help="Skip writing matched source names back to db/masters/players.csv",
    )
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    today = str(date.today())

    if not args.db_path.exists():
        print(f"ERROR: DB not found: {args.db_path}. Run tools/build_duckdb.py first.", file=sys.stderr)
        return 1

    con = duckdb.connect(str(args.db_path))
    try:
        con.execute("CREATE SCHEMA IF NOT EXISTS staging")
        con.execute("CREATE SCHEMA IF NOT EXISTS quarantine")

        dim_idx, dim_by_uid, dim_lookup, names_pool = load_dim_player(con)
        print(f"[match] loaded dim_player: {len(dim_idx)} players")

        all_stats = []
        for cfg in SOURCES:
            stats = match_source(con, cfg, dim_idx, dim_by_uid, dim_lookup, names_pool, today)
            all_stats.append(stats)
            tc = stats.get("tier_counts", {})
            tc_str = " ".join(f"{k}={v}" for k, v in sorted(tc.items()))
            pct = (100.0 * stats["matched"] / stats["total"]) if stats["total"] else 0.0
            print(
                f"[match] {cfg.name:<26} {stats['matched']:>5}/{stats['total']:<5} "
                f"matched ({pct:.0f}%) | quarantine={stats['quarantined']:<5} | {tc_str}"
            )

        if not args.no_master_writeback:
            changed = update_dim_player_source_names(con, args.master_path)
            print(f"[match] master writeback: {changed} dim_player rows updated")
        else:
            print("[match] master writeback skipped (--no-master-writeback)")

    finally:
        con.close()

    return 0


if __name__ == "__main__":
    sys.exit(main())
