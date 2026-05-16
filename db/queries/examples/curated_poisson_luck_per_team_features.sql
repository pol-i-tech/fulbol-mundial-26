-- Inspect the wide model-input table consumed by methodology/curated-poisson-luck.
-- One row per WC2026 qualifier with every feature the model uses: FIFA, economics,
-- recent form, and tier-weighted historical goal mean + std-dev since 2022.
--
-- Canonical home for the query:
--   methodology/curated-poisson-luck/queries/team_model_features.sql
--
-- This example is a 1:1 wrapper so the read pattern is discoverable from
-- db/queries/examples/ alongside the other curated read patterns.
--
-- Naming: follows db/NAMING.md. Allowed shorts: avg, std, mean, stats.
--
-- Run via:
--   duckdb data/wc2026.duckdb < db/queries/examples/curated_poisson_luck_per_team_features.sql

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
    team_current.team_code,
    team_current.team_name,
    team_current.confederation,
    team_current.fifa_rank,
    team_current.fifa_points,
    ROUND(team_current.gdp_per_capita_usd_latest, 0)         AS gdp_per_capita_usd,
    team_current.population_latest,
    recent_form.matches_last_10,
    recent_form.goals_for_last_10,
    recent_form.goals_against_last_10,
    recent_form.form_points_last_10,
    goal_stats.match_count                                   AS historical_match_count,
    ROUND(goal_stats.goals_for_mean,     3)                  AS historical_goals_for_mean,
    ROUND(goal_stats.goals_for_std,      3)                  AS historical_goals_for_std,
    ROUND(goal_stats.goals_against_mean, 3)                  AS historical_goals_against_mean,
    ROUND(goal_stats.goals_against_std,  3)                  AS historical_goals_against_std
FROM curated.dim_team_current team_current
LEFT JOIN curated.dim_team_recent_form recent_form USING (team_code)
LEFT JOIN goal_stats USING (team_code)
WHERE team_current.is_wc2026_qualifier
ORDER BY team_current.fifa_rank NULLS LAST;
