#!/usr/bin/env python3
"""
Build pre-WC2022 club xG ratings from Understat 2021/22 season data.
Backtest-only: leakage-free (season ends May 2022, before WC2022 Nov 2022).

Usage:
  python3 tools/build_wc2022_player_xg.py
"""

import json
import logging
import unicodedata
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")
import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
log = logging.getLogger(__name__)

ROOT = Path(__file__).parent.parent
RAW_DIR = ROOT / "data" / "raw" / "understat"
DERIVED = ROOT / "data" / "derived"

LEAGUE_XG_FACTOR: dict[str, float] = {
    "EPL": 1.00,
    "La_liga": 0.98,
    "Bundesliga": 0.97,
    "Serie_A": 0.94,
    "Ligue_1": 0.91,
}

LEAGUES = list(LEAGUE_XG_FACTOR.keys())

XG_PER_90_CAP = 6.0
MIN_MINUTES = 200
SEASON = 2021


def strip_accents(name: str) -> str:
    """Strip accents — same approach as build_squad_xg_ratings.py simplify_name()."""
    return (
        unicodedata.normalize("NFKD", name)
        .encode("ascii", "ignore")
        .decode()
    )


def load_league(league: str) -> pd.DataFrame | None:
    """Load a single league JSON file; return None (with warning) if missing."""
    path = RAW_DIR / f"{league}_2021_players.json"
    if not path.exists():
        log.warning("File not found, skipping: %s", path)
        return None

    with path.open() as f:
        records = json.load(f)

    df = pd.DataFrame(records)
    df["league"] = league
    return df


def process_leagues() -> pd.DataFrame:
    """Load all leagues, apply adjustments, deduplicate, return final DataFrame."""
    frames = []
    for league in LEAGUES:
        df = load_league(league)
        if df is None:
            continue
        frames.append(df)

    if not frames:
        raise RuntimeError("No league data loaded — nothing to process.")

    raw = pd.concat(frames, ignore_index=True)

    # Cast numeric columns (all arrive as strings in Understat JSON)
    for col in ("time", "xG", "npxG", "shots"):
        raw[col] = pd.to_numeric(raw[col], errors="coerce").fillna(0.0)

    # Filter: minimum minutes played
    raw = raw[raw["time"] >= MIN_MINUTES].copy()

    # Apply league quality factor
    raw["xg_factor"] = raw["league"].map(LEAGUE_XG_FACTOR)
    raw["xg_adjusted"] = raw["xG"] * raw["xg_factor"]

    # Compute xG per 90, then cap (Sarabia cap)
    raw["xg_per_90"] = raw["xg_adjusted"] / (raw["time"] / 90.0)
    raw["xg_per_90"] = raw["xg_per_90"].clip(upper=XG_PER_90_CAP)

    # Winter transfer deduplication: keep highest-minutes row per player id
    raw = (
        raw.sort_values("time", ascending=False)
        .drop_duplicates(subset="id", keep="first")
        .copy()
    )

    # Normalise player names (strip accents)
    raw["player_name_norm"] = raw["player_name"].apply(strip_accents)

    # Build final output schema
    out = pd.DataFrame({
        "player_id":        raw["id"].astype(str),
        "player_name":      raw["player_name"],
        "player_name_norm": raw["player_name_norm"],
        "league":           raw["league"],
        "team":             raw["team_title"],
        "minutes":          raw["time"].astype(int),
        "xg_raw":           raw["xG"].round(4),
        "xg_adjusted":      raw["xg_adjusted"].round(4),
        "xg_per_90":        raw["xg_per_90"].round(4),
        "npxg":             raw["npxG"].round(4),
        "shots":            raw["shots"].astype(int),
        "position":         raw["position"],
        "season":           SEASON,
    })

    out = out.sort_values("xg_per_90", ascending=False).reset_index(drop=True)
    return out


def audit(df: pd.DataFrame) -> None:
    """Print audit table to stdout."""
    sep = "=" * 65

    print(f"\n{sep}")
    print("PLAYER COUNT PER LEAGUE")
    print(sep)
    counts = df.groupby("league").size().sort_values(ascending=False)
    for league, n in counts.items():
        print(f"  {league:<15} {n:>4} players")
    print(f"  {'TOTAL':<15} {len(df):>4} players")

    print(f"\n{sep}")
    print("TOP 5 BY xg_per_90  (expect Lewandowski ~1.15)")
    print(sep)
    cols = ["player_name", "team", "league", "minutes", "xg_raw", "xg_adjusted", "xg_per_90"]
    print(df[cols].head(5).to_string(index=False))

    print(f"\n{sep}")
    print("xg_per_90 DISTRIBUTION STATS")
    print(sep)
    stats = df["xg_per_90"].describe(percentiles=[0.25, 0.50, 0.75, 0.90, 0.95, 0.99])
    for k, v in stats.items():
        print(f"  {k:<8} {v:.4f}")

    print(f"\n{sep}")
    print("SANITY CHECK — KNOWN PLAYERS")
    print(sep)
    targets = ["Lewandowski", "Benzema", "Salah", "Haaland", "Mbappe"]
    hits = df[df["player_name_norm"].str.contains("|".join(targets), case=False, na=False)]
    print(hits[["player_name", "team", "league", "minutes", "xg_raw", "xg_per_90"]].to_string(index=False))

    print()


