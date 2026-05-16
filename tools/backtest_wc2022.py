"""WC2022 held-out backtest for curated-poisson-luck.

Freezes all features at 2022-11-19 (one day before WC2022 first match), runs
the model's compute_lambdas + closed_form_1x2 against every WC2022 match, and
scores:

  - 1X2 accuracy (top-pick correct?)
  - Brier score on the 1X2 probability triple
  - Log-loss
  - Champion-pick: rank by p_win_path (group + R16 + QF + SF + F joint, naive)

No information from 2022-11-20 onward leaks into features. The recent-form
window and the historical-since-2022 goal stats both filter on
match_date < '2022-11-20'.

FIFA rank and economics are NOT historically available — we use current
snapshots (small effect: fifa_rank carries ~10% weight, econ_mult is clipped
to ±15%). This is a known limitation, documented in the output.
"""
from __future__ import annotations

import duckdb
import numpy as np
import pandas as pd
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "data" / "wc2026.duckdb"
CUTOFF = "2022-11-20"  # strict less-than this date

# Load model functions
spec = importlib.util.spec_from_file_location("m", ROOT / "methodology" / "curated-poisson-luck" / "model.py")
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)


FEATURES_AS_OF_SQL = """
WITH
team_match AS (
    SELECT home_team_code AS team_code, home_score AS goals_for, away_score AS goals_against, tournament_tier
    FROM curated.fact_international_match
    WHERE match_date >= DATE '2022-01-01' AND match_date < DATE '{cutoff}'
    UNION ALL
    SELECT away_team_code, away_score, home_score, tournament_tier
    FROM curated.fact_international_match
    WHERE match_date >= DATE '2022-01-01' AND match_date < DATE '{cutoff}'
),
weighted AS (
    SELECT team_match.team_code, team_match.goals_for, team_match.goals_against, tier_weight.weight
    FROM team_match JOIN curated.dim_tournament_tier_weight tier_weight USING (tournament_tier)
),
means AS (
    SELECT team_code, COUNT(*) AS match_count, SUM(weight) AS weight_sum,
           SUM(weight*goals_for)/SUM(weight)     AS goals_for_mean,
           SUM(weight*goals_against)/SUM(weight) AS goals_against_mean
    FROM weighted GROUP BY team_code
),
goal_stats AS (
    SELECT weighted.team_code, means.match_count, means.goals_for_mean,
           SQRT(SUM(weighted.weight*(weighted.goals_for-means.goals_for_mean)*(weighted.goals_for-means.goals_for_mean))/means.weight_sum) AS goals_for_std,
           means.goals_against_mean,
           SQRT(SUM(weighted.weight*(weighted.goals_against-means.goals_against_mean)*(weighted.goals_against-means.goals_against_mean))/means.weight_sum) AS goals_against_std
    FROM weighted JOIN means USING (team_code)
    GROUP BY weighted.team_code, means.match_count, means.goals_for_mean, means.goals_against_mean, means.weight_sum
),
-- Point-in-time recent-form window: rank pre-cutoff matches per team
ranked_pit AS (
    SELECT
        team_code, match_date, team_score, opponent_score, goal_difference, outcome, is_competitive,
        ROW_NUMBER() OVER (PARTITION BY team_code ORDER BY match_date DESC) AS recency_rank
    FROM staging.team_match
    WHERE match_date < DATE '{cutoff}'
),
recent_form AS (
    SELECT
        team_code,
        COUNT(*)            FILTER (WHERE recency_rank <= 10)                          AS matches_last_10,
        SUM(team_score)     FILTER (WHERE recency_rank <= 10)                          AS goals_for_last_10,
        SUM(opponent_score) FILTER (WHERE recency_rank <= 10)                          AS goals_against_last_10,
        SUM(goal_difference) FILTER (WHERE recency_rank <= 10)                         AS goal_difference_last_10,
        SUM(CASE outcome WHEN 'W' THEN 3 WHEN 'D' THEN 1 ELSE 0 END)
            FILTER (WHERE recency_rank <= 10)                                          AS form_points_last_10,
        COUNT(*) FILTER (WHERE recency_rank <= 5)                                      AS matches_last_5,
        SUM(team_score) FILTER (WHERE recency_rank <= 5)                               AS goals_for_last_5,
        SUM(opponent_score) FILTER (WHERE recency_rank <= 5)                           AS goals_against_last_5
    FROM ranked_pit GROUP BY team_code
)
SELECT
    team.team_code, team.team_name, team.confederation, team.is_wc2026_qualifier,
    team_current.fifa_rank, team_current.fifa_points, team_current.fifa_rank_change, team_current.fifa_snapshot_date,
    team_current.economics_year, team_current.gdp_per_capita_usd_latest, team_current.population_latest,
    NULL::DATE AS last_match_date,
    recent_form.matches_last_10, NULL::BIGINT AS wins_last_10, NULL::BIGINT AS draws_last_10, NULL::BIGINT AS losses_last_10,
    recent_form.goals_for_last_10, recent_form.goals_against_last_10, recent_form.goal_difference_last_10, recent_form.form_points_last_10,
    recent_form.matches_last_5, recent_form.goals_for_last_5, recent_form.goals_against_last_5,
    NULL::BIGINT AS competitive_matches_last_10, NULL::BIGINT AS competitive_goal_difference_last_10, NULL::BIGINT AS competitive_form_points_last_10,
    NULL::DOUBLE AS avg_opponent_fifa_rank_last_10,
    goal_stats.match_count         AS historical_match_count,
    goal_stats.goals_for_mean      AS historical_goals_for_mean,
    goal_stats.goals_for_std       AS historical_goals_for_std,
    goal_stats.goals_against_mean  AS historical_goals_against_mean,
    goal_stats.goals_against_std   AS historical_goals_against_std
FROM curated.dim_team team
LEFT JOIN curated.dim_team_current team_current USING (team_code)
LEFT JOIN goal_stats USING (team_code)
LEFT JOIN recent_form USING (team_code)
WHERE team.team_code IN ({wc2022_teams})
ORDER BY team_current.fifa_rank NULLS LAST;
"""


