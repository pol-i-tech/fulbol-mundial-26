#!/usr/bin/env python3
"""
Recompute team ATTACK ratings for all 48 WC2026 qualifiers from their real 2026
rosters, on one consistent scale.

The base `build_squad_xg_ratings.py` pools 2022-24 StatsBomb tournament players —
stale personnel, and only 33 of 48 qualifiers even get a rating (the rest fall
back to a median). This script instead drives the pool from the 2026 ESPN rosters
(`wc2026_squads_clean.parquet`, with each player's current club), attaches:
  - recent club xG  (Understat 2024-25, fuzzy name)
  - national-team xG (StatsBomb tournaments, fuzzy name within the nation)
and re-derives the attack proxy (mean blended xG/90 of the top-5 attackers),
reusing the base script's Bayesian shrinkage.

Why ALL qualifiers, not just the top teams: the engine compares attack ratings
across the 48 qualifiers, so a partial recompute would mix two scales and corrupt
the comparison. Recomputing everyone keeps one consistent scale.

PATCHES only `data/derived/team_attack_ratings.parquet` (the qualifier rows) —
the sole engine input (→ raw.team_attack_ratings → curated.fact_team_rating).
Non-qualifier rows are kept byte-identical. Defense ratings, the player MDM tables
(fact_player_xg_per_90), and squad_xg_ratings.parquet are NOT touched.

Usage:
  python3 tools/build_squad_xg_2026.py
"""
from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

from build_squad_xg_ratings import (  # noqa: E402
    simplify_name, MIN_RELIABLE_MINS, PRIOR_MINS, PRIOR_XG90,
)
from rapidfuzz import fuzz, process  # noqa: E402

DERIVED = ROOT / "data" / "derived"
DB = ROOT / "data" / "wc2026.duckdb"

CLUB_MATCH_THRESHOLD = 80
NAT_MATCH_THRESHOLD = 80


def _best(simple_query, choices, threshold):
    if not choices:
        return None
    r = process.extractOne(simple_query, choices, scorer=fuzz.token_sort_ratio)
    return r[0] if (r and r[1] >= threshold) else None


def build_team_players(label, roster, sb_team, und, und_names, und_lookup):
    sb_team = sb_team.copy()
    sb_team["name_simple"] = sb_team["player"].apply(simplify_name)
    sb_names = sb_team["name_simple"].tolist()
    sb_lookup = dict(zip(sb_team["name_simple"], sb_team.index))

    rows = []
    for _, p in roster.iterrows():
        simple = simplify_name(p["display_name"])

        nat = dict(xg=0.0, mins=0, matches=0, kp=0.0, pp=0.0, pr=0.0)
        m = _best(simple, sb_names, NAT_MATCH_THRESHOLD)
        if m is not None:
            r = sb_team.loc[sb_lookup[m]]
            nat = dict(xg=float(r["xg_per_90"]), mins=int(r["minutes_played"]),
                       matches=int(r["matches"]), kp=float(r["key_passes_per_90"]),
                       pp=float(r["prog_passes_per_90"]), pr=float(r["pressures_per_90"]))

        club_xg = np.nan
        cm = _best(simple, und_names, CLUB_MATCH_THRESHOLD)
        if cm is not None:
            club_xg = float(und.loc[und_lookup[cm], "xg_per_90"])

        if nat["mins"] < MIN_RELIABLE_MINS:
            eff_nat = (nat["mins"] * nat["xg"] + PRIOR_MINS * PRIOR_XG90) \
                / (nat["mins"] + PRIOR_MINS)
        else:
            eff_nat = nat["xg"]
        blended = 0.4 * eff_nat + 0.6 * club_xg if not np.isnan(club_xg) else eff_nat

        rows.append(dict(
            blended_xg90=blended, nat_xg_per_90=nat["xg"], club_xg_per_90=club_xg,
            nat_key_passes_per_90=nat["kp"], nat_prog_passes_per_90=nat["pp"],
            nat_pressures_per_90=nat["pr"], nat_minutes=nat["mins"],
            found=not np.isnan(club_xg),
        ))
    return pd.DataFrame(rows)


