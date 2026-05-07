"""
Export simulation results and ratings to docs/data.json for the WC2026 web report.

Usage:
    python tools/export_web_data.py
"""

import json
import math
from pathlib import Path

import pandas as pd

REPO = Path(__file__).parent.parent

# Teams that fall back to prior ratings due to missing player data (None aliases
# in simulate_wc2026.py). These are flagged LOW confidence in the report.
LOW_CONFIDENCE = {
    "Bosnia and Herzegovina", "South Africa", "Haiti", "Curaçao", "Sweden",
    "New Zealand", "Egypt", "Cape Verde", "Iraq", "Norway", "Algeria",
    "Jordan", "DR Congo", "Uzbekistan",
}

# Kalshi ISO team code → canonical name used in probabilities.json
KALSHI_ISO_MAP = {
    "IRQ": "Iraq", "COD": "DR Congo", "BIH": "Bosnia and Herzegovina",
    "CZE": "Czechia", "PAN": "Panama", "HTI": "Haiti", "CUW": "Curaçao",
    "CIV": "Ivory Coast", "QAT": "Qatar", "RSA": "South Africa",
    "CPV": "Cape Verde", "DZA": "Algeria", "EGY": "Egypt", "JOR": "Jordan",
    "UZB": "Uzbekistan", "NZL": "New Zealand", "TN": "Tunisia",
    "SA": "Saudi Arabia", "IR": "Iran", "SC": "Scotland",
    "PY": "Paraguay", "KR": "South Korea", "GH": "Ghana",
    "AU": "Australia", "SN": "Senegal", "SE": "Sweden",
    "NO": "Norway", "MX": "Mexico", "MA": "Morocco", "JP": "Japan",
    "EC": "Ecuador", "CO": "Colombia", "CH": "Switzerland",
    "CA": "Canada", "AT": "Austria", "UY": "Uruguay",
    "US": "USA", "PT": "Portugal", "NL": "Netherlands",
    "HR": "Croatia", "GB": "England", "DE": "Germany",
    "BR": "Brazil", "BE": "Belgium", "AR": "Argentina",
    "FR": "France", "ES": "Spain", "TR": "Türkiye",
}

# Polymarket variant outcome names → canonical name
POLYMARKET_NAME_MAP = {
    "Bosnia-Herzegovina": "Bosnia and Herzegovina",
    "Turkiye": "Türkiye",
    "Congo DR": "DR Congo",
}


def load_probabilities():
    path = REPO / "results/wc2026-sim/probabilities.json"
    with open(path) as f:
        data = json.load(f)
    probs = data["probabilities"]
    assert len(probs) == 48, f"Expected 48 teams in probabilities, got {len(probs)}"
    return probs


def load_ratings():
    path = REPO / "data/derived/team_ratings_all_models.parquet"
    df = pd.read_parquet(path)
    return df.set_index("nation")


def load_market_odds():
    # Kalshi outright winner prices (last_price is a 0–1 probability)
    k = pd.read_csv(REPO / "data/derived/kalshi_snapshot_2026-04-28.csv")
    k_out = k[k["market_type"] == "outright_winner"].copy()
    k_out["canonical"] = k_out["team_code"].map(KALSHI_ISO_MAP)
    k_out = k_out[k_out["canonical"].notna()]
    kalshi = {row["canonical"]: round(float(row["last_price"]) * 100, 1)
              for _, row in k_out.iterrows()}

    # Polymarket outright winner prices (yes_price is a 0–1 probability)
    pm = pd.read_csv(REPO / "data/derived/polymarket_snapshot_2026-04-28.csv")
    pm_out = pm[pm["market_type"] == "outright_winner"].copy()
    pm_out["canonical"] = pm_out["outcome"].apply(
        lambda x: POLYMARKET_NAME_MAP.get(x, x)
    )
    # Exclude placeholder entries like "Team AM", "Other"
    pm_out = pm_out[~pm_out["outcome"].str.startswith("Team ")]
    pm_out = pm_out[pm_out["outcome"] != "Other"]
    polymarket = {row["canonical"]: round(float(row["yes_price"]) * 100, 1)
                  for _, row in pm_out.iterrows()
                  if not (isinstance(row["yes_price"], float) and math.isnan(row["yes_price"]))}

    return kalshi, polymarket


