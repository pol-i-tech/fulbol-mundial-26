#!/usr/bin/env python3
"""
Build WC2022 team attack + defense ratings for the backtest.
Backtest-only script: all inputs are pre-WC2022 data only (no leakage).

Outputs:
  data/derived/team_attack_ratings_wc2022.parquet
  data/derived/team_defense_ratings_wc2022.parquet
  results/comparisons/wc2022-backtest/name_match_audit_wc2022.csv

Usage:
  python3 tools/build_wc2022_ratings.py
"""
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")
import numpy as np
import pandas as pd
from rapidfuzz import fuzz, process

ROOT = Path(__file__).parent.parent
DERIVED = ROOT / "data" / "derived"
RESULTS_DIR = ROOT / "results" / "comparisons" / "wc2022-backtest"

# --- Blend config (mirrors build_2026_ratings.py) ---
BLEND_CLUB = 0.7
BLEND_TOURNAMENT = 0.3
TOP_N = 5
FALLBACK_Q = 0.25       # nations with < 3 rated players get 25th-pct floor
MIN_MATCH_SCORE = 75    # rapidfuzz threshold


def simplify_name(name: str) -> str:
    """Strip accents and reduce to first+last token — matches build_squad_xg_ratings.py."""
    import unicodedata
    name = unicodedata.normalize("NFD", str(name))
    name = "".join(c for c in name if unicodedata.category(c) != "Mn")
    parts = name.strip().split()
    if len(parts) >= 2:
        return f"{parts[0]} {parts[-1]}".lower()
    return name.lower()


def fuzzy_match(name: str, candidates: list[str], threshold: int = MIN_MATCH_SCORE):
    result = process.extractOne(simplify_name(name), candidates, scorer=fuzz.token_sort_ratio)
    if result and result[1] >= threshold:
        return result[0], result[1]
    return None, 0


# ─────────────────────────────────────────────────────────────────────────────
# Attack ratings
# ─────────────────────────────────────────────────────────────────────────────