def team_aggregate(label, grp):
    top_attack = grp.nlargest(5, "blended_xg90")
    top_press = grp.nlargest(8, "nat_pressures_per_90")
    nat_have = grp[grp["nat_minutes"] > 0]
    club_vals = top_attack["club_xg_per_90"].dropna()
    return {
        "nation": label,
        "squad_players": len(grp),
        "matched_to_club": int(grp["found"].sum()),
        "attack_rating": round(top_attack["blended_xg90"].mean(), 4),
        "attack_nat_only": round(top_attack["nat_xg_per_90"].mean(), 4),
        "attack_club_only": round(club_vals.mean(), 4) if len(club_vals) else None,
        "creativity_rating": round(nat_have["nat_key_passes_per_90"].mean(), 4)
        if len(nat_have) else 0.0,
        "progressive_pass_rating": round(nat_have["nat_prog_passes_per_90"].mean(), 4)
        if len(nat_have) else 0.0,
        "press_intensity": round(top_press["nat_pressures_per_90"].mean(), 4),
    }


def load_label_maps(team_old):
    """From the DB: qualifier set, FIFA3→StatsBomb labels, FIFA3→output label."""
    con = duckdb.connect(str(DB), read_only=True)
    tnr = con.execute("SELECT nation_name, team_code FROM staging.team_name_resolution").fetchall()
    qual = {r[0] for r in con.execute(
        "SELECT team_code FROM curated.dim_team_current WHERE is_wc2026_qualifier").fetchall()}
    dim = dict(con.execute("SELECT team_code, team_name FROM curated.dim_team_current").fetchall())
    con.close()

    code2sblabels = defaultdict(set)
    name2code = {}
    for name, code in tnr:
        code2sblabels[code].add(name)
        name2code[name] = code

    # Output label per code: reuse the existing team_attack label when present
    # (so the build_duckdb name-resolution join is unchanged); else dim team_name.
    old_label_for_code = {}
    for lbl in team_old["nation"]:
        c = name2code.get(lbl)
        if c and c not in old_label_for_code:
            old_label_for_code[c] = lbl
    code2label = {c: old_label_for_code.get(c, dim.get(c)) for c in qual}
    return qual, code2sblabels, code2label


def main():
    squads = pd.read_parquet(DERIVED / "wc2026_squads_clean.parquet")
    und_raw = pd.read_parquet(DERIVED / "understat_player_xg_raw.parquet")
    sb = pd.read_parquet(DERIVED / "sb_player_summary.parquet")
    team_old = pd.read_parquet(DERIVED / "team_attack_ratings.parquet")

    und = und_raw[(und_raw["season"] == 2024) & (und_raw["time"] >= 200)].copy()
    und["name_simple"] = und["player"].apply(simplify_name)
    und_names = und["name_simple"].tolist()
    und_lookup = dict(zip(und["name_simple"], und.index))

    qual, code2sblabels, code2label = load_label_maps(team_old)

    new_teams = []
    print(f"Recomputing {len(qual)} WC2026 qualifiers from 2026 rosters...\n")
    for code in sorted(qual):
        label = code2label.get(code)
        roster = squads[squads["country_code"] == code]
        if roster.empty or label is None:
            print(f"  !! {code}: no roster/label — skipped (median fallback applies)")
            continue
        sb_team = sb[sb["team"].isin(code2sblabels[code])]
        grp = build_team_players(label, roster, sb_team, und, und_names, und_lookup)
        new_teams.append(team_aggregate(label, grp))

    new_df = pd.DataFrame(new_teams)
    done_labels = set(new_df["nation"])
    patched = pd.concat(
        [team_old[~team_old["nation"].isin(done_labels)], new_df], ignore_index=True
    ).sort_values("attack_rating", ascending=False)[team_old.columns]
    patched.to_parquet(DERIVED / "team_attack_ratings.parquet", index=False)

    # Report the headline movers vs the old ratings.
    oldmap = dict(zip(team_old["nation"], team_old["attack_rating"]))
    print(f"{'Team':16}{'club%':>7}{'old':>9}{'new':>9}")
    show = new_df.sort_values("attack_rating", ascending=False)
    for _, r in show.head(20).iterrows():
        cp = 100 * r["matched_to_club"] / r["squad_players"]
        ov = oldmap.get(r["nation"], float("nan"))
        print(f"  {r['nation']:14}{cp:>6.0f}%{ov:>9.3f}{r['attack_rating']:>9.3f}")
    print(f"\nPatched {len(new_df)} qualifier rows → team_attack_ratings.parquet "
          f"({len(team_old)-len([l for l in team_old['nation'] if l in done_labels])} non-qualifier rows kept)")


if __name__ == "__main__":
    main()