def build_squad_proxy() -> pd.DataFrame:
    """
    Extract WC2022 squad proxy from sb_player_stats.parquet.
    Uses post-hoc match appearances (not pre-announced squads).
    Leakage is bounded: we use WHO played, not their WC2022 xG performance.
    """
    stats_path = DERIVED / "sb_player_stats.parquet"
    df = pd.read_parquet(stats_path)

    # Leakage guard: we want wc2022 rows (squad membership only, not performance)
    wc22 = df[df["season"] == "wc2022"].copy()
    assert len(wc22) > 0, "No wc2022 rows found in sb_player_stats.parquet"

    proxy = (
        wc22.groupby(["player", "team"], as_index=False)["minutes_played"]
        .sum()
        .query("minutes_played > 0")
        .sort_values(["team", "minutes_played"], ascending=[True, False])
        .reset_index(drop=True)
    )
    return proxy


def build_tournament_pedigree_summary() -> pd.DataFrame:
    """
    Aggregate sb_player_stats_pedigree.parquet (wc2018 + euro2020) into
    a per-player summary for the WC2022 rating builder.
    """
    pedigree_path = DERIVED / "sb_player_stats_pedigree.parquet"
    df = pd.read_parquet(pedigree_path)

    # Leakage check
    assert df[df["season"] == "wc2022"].empty, "LEAKAGE: wc2022 rows found in pedigree file!"

    summary = (
        df.groupby(["player", "team"], as_index=False)
        .agg(
            xg_total=("xg_total", "sum"),
            shots=("shots", "sum"),
            goals=("goals", "sum"),
            minutes=("minutes", "sum"),
        )
    )
    summary["xg_per_90"] = (summary["xg_total"] / (summary["minutes"] / 90)).round(4)
    # Clamp outliers
    summary["xg_per_90"] = summary["xg_per_90"].clip(upper=XG_PER_90_CAP)
    summary = summary.sort_values("xg_total", ascending=False).reset_index(drop=True)
    return summary


def main() -> None:
    DERIVED.mkdir(parents=True, exist_ok=True)

    # ── Unit 2: Understat 2021/22 club xG ──────────────────────────────────
    log.info("Loading and processing 2021/22 Understat league files…")
    df = process_leagues()
    out_path = DERIVED / "understat_2122_players.parquet"
    df.to_parquet(out_path, index=False)
    log.info("Saved → %s  (%d rows)", out_path, len(df))
    audit(df)

    # ── Unit 1a: WC2022 squad proxy ────────────────────────────────────────
    log.info("Building WC2022 squad proxy from sb_player_stats.parquet…")
    proxy = build_squad_proxy()
    proxy_path = DERIVED / "squad_wc2022_proxy.parquet"
    proxy.to_parquet(proxy_path, index=False)
    log.info("Squad proxy → %s  (%d rows, %d nations)", proxy_path, len(proxy),
             proxy["team"].nunique())
    print(f"\nSquad proxy: {proxy['team'].nunique()} nations, avg {len(proxy)/proxy['team'].nunique():.1f} players/nation")
    print(proxy.groupby("team").size().sort_values().tail(5).to_string())

    # ── Unit 1b: Pre-WC22 tournament pedigree summary ──────────────────────
    log.info("Building tournament pedigree summary (wc2018 + euro2020)…")
    pedigree = build_tournament_pedigree_summary()
    pedigree_path = DERIVED / "sb_player_summary_pre_wc22.parquet"
    pedigree.to_parquet(pedigree_path, index=False)
    log.info("Pedigree summary → %s  (%d players)", pedigree_path, len(pedigree))
    print(f"\nTournament pedigree: {len(pedigree)} players")
    print("Top 5 by total xG:")
    print(pedigree[["player","team","xg_total","shots","goals","xg_per_90"]].head(5).to_string(index=False))


if __name__ == "__main__":
    main()
