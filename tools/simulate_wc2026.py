#!/usr/bin/env python3
"""
Monte Carlo simulation of FIFA World Cup 2026.

Uses team_attack_ratings.parquet (blended xG/90 per nation) to estimate
match win probabilities via a Poisson goal model. Simulates the full
tournament N times and reports per-team stage-reach probabilities.

Saves:
  results/wc2026-sim/probabilities.json
  results/wc2026-sim/probabilities.csv

Usage:
  python3 tools/simulate_wc2026.py [--n 10000] [--seed 42]
"""
import json, sys, csv, argparse
from pathlib import Path
from collections import defaultdict

import numpy as np
import pandas as pd

ROOT = Path(__file__).parent.parent
TOURNAMENT_PATH = ROOT / "data" / "wc2026" / "tournament.json"
RATINGS_PATH    = ROOT / "data" / "derived" / "team_attack_ratings.parquet"
OUT_DIR         = ROOT / "results" / "wc2026-sim"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# Nation name bridge: tournament name → attack_ratings nation column
NAME_ALIASES = {
    "USA":                      "United States",
    "Czechia":                  "Czech Republic",
    "Türkiye":                  "Turkey",
    "Ivory Coast":              "Côte d'Ivoire",  # fallback if present
    "Bosnia and Herzegovina":   None,  # not in ratings → fallback
    "South Africa":             None,
    "Haiti":                    None,
    "Curaçao":                  None,
    "Sweden":                   None,
    "New Zealand":              None,
    "Egypt":                    None,
    "Cape Verde":               None,
    "Iraq":                     None,
    "Norway":                   None,
    "Algeria":                  None,
    "Jordan":                   None,
    "DR Congo":                 None,
    "Uzbekistan":               None,
}

# Poisson λ bounds: even the weakest WC team scores ~0.7/game; best ~1.9
LAMBDA_MIN = 0.70
LAMBDA_MAX = 1.90
RATING_MIN = None  # set from data
RATING_MAX = None  # set from data


def load_ratings():
    df = pd.read_parquet(RATINGS_PATH)[["nation", "attack_rating"]]
    ratings = {row.nation: row.attack_rating for row in df.itertuples()}
    global RATING_MIN, RATING_MAX
    RATING_MIN = float(df["attack_rating"].min())
    RATING_MAX = float(df["attack_rating"].max())
    # Fallback for unrated teams: 25th percentile (modestly weak)
    fallback = float(df["attack_rating"].quantile(0.25))
    return ratings, fallback


def resolve(team, ratings, fallback):
    """Return attack_rating for a team, applying aliases and fallback."""
    alias = NAME_ALIASES.get(team, team)  # default: same name (no alias needed)
    if alias is None:
        return fallback
    if alias in ratings:
        return ratings[alias]
    if team in ratings:
        return ratings[team]
    return fallback


def get_lambda(team, ratings, fallback):
    rating = resolve(team, ratings, fallback)
    # Min-max normalize to [LAMBDA_MIN, LAMBDA_MAX]
    t = (rating - RATING_MIN) / max(RATING_MAX - RATING_MIN, 1e-6)
    return LAMBDA_MIN + t * (LAMBDA_MAX - LAMBDA_MIN)


def sim_match(t1, t2, ratings, fallback, rng):
    """Simulate a single match. Returns winner (t1 or t2)."""
    lam1 = get_lambda(t1, ratings, fallback)
    lam2 = get_lambda(t2, ratings, fallback)
    g1 = rng.poisson(lam1)
    g2 = rng.poisson(lam2)
    if g1 > g2:
        return t1
    if g2 > g1:
        return t2
    # Draw: resolve via weighted coin (penalty shootout proxy)
    return t1 if rng.random() < lam1 / (lam1 + lam2) else t2


def sim_match_with_score(t1, t2, ratings, fallback, rng):
    """Returns (winner, g1, g2) — used for group stage point tracking."""
    lam1 = get_lambda(t1, ratings, fallback)
    lam2 = get_lambda(t2, ratings, fallback)
    g1 = rng.poisson(lam1)
    g2 = rng.poisson(lam2)
    if g1 > g2:
        return t1, g1, g2
    if g2 > g1:
        return t2, g1, g2
    return None, g1, g2  # draw