def build_attack_ratings(proxy, und, pedigree) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Fuzzy-match WC2022 squad proxy → Understat 2021/22 club xG + tournament pedigree.
    Returns (player_ratings_df, audit_df).
    """
    # Simplified name index for Understat lookup
    und["name_simple"] = und["player_name"].apply(simplify_name)
    und_names = und["name_simple"].tolist()
    und_lookup = dict(zip(und["name_simple"], und.index))

    # Simplified name index for pedigree lookup
    pedigree["name_simple"] = pedigree["player"].apply(simplify_name)
    ped_lookup = dict(zip(pedigree["name_simple"], pedigree.index))
    ped_names = pedigree["name_simple"].tolist()

    rows = []
    audit_rows = []

    for _, squad_row in proxy.iterrows():
        sb_name = squad_row["player"]
        nation = squad_row["team"]
        minutes_wc22 = squad_row["minutes_played"]

        # Match to Understat club xG
        club_match, club_score = fuzzy_match(sb_name, und_names)
        club_xg90 = np.nan
        club_team = ""
        club_league = ""
        if club_match and club_match in und_lookup:
            idx = und_lookup[club_match]
            row = und.loc[idx]
            club_xg90 = float(row["xg_per_90"])
            club_team = str(row["team"])
            club_league = str(row["league"])

        # Match to tournament pedigree
        ped_match, ped_score = fuzzy_match(sb_name, ped_names)
        tournament_xg90 = np.nan
        if ped_match and ped_match in ped_lookup:
            idx = ped_lookup[ped_match]
            tournament_xg90 = float(pedigree.loc[idx, "xg_per_90"])

        # Blend
        if not np.isnan(club_xg90) and not np.isnan(tournament_xg90):
            blended = BLEND_CLUB * club_xg90 + BLEND_TOURNAMENT * tournament_xg90
        elif not np.isnan(club_xg90):
            blended = club_xg90
        elif not np.isnan(tournament_xg90):
            blended = tournament_xg90
        else:
            blended = np.nan

        rows.append({
            "nation": nation,
            "player": sb_name,
            "club_team": club_team,
            "club_league": club_league,
            "club_xg90": round(club_xg90, 4) if not np.isnan(club_xg90) else np.nan,
            "tournament_xg90": round(tournament_xg90, 4) if not np.isnan(tournament_xg90) else np.nan,
            "blended_xg90": round(blended, 4) if not np.isnan(blended) else np.nan,
            "minutes_wc22": minutes_wc22,
        })
        audit_rows.append({
            "squad_player": sb_name,
            "nation": nation,
            "und_player_matched": club_match or "",
            "match_score": club_score,
            "club_xg90": round(club_xg90, 4) if not np.isnan(club_xg90) else np.nan,
            "threshold_passed": club_score >= MIN_MATCH_SCORE,
        })

    players_df = pd.DataFrame(rows)
    audit_df = pd.DataFrame(audit_rows)
    return players_df, audit_df


def aggregate_team_attack(players_df: pd.DataFrame) -> pd.DataFrame:
    """Aggregate to team level: top-N mean blended_xg90, fallback for sparse nations."""
    rows = []
    fallback_val = None  # computed after first pass

    per_nation = []
    for nation, grp in players_df.groupby("nation"):
        rated = grp.dropna(subset=["blended_xg90"]).sort_values("blended_xg90", ascending=False)
        top = rated.head(TOP_N)
        n_rated = len(rated)
        per_nation.append((nation, top, n_rated, len(grp)))

    # Compute fallback from nations with enough data
    all_ratings = [top["blended_xg90"].mean() for _, top, n, _ in per_nation if n >= 3]
    fallback_val = float(np.quantile(all_ratings, FALLBACK_Q)) if all_ratings else 0.5

    for nation, top, n_rated, n_total in per_nation:
        if n_rated >= 3:
            attack_rating = float(top["blended_xg90"].mean())
            used_fallback = False
        else:
            attack_rating = fallback_val
            used_fallback = True
        rows.append({
            "nation": nation,
            "attack_rating": round(attack_rating, 4),
            "players_rated": n_rated,
            "players_total": n_total,
            "used_fallback": used_fallback,
        })

    return pd.DataFrame(rows).sort_values("attack_rating", ascending=False).reset_index(drop=True)


# ─────────────────────────────────────────────────────────────────────────────
# Defense ratings
# ─────────────────────────────────────────────────────────────────────────────

def build_defense_ratings(wc2022_nations: list[str], xga_pedigree: pd.DataFrame) -> pd.DataFrame:
    """
    Build defensive ratings from tournament xGA pedigree (wc2018 + euro2020).
    Nations that never appeared get median fallback.
    Note: no club-level defensive data available for 2021/22 (Understat is offense-only).
    """
    # Average xGA/90 across competitions for nations that appeared in both
    nation_xga = (
        xga_pedigree.groupby("nation", as_index=False)
        .agg(tournament_xga=("tournament_xga_per_90", "mean"), appearances=("matches", "sum"))
    )
    nation_xga_map = dict(zip(nation_xga["nation"], nation_xga["tournament_xga"]))

    # WC2022 nation name normalization: StatsBomb names vs pedigree names
    # Build a quick fuzzy lookup
    ped_nations = list(nation_xga_map.keys())
    ped_nation_simple = {simplify_name(n): n for n in ped_nations}
    ped_simple_list = list(ped_nation_simple.keys())

    median_xga = float(np.median(list(nation_xga_map.values())))

    rows = []
    for nation in wc2022_nations:
        # Try exact match first, then fuzzy
        xga = nation_xga_map.get(nation)
        used_fallback = False
        if xga is None:
            match, score = fuzzy_match(nation, ped_simple_list, threshold=70)
            if match and match in ped_nation_simple:
                orig_name = ped_nation_simple[match]
                xga = nation_xga_map[orig_name]
            else:
                xga = median_xga
                used_fallback = True
        rows.append({
            "nation": nation,
            "defensive_rating": round(float(xga), 4),
            "tournament_xga": round(float(xga), 4),
            "club_xga_avg": np.nan,           # not available for 2021/22
            "club_sample_size": 0,
            "used_fallback": used_fallback,
        })

    return (
        pd.DataFrame(rows)
        .sort_values("defensive_rating")
        .reset_index(drop=True)
    )


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main():
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    print("Loading inputs…")
    proxy    = pd.read_parquet(DERIVED / "squad_wc2022_proxy.parquet")
    und      = pd.read_parquet(DERIVED / "understat_2122_players.parquet")
    pedigree = pd.read_parquet(DERIVED / "sb_player_summary_pre_wc22.parquet")
    xga_ped  = pd.read_parquet(DERIVED / "team_xga_pedigree.parquet")

    print(f"  Squad proxy: {len(proxy)} players, {proxy['team'].nunique()} nations")
    print(f"  Understat 2021/22: {len(und)} players")
    print(f"  Tournament pedigree: {len(pedigree)} players")
    print(f"  xGA pedigree: {len(xga_ped)} nation-competition rows")

    # ── Attack ratings ─────────────────────────────────────────────────────
    print("\nMatching players (attack)…")
    players_df, audit_df = build_attack_ratings(proxy, und, pedigree)

    audit_path = RESULTS_DIR / "name_match_audit_wc2022.csv"
    audit_df.to_csv(audit_path, index=False)

    matched = audit_df["threshold_passed"].sum()
    total = len(audit_df)
    print(f"  Match rate: {matched}/{total} ({100*matched/total:.1f}%)")

    # Big-5 nations match rate
    big5_nations = ["England","Spain","Germany","France","Brazil","Argentina"]
    b5 = audit_df[audit_df["nation"].isin(big5_nations)]
    b5_rate = b5["threshold_passed"].mean()
    print(f"  Big-5 nation match rate: {100*b5_rate:.1f}%  (target ≥70%)")

    attack_df = aggregate_team_attack(players_df)
    attack_path = DERIVED / "team_attack_ratings_wc2022.parquet"
    attack_df.to_parquet(attack_path, index=False)
    print(f"\nAttack ratings saved → {attack_path}  ({len(attack_df)} nations)")

    print("\nTop 8 attack nations:")
    print(attack_df[["nation","attack_rating","players_rated","used_fallback"]].head(8).to_string(index=False))
    print("\nBottom 5 attack nations:")
    print(attack_df[["nation","attack_rating","players_rated","used_fallback"]].tail(5).to_string(index=False))

    # ── Defense ratings ────────────────────────────────────────────────────
    wc2022_nations = sorted(proxy["team"].unique().tolist())
    defense_df = build_defense_ratings(wc2022_nations, xga_ped)
    defense_path = DERIVED / "team_defense_ratings_wc2022.parquet"
    defense_df.to_parquet(defense_path, index=False)
    print(f"\nDefense ratings saved → {defense_path}  ({len(defense_df)} nations)")

    fallback_nations = defense_df[defense_df["used_fallback"]]["nation"].tolist()
    print(f"  Nations using fallback ({len(fallback_nations)}): {fallback_nations}")

    print("\nTop 8 most defensively solid (lowest xGA conceded):")
    print(defense_df[["nation","defensive_rating","used_fallback"]].head(8).to_string(index=False))
    print("\nBottom 5 most leaky (highest xGA conceded):")
    print(defense_df[["nation","defensive_rating","used_fallback"]].tail(5).to_string(index=False))


if __name__ == "__main__":
    main()