def confidence_level(team, ratings):
    if team in LOW_CONFIDENCE:
        return "LOW"
    if team in ratings.index:
        m2 = float(ratings.loc[team, "M2_Season"])
        if m2 >= 0.45:
            return "HIGH"
        return "MEDIUM"
    return "MEDIUM"


def _head_to_head_pct(t1_prob, t2_prob):
    """Convert raw stage-reach probabilities to a head-to-head win split."""
    total = t1_prob + t2_prob
    if total <= 0:
        return 50.0, 50.0
    p1 = round(t1_prob / total * 100, 1)
    return p1, round(100 - p1, 1)


def derive_bracket(probs, tournament):
    groups_cfg = tournament["groups"]
    bracket_cfg = tournament["bracket"]
    third_place_rules = tournament["third_place_rules"]["slot_to_groups"]

    # --- Group stage: rank by champion% as proxy for group standing ---
    group_results = {}
    thirds_pool = []

    for g in groups_cfg:
        gid = g["id"]
        ranked = sorted(g["teams"],
                        key=lambda t: probs.get(t, {}).get("champion", 0),
                        reverse=True)
        group_results[gid] = {
            "winner": ranked[0],
            "runner_up": ranked[1],
            "teams": g["teams"],
        }
        thirds_pool.append({
            "team": ranked[2],
            "group": gid,
            "pct": probs.get(ranked[2], {}).get("champion", 0),
        })

    # --- Best-thirds: pick top 8 by champion%, assign to valid R32 slots ---
    thirds_pool.sort(key=lambda x: x["pct"], reverse=True)
    best_8 = thirds_pool[:8]  # {team, group, pct}
    # Map group_id → team for the best 8
    best_thirds_by_group = {t["group"]: t["team"] for t in best_8}

    winners = {gid: r["winner"] for gid, r in group_results.items()}
    runners_up = {gid: r["runner_up"] for gid, r in group_results.items()}

    # Greedy assignment: for each "3" slot, pick the best available third
    # whose group is in the slot's valid set.
    assigned_thirds = {}  # match_id → team

    def _pick_third(match_id, valid_groups, remaining):
        for g in sorted(valid_groups,
                        key=lambda x: -probs.get(remaining.get(x, ""), {}).get("champion", 0)):
            if g in remaining:
                team = remaining.pop(g)
                assigned_thirds[match_id] = team
                return team
        return "TBD"

    remaining_thirds = dict(best_thirds_by_group)

    def resolve_slot(slot_str, match_id):
        if slot_str.startswith("1"):
            return winners.get(slot_str[1:], "TBD")
        if slot_str.startswith("2"):
            return runners_up.get(slot_str[1:], "TBD")
        if slot_str.startswith("3"):
            valid = third_place_rules.get(match_id, [])
            return _pick_third(match_id, valid, remaining_thirds)
        return "TBD"

    match_winners = {}  # match_id → predicted winner

    def _slot_to_key(slot_str):
        """Convert a slot reference like 'W73', 'W89', or 'WSF1' to a match_winners key."""
        suffix = slot_str[1:]  # strip leading 'W'
        # Numeric suffix → "M" + suffix (e.g. "W73" → "M73")
        # Non-numeric suffix → use as-is (e.g. "WSF1" → "SF1")
        return "M" + suffix if suffix.isdigit() else suffix

    def build_round_from_slots(slots, prob_key, source="slots"):
        matches = []
        for m in slots:
            if source == "slots":
                t1 = resolve_slot(m["slot_a"], m["id"])
                t2 = resolve_slot(m["slot_b"], m["id"])
            else:
                # R16+ slots use "W<match_id>" references
                t1 = match_winners.get(_slot_to_key(m["slot_a"]), "TBD")
                t2 = match_winners.get(_slot_to_key(m["slot_b"]), "TBD")
            p1_raw = probs.get(t1, {}).get(prob_key, 0)
            p2_raw = probs.get(t2, {}).get(prob_key, 0)
            p1, p2 = _head_to_head_pct(p1_raw, p2_raw)
            winner = t1 if p1 >= p2 else t2
            match_winners[m["id"]] = winner
            matches.append({
                "match_id": m["id"],
                "team1": t1,
                "team2": t2,
                "p1": p1,
                "p2": p2,
                "winner": winner,
            })
        return matches

    r32 = build_round_from_slots(bracket_cfg["r32"], "r16", source="slots")
    r16 = build_round_from_slots(bracket_cfg["r16"], "qf", source="winners")
    qf = build_round_from_slots(bracket_cfg["quarterfinals"], "sf", source="winners")
    sf = build_round_from_slots(bracket_cfg["semifinals"], "final", source="winners")
    final = build_round_from_slots(bracket_cfg["final"], "champion", source="winners")

    champion = final[0]["winner"] if final else None

    return {
        "groups": {
            gid: {
                "winner": res["winner"],
                "runner_up": res["runner_up"],
                "teams": res["teams"],
            }
            for gid, res in group_results.items()
        },
        "r32": r32,
        "r16": r16,
        "qf": qf,
        "sf": sf,
        "final": final[0] if final else {},
        "champion": champion,
    }