def sim_group(group, ratings, fallback, rng):
    """
    Simulate all 6 group matches. Returns list of (team, pts, gd, gs) sorted
    by rank (pts→gd→gs→random tiebreak).
    """
    teams = group["teams"]
    pts = defaultdict(int)
    gd  = defaultdict(int)
    gs  = defaultdict(int)
    h2h_pts = defaultdict(lambda: defaultdict(int))

    for match in group["matches"]:
        h, a = match["home"], match["away"]
        winner, gh, ga = sim_match_with_score(h, a, ratings, fallback, rng)
        gs[h] += gh; gs[a] += ga
        gd[h] += gh - ga; gd[a] += ga - gh
        if winner == h:
            pts[h] += 3
            h2h_pts[h][a] += 3
        elif winner == a:
            pts[a] += 3
            h2h_pts[a][h] += 3
        else:
            pts[h] += 1; pts[a] += 1
            h2h_pts[h][a] += 1; h2h_pts[a][h] += 1

    def sort_key(t):
        # Primary: pts, gd, gs; secondary: head-to-head (simplified); tertiary: random
        return (-pts[t], -gd[t], -gs[t], rng.random())

    ranked = sorted(teams, key=sort_key)
    return [
        {"team": t, "pts": pts[t], "gd": gd[t], "gs": gs[t]}
        for t in ranked
    ]


def pick_third_place_qualifiers(all_thirds, third_place_rules):
    """
    Select 8 best 3rd-place teams and assign them to R32 slots.
    all_thirds: list of {team, group_id, pts, gd, gs}
    Returns: dict {match_id → team}
    """
    ranked = sorted(all_thirds,
                    key=lambda x: (-x["pts"], -x["gd"], -x["gs"]))
    top8 = ranked[:8]
    slot_rules = third_place_rules["slot_to_groups"]

    assignments = {}
    used_teams = set()
    # For each slot (in order of match ID), find the highest-ranked unassigned
    # team whose group is in the slot's valid set
    for slot_id, valid_groups in slot_rules.items():
        for candidate in top8:
            if candidate["team"] in used_teams:
                continue
            if candidate["group_id"] in valid_groups:
                assignments[slot_id] = candidate["team"]
                used_teams.add(candidate["team"])
                break
        if slot_id not in assignments:
            # Fallback: take next unassigned team regardless of group
            for candidate in top8:
                if candidate["team"] not in used_teams:
                    assignments[slot_id] = candidate["team"]
                    used_teams.add(candidate["team"])
                    break
    return assignments


def resolve_r32_slot(slot, winners, runners_up, third_assignments, group_id=None):
    """Resolve a slot string like '1A', '2F', '3ABCDF' to a team name."""
    if slot.startswith("1"):
        return winners[slot[1]]
    if slot.startswith("2"):
        return runners_up[slot[1]]
    if slot.startswith("3"):
        # The slot string is like '3ABCDF' — look up via third_assignments keyed by match id
        # This is called with the match id as group_id
        return third_assignments.get(group_id)
    return None


def sim_bracket(winners, runners_up, third_assignments, tournament, ratings, fallback, rng):
    """Simulate the knockout bracket. Returns champion team name."""
    bracket = tournament["bracket"]
    match_winners = {}

    # R32
    for m in bracket["r32"]:
        slot_a, slot_b = m["slot_a"], m["slot_b"]
        t1 = resolve_r32_slot(slot_a, winners, runners_up, third_assignments, m["id"])
        t2 = resolve_r32_slot(slot_b, winners, runners_up, third_assignments, m["id"])
        if t1 is None or t2 is None:
            # Should not happen; use a fallback team
            t1 = t1 or list(winners.values())[0]
            t2 = t2 or list(winners.values())[1]
        match_winners[m["id"]] = sim_match(t1, t2, ratings, fallback, rng)

    def lookup(slot):
        key = slot[1:]  # strip leading "W"
        if key.isdigit():
            key = "M" + key
        return match_winners[key]

    # R16, QF, SF, Final — slots are "W<match_id>"
    for round_key in ["r16", "quarterfinals", "semifinals"]:
        for m in bracket[round_key]:
            t1 = lookup(m["slot_a"])
            t2 = lookup(m["slot_b"])
            match_winners[m["id"]] = sim_match(t1, t2, ratings, fallback, rng)

    final = bracket["final"][0]
    t1 = lookup(final["slot_a"])
    t2 = lookup(final["slot_b"])
    champion = sim_match(t1, t2, ratings, fallback, rng)
    match_winners["FINAL"] = champion

    return match_winners


