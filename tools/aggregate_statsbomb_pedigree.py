#!/usr/bin/env python3
"""
Aggregate StatsBomb wc2018 + euro2020 event data into pre-WC2022 pedigree parquets.
Backtest-only script: does NOT modify sb_player_stats.parquet or sb_player_summary.parquet.

Writes:
  data/derived/sb_player_stats_pedigree.parquet  -- player-level xG/shots/goals/minutes per competition
  data/derived/team_xga_pedigree.parquet         -- team-level xGA per competition

Usage:
  python3 tools/aggregate_statsbomb_pedigree.py
"""
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")
import numpy as np
import pandas as pd

ROOT = Path(__file__).parent.parent
RAW = ROOT / "data" / "raw" / "statsbomb"
DERIVED = ROOT / "data" / "derived"

COMPS = {
    "wc2018":   "data/raw/statsbomb/wc2018/events",
    "euro2020": "data/raw/statsbomb/euro2020/events",
}

# Canonical files that must NOT be touched
PROTECTED = {
    DERIVED / "sb_player_stats.parquet",
    DERIVED / "sb_player_summary.parquet",
}


def process_match_events(ev_path: Path, comp_key: str):
    """
    Parse a single match event file.

    Returns:
        player_rows  — list of per-player dicts (xg, shots, goals, minutes)
        team_xga     — dict mapping team -> xga accumulated in this match
    """
    df = pd.read_json(ev_path)

    # Identify the two teams in this match
    match_teams = df["team"].dropna().unique().tolist()

    # Shot rows only
    shot_mask = df["type"] == "Shot"
    shots_df = df[shot_mask].copy()

    # ------------------------------------------------------------------
    # Player-level aggregation
    # ------------------------------------------------------------------
    player_stats: dict[tuple, dict] = {}

    def get_player(player_name: str, team: str) -> dict:
        key = (player_name, team)
        if key not in player_stats:
            player_stats[key] = {
                "player": player_name,
                "team": team,
                "competition": comp_key,
                "season": comp_key,
                "xg_total": 0.0,
                "shots": 0,
                "goals": 0,
                # Track unique minutes as a set; convert to count at the end
                "_minutes_set": set(),
            }
        return player_stats[key]

    for _, row in df.iterrows():
        player_name = row.get("player", "")
        team = row.get("team", "")
        if not player_name or not isinstance(player_name, str) or not team:
            continue

        minute = row.get("minute")
        if pd.notna(minute):
            get_player(player_name, team)["_minutes_set"].add(int(minute))

        etype = row.get("type", "")
        if etype == "Shot":
            xg_val = float(row.get("shot_statsbomb_xg", 0) or 0)
            outcome = row.get("shot_outcome", "") or ""
            p = get_player(player_name, team)
            p["shots"] += 1
            p["xg_total"] += xg_val
            if outcome == "Goal":
                p["goals"] += 1

    # Materialise the minutes count and remove the set
    player_rows = []
    for stats in player_stats.values():
        minutes_set = stats.pop("_minutes_set")
        stats["minutes"] = len(minutes_set) if minutes_set else 1
        player_rows.append(stats)

    # ------------------------------------------------------------------
    # Team xGA aggregation
    # ------------------------------------------------------------------
    # For each shot, xGA is credited to the NON-shooting team in this match.
    team_xga: dict[str, float] = {t: 0.0 for t in match_teams}
    team_shots_faced: dict[str, int] = {t: 0 for t in match_teams}

    for _, shot_row in shots_df.iterrows():
        shooting_team = shot_row.get("team", "")
        xg_val = float(shot_row.get("shot_statsbomb_xg", 0) or 0)
        if not shooting_team:
            continue
        for t in match_teams:
            if t != shooting_team:
                team_xga[t] = team_xga.get(t, 0.0) + xg_val
                team_shots_faced[t] = team_shots_faced.get(t, 0) + 1

    return player_rows, team_xga