def derive_model_agreement(probs, ratings):
    """Return top 16 teams by champion% with model convergence signal."""
    top_teams = sorted(probs.keys(),
                       key=lambda t: probs[t]["champion"],
                       reverse=True)[:16]
    result = []
    for team in top_teams:
        if team not in ratings.index:
            result.append({"team": team, "agreement": "UNKNOWN",
                           "champion_pct": round(probs[team]["champion"] * 100, 1)})
            continue
        m1 = float(ratings.loc[team, "M1_History"])
        m2 = float(ratings.loc[team, "M2_Season"])
        m3 = float(ratings.loc[team, "M3_RecentForm"])
        vals = [m1, m2, m3]
        mean = sum(vals) / 3
        cv = (sum((x - mean) ** 2 for x in vals) / 3) ** 0.5 / mean if mean > 0 else 1
        result.append({
            "team": team,
            "champion_pct": round(probs[team]["champion"] * 100, 1),
            "agreement": "CONVERGE" if cv < 0.12 else "DIVERGE",
        })
    return result


def main():
    probs = load_probabilities()
    ratings = load_ratings()
    kalshi, polymarket = load_market_odds()

    with open(REPO / "data/wc2026/tournament.json") as f:
        tournament = json.load(f)

    # Build sorted team list (champion% descending)
    teams = []
    for rank, (team, p) in enumerate(
        sorted(probs.items(), key=lambda x: x[1]["champion"], reverse=True), 1
    ):
        r_m1 = float(ratings.loc[team, "M1_History"]) if team in ratings.index else None
        r_m2 = float(ratings.loc[team, "M2_Season"]) if team in ratings.index else None
        r_m3 = float(ratings.loc[team, "M3_RecentForm"]) if team in ratings.index else None

        teams.append({
            "rank": rank,
            "name": team,
            "champion_pct": round(p["champion"] * 100, 1),
            "final_pct": round(p["final"] * 100, 1),
            "semi_pct": round(p["sf"] * 100, 1),
            "group_exit_pct": round((1 - p["r32"]) * 100, 1),
            "confidence": confidence_level(team, ratings),
            "ratings": {
                "m1_history": round(r_m1, 3) if r_m1 is not None else None,
                "m2_season": round(r_m2, 3) if r_m2 is not None else None,
                "m3_form": round(r_m3, 3) if r_m3 is not None else None,
            },
            "market": {
                "kalshi_pct": kalshi.get(team),
                "polymarket_pct": polymarket.get(team),
            },
        })

    bracket = derive_bracket(probs, tournament)
    model_agreement = derive_model_agreement(probs, ratings)

    output = {
        "meta": {
            "generated": "2026-05-07",
            "simulations": 10000,
            "note": (
                "Predicted bracket is a model-estimated path based on win probabilities, "
                "not official FIFA seeding. Will be updated as squads are confirmed."
            ),
        },
        "teams": teams,
        "bracket": bracket,
        "model_agreement": model_agreement,
    }

    out_path = REPO / "docs/data.json"
    out_path.parent.mkdir(exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"✓  Written to {out_path.relative_to(REPO)}")
    print(f"   Teams: {len(teams)}")
    print(f"   Champion: {bracket['champion']}")
    print(f"   Finalist: {bracket['final'].get('team1')} vs {bracket['final'].get('team2')}")
    k_covered = sum(1 for t in teams if t["market"]["kalshi_pct"] is not None)
    pm_covered = sum(1 for t in teams if t["market"]["polymarket_pct"] is not None)
    print(f"   Kalshi coverage: {k_covered}/48 teams")
    print(f"   Polymarket coverage: {pm_covered}/48 teams")
    low_count = sum(1 for t in teams if t["confidence"] == "LOW")
    print(f"   Low-confidence teams: {low_count}")


if __name__ == "__main__":
    main()
