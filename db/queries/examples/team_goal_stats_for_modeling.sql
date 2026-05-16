-- Per-team goals-scored and goals-conceded mean + std-dev, tier-weighted,
-- since 2022-01-01. Computed entirely from curated.fact_international_match.
--
-- Canonical home for the query: methodology/curated-poisson-luck/queries/team_goal_stats.sql
-- This mirror exists so model-builders can discover the goal-stats pattern from
-- db/queries/examples/ alongside the other curated read patterns.
--
-- Tier weights sourced from curated.dim_tournament_tier_weight
-- (single source of truth, committed at db/masters/tournament_tier_weights.csv).
--
-- Naming: follows db/NAMING.md. Allowed shorts: avg, std, mean, stats.
--
-- Run via: duckdb data/wc2026.duckdb < db/queries/examples/team_goal_stats_for_modeling.sql

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
    goal_stats.team_code,
    team.team_name,
    team.confederation,
    goal_stats.match_count,
    ROUND(goal_stats.goals_for_mean,     3) AS goals_for_mean,
    ROUND(goal_stats.goals_for_std,      3) AS goals_for_std,
    ROUND(goal_stats.goals_against_mean, 3) AS goals_against_mean,
    ROUND(goal_stats.goals_against_std,  3) AS goals_against_std
FROM goal_stats
JOIN curated.dim_team team USING (team_code)
WHERE team.is_wc2026_qualifier
ORDER BY goal_stats.goals_for_mean DESC;
