#!/usr/bin/env python3
"""
Build team attack ratings from 2026 Sofascore player data + WC2022 tournament history.

Blends two signals per player:
  - 2026 club xG/90   (from sofascore_2026_player_xg.parquet)  → current form
  - WC2022/Euro/Copa xG/90  (from sb_player_summary.parquet)   → tournament pedigree

Team rating = average xG/90 of top 5 players by blended score.

Saves:
  data/derived/team_attack_ratings.parquet

Usage:
  python3 tools/build_2026_ratings.py [--wc-weight 0.3] [--form-weight 0.7]
"""
import argparse, json, unicodedata, warnings
from pathlib import Path

warnings.filterwarnings("ignore")
import pandas as pd
import numpy as np

ROOT    = Path(__file__).parent.parent
DERIVED = ROOT / "data" / "derived"

MIN_MINS   = 90    # minimum 2026 minutes to use 2026 rating
MAX_XG90   = 6.0   # Sarabia rule: per-90 above this is noise
TOP_N      = 5     # top N players per team used for team rating
FALLBACK_Q = 0.25  # fallback = 25th percentile of rated teams

NATION_ALIASES = {
    "United States":  "USA",
    "Czech Republic": "Czechia",
    "Turkey":         "Türkiye",
    "England":        "England",
    "Côte d'Ivoire":  "Ivory Coast",
}


def normalize_nation(n):
    return NATION_ALIASES.get(n, n)


def strip_accents(s):
    return "".join(
        c for c in unicodedata.normalize("NFD", str(s))
        if unicodedata.category(c) != "Mn"
    ).lower().strip()


def load_2026(path):
    df = pd.read_parquet(path)
    df = df[df["minutes_2026"] >= MIN_MINS]
    df = df[df["xg_per_90"] <= MAX_XG90]
    df["name_key"] = df["name"].apply(strip_accents)
    return df


def load_wc_history(path):
    df = pd.read_parquet(path)
    df = df[df["minutes_played"] >= MIN_MINS]
    df = df[df["xg_per_90"] <= MAX_XG90]
    df["nation"] = df["team"].apply(normalize_nation)
    df["name_key"] = df["player"].apply(strip_accents)
    return df


def blend(xg_2026, xg_wc, w_form, w_wc):
    has_2026 = not np.isnan(xg_2026)
    has_wc   = not np.isnan(xg_wc)
    if has_2026 and has_wc:
        return w_form * xg_2026 + w_wc * xg_wc
    if has_2026:
        return xg_2026
    if has_wc:
        return xg_wc
    return np.nan


def main(w_form=0.7, w_wc=0.3):
    sc_path = DERIVED / "sofascore_2026_player_xg.parquet"
    sb_path = DERIVED / "sb_player_summary.parquet"

    has_sc = sc_path.exists()
    has_sb = sb_path.exists()

    print(f"2026 Sofascore data: {'yes' if has_sc else 'NOT FOUND'}")
    print(f"WC2022/Euro/Copa data: {'yes' if has_sb else 'NOT FOUND'}")
    print(f"Blend weights: form={w_form:.0%}  tournament={w_wc:.0%}\n")

    sc = load_2026(sc_path) if has_sc else pd.DataFrame()
    sb = load_wc_history(sb_path) if has_sb else pd.DataFrame()

    # Build lookup: name_key → xg_per_90
    sc_lookup = dict(zip(sc["name_key"], sc["xg_per_90"])) if not sc.empty else {}
    sc_nation  = dict(zip(sc["name_key"], sc["nation"])) if not sc.empty else {}

    # All nations in tournament
    tournament = json.loads((ROOT / "data" / "wc2026" / "tournament.json").read_text())
    wc_nations = set()
    for g in tournament["groups"]:
        for t in g["teams"]:
            wc_nations.add(t)

    team_rows = []
    coverage  = {}

    for nation in sorted(wc_nations):
        # Get all players for this nation from both sources
        players = {}  # name_key → {xg_2026, xg_wc, blended}

        # From WC history
        if not sb.empty:
            nat_sb = sb[sb["nation"] == nation]
            for _, row in nat_sb.iterrows():
                key = row["name_key"]
                players.setdefault(key, {"xg_2026": np.nan, "xg_wc": np.nan})
                players[key]["xg_wc"] = float(row["xg_per_90"])

        # From 2026 Sofascore
        if not sc.empty:
            nat_sc = sc[sc["nation"] == nation]
            for _, row in nat_sc.iterrows():
                key = row["name_key"]
                players.setdefault(key, {"xg_2026": np.nan, "xg_wc": np.nan})
                players[key]["xg_2026"] = float(row["xg_per_90"])

        # Compute blended per player
        for key in players:
            players[key]["blended"] = blend(
                players[key]["xg_2026"],
                players[key]["xg_wc"],
                w_form, w_wc
            )

        valid = [(k, v) for k, v in players.items() if not np.isnan(v["blended"])]
        valid.sort(key=lambda x: -x[1]["blended"])

        top5 = valid[:TOP_N]
        has_2026_data = sum(1 for _, v in top5 if not np.isnan(v["xg_2026"]))
        has_wc_data   = sum(1 for _, v in top5 if not np.isnan(v["xg_wc"]))

        if top5:
            attack_rating = round(np.mean([v["blended"] for _, v in top5]), 4)
            coverage[nation] = {"rated": len(valid), "top5_2026": has_2026_data, "top5_wc": has_wc_data}
        else:
            attack_rating = None
            coverage[nation] = {"rated": 0, "top5_2026": 0, "top5_wc": 0}

        team_rows.append({
            "nation":          nation,
            "attack_rating":   attack_rating,
            "players_rated":   len(valid),
            "top5_with_2026":  has_2026_data,
            "top5_with_wc":    has_wc_data,
        })

    df = pd.DataFrame(team_rows)

    # Apply fallback to nations with no rating
    rated    = df[df["attack_rating"].notna()]["attack_rating"]
    fallback = float(rated.quantile(FALLBACK_Q)) if len(rated) > 0 else 0.3
    df["attack_rating"] = df["attack_rating"].fillna(fallback)
    df["used_fallback"] = df["players_rated"] == 0

    df = df.sort_values("attack_rating", ascending=False)
    df.to_parquet(DERIVED / "team_attack_ratings.parquet", index=False)

    # Print summary
    print(f"{'Nation':<24} {'Rating':>8} {'Rated':>7} {'2026':>5} {'WC':>5} {'Fallback':>9}")
    print("-" * 62)
    for _, r in df.iterrows():
        fb = "★" if r["used_fallback"] else ""
        print(f"  {r['nation']:<22} {r['attack_rating']:>8.4f} {r['players_rated']:>7} "
              f"{r['top5_with_2026']:>5} {r['top5_with_wc']:>5} {fb:>9}")

    n_fallback = int(df["used_fallback"].sum())
    print(f"\n  Fallback value (25th pct): {fallback:.4f}")
    print(f"  Nations using fallback: {n_fallback}/48")
    print(f"\nSaved → data/derived/team_attack_ratings.parquet")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--form-weight", type=float, default=0.7)
    parser.add_argument("--wc-weight",   type=float, default=0.3)
    args = parser.parse_args()
    main(w_form=args.form_weight, w_wc=args.wc_weight)