def run(n=10000, seed=42):
    print(f"Loading ratings ...")
    ratings, fallback = load_ratings()
    tournament = json.loads(TOURNAMENT_PATH.read_text())

    all_teams = set()
    for g in tournament["groups"]:
        for t in g["teams"]:
            all_teams.add(t)

    # Count unrated teams
    unrated = [t for t in all_teams if resolve(t, ratings, fallback) == fallback]
    if unrated:
        print(f"  [warn] {len(unrated)} teams using fallback rating: {', '.join(sorted(unrated))}")

    # Stage reach counters
    stages = ["r32", "r16", "qf", "sf", "final", "champion"]
    counts = {t: {s: 0 for s in stages} for t in all_teams}

    rng = np.random.default_rng(seed)
    third_place_rules = tournament["third_place_rules"]

    print(f"Running {n:,} simulations ...")
    for _ in range(n):
        winners = {}      # group_id → 1st place team
        runners_up = {}   # group_id → 2nd place team
        all_thirds = []   # list of {team, group_id, pts, gd, gs}

        for group in tournament["groups"]:
            standings = sim_group(group, ratings, fallback, rng)
            gid = group["id"]
            winners[gid]    = standings[0]["team"]
            runners_up[gid] = standings[1]["team"]
            all_thirds.append({**standings[2], "group_id": gid})

        third_assignments = pick_third_place_qualifiers(all_thirds, third_place_rules)

        # Track R32 participants
        r32_teams = set(winners.values()) | set(runners_up.values()) | set(third_assignments.values())
        for t in r32_teams:
            counts[t]["r32"] += 1

        match_winners = sim_bracket(
            winners, runners_up, third_assignments, tournament, ratings, fallback, rng
        )

        bracket = tournament["bracket"]

        def lkp(slot):
            key = slot[1:]
            if key.isdigit():
                key = "M" + key
            return match_winners[key]

        # R16 participants
        for m in bracket["r16"]:
            counts[lkp(m["slot_a"])]["r16"] += 1
            counts[lkp(m["slot_b"])]["r16"] += 1

        # QF
        for m in bracket["quarterfinals"]:
            counts[lkp(m["slot_a"])]["qf"] += 1
            counts[lkp(m["slot_b"])]["qf"] += 1

        # SF
        for m in bracket["semifinals"]:
            counts[lkp(m["slot_a"])]["sf"] += 1
            counts[lkp(m["slot_b"])]["sf"] += 1

        # Final (both finalists)
        final = bracket["final"][0]
        counts[lkp(final["slot_a"])]["final"] += 1
        counts[lkp(final["slot_b"])]["final"] += 1

        # Champion
        counts[match_winners["FINAL"]]["champion"] += 1

    # Convert to probabilities
    probs = {
        t: {s: round(counts[t][s] / n, 4) for s in stages}
        for t in all_teams
    }

    # Sort by champion probability
    ranked = sorted(probs.items(), key=lambda x: -x[1]["champion"])

    print_summary(ranked[:20])
    save_results(ranked, n, seed)
    return probs


def print_summary(ranked):
    print()
    print(f"{'Team':26} {'Win%':>6} {'Final':>6} {'Semi':>6} {'QF':>6} {'R16':>6} {'R32':>6}")
    print("-" * 70)
    for team, p in ranked:
        print(
            f"{team:26} "
            f"{p['champion']*100:5.1f}%  "
            f"{p['final']*100:5.1f}%  "
            f"{p['sf']*100:5.1f}%  "
            f"{p['qf']*100:5.1f}%  "
            f"{p['r16']*100:5.1f}%  "
            f"{p['r32']*100:5.1f}%"
        )


def save_results(ranked, n, seed):
    out_json = OUT_DIR / "probabilities.json"
    out_csv  = OUT_DIR / "probabilities.csv"

    payload = {
        "meta": {"simulations": n, "seed": seed},
        "probabilities": {t: p for t, p in ranked}
    }
    out_json.write_text(json.dumps(payload, indent=2))

    with open(out_csv, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["team", "p_champion", "p_final", "p_semi", "p_qf", "p_r16", "p_r32"])
        for team, p in ranked:
            w.writerow([team, p["champion"], p["final"], p["sf"], p["qf"], p["r16"], p["r32"]])

    print(f"\nSaved → {out_json.relative_to(ROOT)}")
    print(f"Saved → {out_csv.relative_to(ROOT)}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--n",    type=int, default=10000, help="Number of simulations")
    parser.add_argument("--seed", type=int, default=42,    help="Random seed")
    args = parser.parse_args()
    run(n=args.n, seed=args.seed)
