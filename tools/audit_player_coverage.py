#!/usr/bin/env python3
"""
Audit per-nation player-data coverage.

Reads `data/derived/squad_xg_ratings.parquet` (the joined player-grain table)
and emits `data/derived/player_coverage_report.csv` with one row per nation:

    nation                  FIFA-3 or display name
    players                 squad player count
    matched_to_club         count with Understat club xG matched
    match_rate              matched_to_club / players
    national_minutes        sum of national-team minutes across squad
    low_minutes_players     count below LOW_MINUTES_THRESHOLD
    missing_club_players    count without Understat club xG
    stale_players           count with no 2024-25 club minutes

Read-only on inputs. Idempotent: same input + same code = byte-identical output.
Thresholds documented below. Changing them is a methodology change requiring
a PR; it does not trigger the refinement-loop because no model output changes.

Usage:
    python3 tools/audit_player_coverage.py

Owned by the Coverage Audit role:
    docs/agents/quality-coverage-audit.md
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
SQUAD_XG = ROOT / "data" / "derived" / "squad_xg_ratings.parquet"
OUTPUT = ROOT / "data" / "derived" / "player_coverage_report.csv"

# A player is "low-minutes" if their national-team sample is below this.
# Tied to the Bayesian shrinkage threshold in tools/build_squad_xg_ratings.py
# (MIN_RELIABLE_MINS = 180) so the audit and the modeling layer agree on
# what counts as a small sample.
LOW_MINUTES_THRESHOLD = 180

# Column name for current-season club minutes. Update this when the project
# rolls forward to the next season's parquet column.
CLUB_MINUTES_COLUMN = "club_minutes_2425"


def load_squad_xg(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(
            f"Input parquet not found: {path}. "
            f"Run tools/build_squad_xg_ratings.py first."
        )
    df = pd.read_parquet(path)
    if df.empty:
        raise ValueError(f"Input parquet is empty: {path}")
    required = {"nation", "player", "found_in_understat", "nat_minutes"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(
            f"Input parquet missing required columns: {sorted(missing)}. "
            f"Got: {sorted(df.columns)}"
        )
    return df


def audit(df: pd.DataFrame) -> pd.DataFrame:
    has_club_minutes = (
        df[CLUB_MINUTES_COLUMN].fillna(0).astype(float) > 0
        if CLUB_MINUTES_COLUMN in df.columns
        else pd.Series(False, index=df.index)
    )

    df = df.assign(
        _matched=df["found_in_understat"].fillna(False).astype(bool),
        _low_min=df["nat_minutes"].fillna(0).astype(float) < LOW_MINUTES_THRESHOLD,
        _has_recent_club=has_club_minutes,
    )

    grouped = df.groupby("nation", as_index=False, sort=True).agg(
        players=("player", "count"),
        matched_to_club=("_matched", "sum"),
        national_minutes=("nat_minutes", "sum"),
        low_minutes_players=("_low_min", "sum"),
    )

    missing_club = (
        df.groupby("nation", as_index=False)
        .agg(missing_club_players=("_matched", lambda s: int((~s).sum())))
    )
    stale_club = (
        df.groupby("nation", as_index=False)
        .agg(stale_players=("_has_recent_club", lambda s: int((~s).sum())))
    )

    out = (
        grouped.merge(missing_club, on="nation", how="left")
        .merge(stale_club, on="nation", how="left")
        .assign(
            match_rate=lambda d: (d["matched_to_club"] / d["players"]).round(4),
        )
    )

    out = out[
        [
            "nation",
            "players",
            "matched_to_club",
            "match_rate",
            "national_minutes",
            "low_minutes_players",
            "missing_club_players",
            "stale_players",
        ]
    ]

    int_cols = [
        "players",
        "matched_to_club",
        "low_minutes_players",
        "missing_club_players",
        "stale_players",
    ]
    out[int_cols] = out[int_cols].astype(int)
    out["national_minutes"] = out["national_minutes"].round(0).astype(int)

    return out.sort_values("nation").reset_index(drop=True)


def main() -> int:
    df = load_squad_xg(SQUAD_XG)
    report = audit(df)

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    report.to_csv(OUTPUT, index=False, lineterminator="\n")

    print(f"Wrote {len(report)} nation rows to {OUTPUT.relative_to(ROOT)}")
    print(
        f"  match_rate: min={report['match_rate'].min():.2f}, "
        f"median={report['match_rate'].median():.2f}, "
        f"max={report['match_rate'].max():.2f}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
