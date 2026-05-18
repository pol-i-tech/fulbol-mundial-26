-- methodology/wc2026-predictor/queries/team_model_features.sql
-- Grain: one row per WC2026 qualifier (48 rows).
-- Joins curated.dim_team_current + curated.dim_team_recent_form + the
-- goal-stats CTE (mirror of methodology/wc2026-predictor/queries/team_goal_stats.sql)
-- into a single wide model-input row.
--
-- Read-only against curated.*; no parquet reads.
-- Naming: follows db/NAMING.md.
--
-- Plan: docs/plans/2026-05-15-002-feat-wc2026-predictor-model-plan.md (Unit 2)

-- Tier weights sourced from curated.dim_tournament_tier_weight (single source of truth).
WITH
team_match AS (
    SELECT home_team_code AS team_code, home_score AS goals_for, away_score AS goals_against, tournament_tier
    FROM curated.fact_international_match
    WHERE match_date >= DATE '2022-01-01'
    UNION ALL
    SELECT away_team_code, away_score, home_score, tournament_tier
    FROM curated.fact_international_match
    WHERE match_date >= DATE '2022-01-01'
),

weighted AS (
    SELECT team_match.team_code, team_match.goals_for, team_match.goals_against, tier_weight.weight
    FROM team_match
    JOIN curated.dim_tournament_tier_weight tier_weight USING (tournament_tier)
),

means AS (
    SELECT
        team_code,
        COUNT(*)                                   AS match_count,
        SUM(weight)                                AS weight_sum,
        SUM(weight * goals_for)     / SUM(weight)  AS goals_for_mean,
        SUM(weight * goals_against) / SUM(weight)  AS goals_against_mean
    FROM weighted
    GROUP BY team_code
),

goal_stats AS (
    SELECT
        weighted.team_code,
        means.match_count,
        means.goals_for_mean,
        SQRT(SUM(weighted.weight * (weighted.goals_for - means.goals_for_mean) * (weighted.goals_for - means.goals_for_mean)) / means.weight_sum) AS goals_for_std,
        means.goals_against_mean,
        SQRT(SUM(weighted.weight * (weighted.goals_against - means.goals_against_mean) * (weighted.goals_against - means.goals_against_mean)) / means.weight_sum) AS goals_against_std
    FROM weighted
    JOIN means USING (team_code)
    GROUP BY weighted.team_code, means.match_count, means.goals_for_mean, means.goals_against_mean, means.weight_sum
)

SELECT
    -- identity
    team_current.team_code,
    team_current.team_name,
    team_current.confederation,
    team_current.is_wc2026_qualifier,

    -- FIFA ranking          (from curated.fact_team_fifa_ranking via dim_team_current)
    team_current.fifa_rank,
    team_current.fifa_points,
    team_current.fifa_rank_change,
    team_current.fifa_snapshot_date,

    -- economics             (from curated.fact_team_economics via dim_team_current)
    team_current.economics_year,
    team_current.gdp_per_capita_usd_latest,
    team_current.population_latest,

    -- recent form           (from curated.dim_team_recent_form)
    recent_form.last_match_date,
    recent_form.matches_last_10,
    recent_form.wins_last_10,
    recent_form.draws_last_10,
    recent_form.losses_last_10,
    recent_form.goals_for_last_10,
    recent_form.goals_against_last_10,
    recent_form.goal_difference_last_10,
    recent_form.form_points_last_10,
    recent_form.matches_last_5,
    recent_form.goals_for_last_5,
    recent_form.goals_against_last_5,
    recent_form.competitive_matches_last_10,
    recent_form.competitive_goal_difference_last_10,
    recent_form.competitive_form_points_last_10,
    recent_form.avg_opponent_fifa_rank_last_10,

    -- historical goal stats since 2022 (from CTE above, ultimately fact_international_match)
    goal_stats.match_count          AS historical_match_count,
    goal_stats.goals_for_mean       AS historical_goals_for_mean,
    goal_stats.goals_for_std        AS historical_goals_for_std,
    goal_stats.goals_against_mean   AS historical_goals_against_mean,
    goal_stats.goals_against_std    AS historical_goals_against_std,

    -- squad-pool xG (from curated.fact_team_xg). NULL for ~15 qualifiers
    -- not yet in raw.squad_xg_ratings.
    team_xg.players_in_pool                   AS xg_players_in_pool,
    team_xg.club_data_coverage_percent        AS xg_club_data_coverage_percent,
    team_xg.top_11_blended_xg_per_90,
    team_xg.top_11_national_team_xg_per_90,
    team_xg.top_11_club_xg_per_90,
    team_xg.top_11_club_xa_per_90,
    team_xg.top_3_attackers_blended_xg_per_90,
    team_xg.forwards_blended_xg_per_90,

    -- squad-pool xGA (from curated.fact_team_xg_against). NULL for teams
    -- without SB matches AND without club coverage; ~40 of 98 dim_team rows.
    team_xga.national_team_matches_in_sample      AS xga_sb_matches_in_sample,
    team_xga.national_team_xga_per_90,
    team_xga.national_team_goals_conceded_per_90,
    team_xga.national_team_xga_vs_actual_gap_per_90,
    team_xga.squad_club_xga_per_game,
    team_xga.blended_xga_per_90
FROM curated.dim_team_current team_current
LEFT JOIN curated.dim_team_recent_form recent_form USING (team_code)
LEFT JOIN goal_stats                   USING (team_code)
LEFT JOIN curated.fact_team_xg team_xg USING (team_code)
LEFT JOIN curated.fact_team_xg_against team_xga USING (team_code)
WHERE team_current.is_wc2026_qualifier
ORDER BY team_current.fifa_rank NULLS LAST;