def main():
    # Sanity-check: protected files must not be overwritten
    for protected in PROTECTED:
        assert protected != DERIVED / "sb_player_stats_pedigree.parquet", \
            "BUG: writing to a protected path"
        assert protected != DERIVED / "team_xga_pedigree.parquet", \
            "BUG: writing to a protected path"

    all_player_rows: list[dict] = []

    # team_match_counts[comp][team] = number of matches
    team_match_counts: dict[str, dict[str, int]] = {}
    # team_xga_totals[comp][team] = total xGA
    team_xga_totals: dict[str, dict[str, float]] = {}

    for comp_key, events_rel_path in COMPS.items():
        events_dir = ROOT / events_rel_path
        if not events_dir.exists():
            print(f"[skip] {comp_key} — directory not found: {events_dir}")
            continue

        event_files = sorted(events_dir.glob("*.json"))
        print(f"\n{comp_key}: {len(event_files)} match files")

        team_match_counts[comp_key] = {}
        team_xga_totals[comp_key] = {}

        for ev_path in event_files:
            player_rows, team_xga = process_match_events(ev_path, comp_key)
            all_player_rows.extend(player_rows)

            # Accumulate team xGA and match count
            for team, xga in team_xga.items():
                team_xga_totals[comp_key][team] = \
                    team_xga_totals[comp_key].get(team, 0.0) + xga
                team_match_counts[comp_key][team] = \
                    team_match_counts[comp_key].get(team, 0) + 1

        n_teams = len(team_xga_totals[comp_key])
        print(f"  Teams tracked: {n_teams}")

    # ------------------------------------------------------------------
    # Build player pedigree parquet
    # ------------------------------------------------------------------
    player_df = pd.DataFrame(all_player_rows)

    # Aggregate across all matches per (player, team, competition)
    player_agg = (
        player_df.groupby(["player", "team", "competition", "season"])
        .agg(
            xg_total=("xg_total", "sum"),
            shots=("shots", "sum"),
            goals=("goals", "sum"),
            minutes=("minutes", "sum"),
        )
        .reset_index()
    )

    # Keep only players who took at least one shot
    player_agg = player_agg[player_agg["shots"] > 0].copy()

    # Derived rate
    player_agg["xg_per_90"] = (
        player_agg["xg_total"] / player_agg["minutes"].clip(lower=1) * 90
    ).round(4)

    # Leakage assertion: no wc2022 rows
    assert player_agg[player_agg["season"] == "wc2022"].empty, \
        "LEAKAGE: wc2022 season rows found in pedigree file!"

    player_pedigree_path = DERIVED / "sb_player_stats_pedigree.parquet"
    player_agg.to_parquet(player_pedigree_path, index=False)
    print(f"\n[saved] sb_player_stats_pedigree.parquet  — {len(player_agg)} rows")

    # ------------------------------------------------------------------
    # Build team xGA pedigree parquet
    # ------------------------------------------------------------------
    team_rows: list[dict] = []
    for comp_key in COMPS:
        if comp_key not in team_xga_totals:
            continue
        for team, xga in team_xga_totals[comp_key].items():
            n_matches = team_match_counts[comp_key].get(team, 0)
            total_minutes = n_matches * 90
            xga_per_90 = xga / (total_minutes / 90) if total_minutes > 0 else np.nan
            team_rows.append({
                "nation": team,
                "matches": n_matches,
                "total_xg_conceded": round(xga, 4),
                "total_minutes": total_minutes,
                "pressures_per_90": np.nan,   # Not parsed — mirrors defensive_ratings_tournament schema
                "tournament_xga_per_90": round(xga_per_90, 6),
                "competition": comp_key,
            })

    team_df = pd.DataFrame(team_rows).sort_values(["competition", "nation"]).reset_index(drop=True)

    team_pedigree_path = DERIVED / "team_xga_pedigree.parquet"
    team_df.to_parquet(team_pedigree_path, index=False)
    print(f"[saved] team_xga_pedigree.parquet         — {len(team_df)} rows ({team_df['nation'].nunique()} unique nations)")

    # ------------------------------------------------------------------
    # Audit output
    # ------------------------------------------------------------------
    print("\n--- AUDIT ---")
    for comp in COMPS:
        comp_players = player_agg[player_agg["competition"] == comp]
        comp_teams = team_df[team_df["competition"] == comp]
        print(f"\n{comp}:")
        print(f"  Players with shots: {len(comp_players)}")
        print(f"  Teams (xGA): {len(comp_teams)}")

    print("\nTop 5 players by xG (across both competitions):")
    top5 = player_agg.nlargest(5, "xg_total")[
        ["player", "team", "competition", "shots", "goals", "xg_total", "xg_per_90"]
    ]
    print(top5.to_string(index=False))

    print("\nTop 5 most-defensively-tested nations (highest xGA conceded):")
    top5_def = team_df.nlargest(5, "total_xg_conceded")[
        ["nation", "competition", "matches", "total_xg_conceded", "tournament_xga_per_90"]
    ]
    print(top5_def.to_string(index=False))

    print("\nLeakage check (wc2022 rows in player pedigree):", player_agg[player_agg["season"] == "wc2022"].shape[0], "— PASS" if player_agg[player_agg["season"] == "wc2022"].empty else "— FAIL")

    print("\nDone.")


if __name__ == "__main__":
    main()