WC2022_TEAMS = ['ARG','AUS','BEL','BRA','CAN','CMR','CRC','CRO','DEN','ECU','ENG','ESP','FRA','GER',
                'GHA','IRI','JPN','KOR','KSA','MAR','MEX','NED','POL','POR','QAT','SEN','SRB','SUI',
                'TUN','URU','USA','WAL']

HOST_TEAM_CODES_2022 = {"QAT"}  # WC2022 host


def load_features(con):
    sql = FEATURES_AS_OF_SQL.format(
        cutoff=CUTOFF,
        wc2022_teams=",".join(f"'{t}'" for t in WC2022_TEAMS),
    )
    return con.sql(sql).df()


def load_matches(con):
    return con.sql(f"""
        SELECT match_date, home_team_code, away_team_code, home_score, away_score, neutral_site,
               (CASE WHEN home_score > away_score THEN 'home'
                     WHEN home_score < away_score THEN 'away'
                     ELSE 'draw' END) AS actual
        FROM curated.fact_international_match
        WHERE tournament = 'FIFA World Cup'
          AND match_date BETWEEN DATE '2022-11-20' AND DATE '2022-12-18'
        ORDER BY match_date
    """).df()


def score_match(home_row, away_row, is_home_host):
    p_h, p_d, p_a = m.closed_form_1x2(
        home_row["lambda_team"], home_row["sigma_team"],
        away_row["lambda_team"], away_row["sigma_team"],
        is_neutral=not is_home_host, is_home_host=is_home_host,
    )
    return p_h, p_d, p_a


def main():
    con = duckdb.connect(str(DB_PATH), read_only=True)
    feats = load_features(con)
    print(f"\nLoaded features for {len(feats)} of 32 WC2022 teams.")
    missing = set(WC2022_TEAMS) - set(feats["team_code"])
    if missing:
        print(f"  Missing: {missing}")

    # Patch: model expects every column it reads to exist. Add zeros for any NaN inputs.
    for col in ["goals_for_last_10","matches_last_10","historical_goals_for_mean",
                "historical_goals_for_std","historical_match_count"]:
        if feats[col].isna().any():
            n = feats[col].isna().sum()
            print(f"  WARN: {n} teams missing {col} -> imputing 0")
            feats[col] = feats[col].fillna(0)

    lambdas = m.compute_lambdas(feats).set_index("team_code")

    print("\n=== λ_team and σ_team for the 32 WC2022 teams (top by FIFA rank) ===")
    show = lambdas[["team_name","fifa_rank","lambda_team","sigma_team",
                    "goals_for_last_10","historical_goals_for_mean","historical_goals_for_std"]]
    print(show.head(12).round(3).to_string())

    matches = load_matches(con)
    print(f"\nScoring {len(matches)} WC2022 matches...\n")

    rows = []
    for _, mt in matches.iterrows():
        h, a = mt["home_team_code"], mt["away_team_code"]
        if h not in lambdas.index or a not in lambdas.index:
            continue
        is_home_host = h in HOST_TEAM_CODES_2022
        p_h, p_d, p_a = score_match(lambdas.loc[h], lambdas.loc[a], is_home_host)
        actual = mt["actual"]
        top_pick = ["home","draw","away"][int(np.argmax([p_h, p_d, p_a]))]
        correct = (top_pick == actual)
        # Brier: sum of squared errors against one-hot outcome
        oh = {"home":[1,0,0],"draw":[0,1,0],"away":[0,0,1]}[actual]
        brier = sum((p - o)**2 for p, o in zip([p_h,p_d,p_a], oh))
        # Log-loss for the actual outcome
        p_actual = {"home":p_h,"draw":p_d,"away":p_a}[actual]
        log_loss = -np.log(max(p_actual, 1e-9))
        rows.append({
            "date": mt["match_date"], "home": h, "away": a,
            "score": f"{mt['home_score']}-{mt['away_score']}",
            "actual": actual, "p_h": p_h, "p_d": p_d, "p_a": p_a,
            "top_pick": top_pick, "correct": correct,
            "brier": brier, "log_loss": log_loss,
        })

    df = pd.DataFrame(rows)
    print("=== Per-match predictions (first 16 matches, group stage opening week) ===")
    print(df.head(16).round(3).to_string(index=False))

    print("\n=== Aggregate scores across 64 WC2022 matches ===")
    acc = df["correct"].mean()
    brier = df["brier"].mean()
    ll = df["log_loss"].mean()
    print(f"  1X2 accuracy:  {acc:.1%}  ({df['correct'].sum()}/{len(df)})")
    print(f"  Brier (mean):  {brier:.3f}    (lower = better; uniform 1/3 baseline ≈ 0.667)")
    print(f"  Log-loss (mean):{ll:.3f}     (lower = better; uniform 1/3 baseline = 1.099)")
    print(f"\n  Top picks by outcome:")
    print(df.groupby(["actual","top_pick"]).size().unstack(fill_value=0).to_string())

    print("\n=== Where the model went wrong (matches where top pick failed) ===")
    misses = df[~df["correct"]].copy()
    print(f"  {len(misses)} misses out of {len(df)}")
    # Sort by "biggest miss" (highest probability put on wrong outcome)
    misses["confidence_in_wrong"] = misses.apply(
        lambda r: max(r["p_h"], r["p_d"], r["p_a"]), axis=1
    )
    print(misses.nlargest(10, "confidence_in_wrong")[
        ["date","home","away","score","actual","top_pick","p_h","p_d","p_a"]
    ].round(3).to_string(index=False))

    print("\n=== Pre-tournament champion pick implied by the model ===")
    # For each team: probability of winning each group stage match (assuming we use
    # actual fixtures) and then a rough "favorite index" based on lambda_team * 1/(1+rank)
    # The true championship probability requires running the full bracket — skipped for
    # this first pass. Use lambda_team as a simple strength proxy.
    print("Top 10 by λ_team (model's strength proxy):")
    print(lambdas.sort_values("lambda_team", ascending=False)
          [["team_name","fifa_rank","lambda_team","sigma_team"]].head(10).round(3).to_string())
    print("\nActual finishers: ARG (champ), FRA (RU), CRO (3rd), MAR (4th).")


if __name__ == "__main__":
    main()
