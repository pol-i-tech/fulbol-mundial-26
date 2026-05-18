-- methodology/wc2026-predictor/queries/team_goal_stats.sql
-- Grain: one row per team_code that has played at least one international
--        match since 2022-01-01.
-- Source: curated.fact_international_match (curated-only — see db/SCHEMA.md).
-- Output columns:
--   team_code                       -- FIFA 3-letter code (joins to curated.dim_team)
--   match_count                     -- unweighted match count (sample-size honesty)
--   goals_for_weighted_mean         -- tier-weighted mean of goals scored
--   goals_for_weighted_std          -- tier-weighted std-dev of goals scored
--   goals_against_weighted_mean     -- tier-weighted mean of goals conceded
--   goals_against_weighted_std      -- tier-weighted std-dev of goals conceded
--
-- Tier weights are sourced from curated.dim_tournament_tier_weight
-- (single source of truth, committed at db/masters/tournament_tier_weights.csv).
-- Do NOT hardcode tier weights anywhere — JOIN this dim instead.
--
-- Weighted std-dev formula: SUM(w*(x-mean)^2) / SUM(w), then sqrt.
-- Two-pass: first compute weighted means, then weighted variances.
--
-- Naming: follows db/NAMING.md. Allowed shorts: avg, std, mean, stats.
--
-- Plan: docs/plans/2026-05-15-002-feat-wc2026-predictor-model-plan.md (Unit 1)

WITH
team_match AS (
    -- Unpivot fact_international_match to one row per (team_code, match).
    -- Each match contributes two rows (home + away view).
    SELECT
        home_team_code           AS team_code,
        match_date,
        home_score               AS goals_for,
        away_score               AS goals_against,
        tournament_tier
    FROM curated.fact_international_match
    WHERE match_date >= DATE '2022-01-01'

    UNION ALL

    SELECT
        away_team_code           AS team_code,
        match_date,
        away_score               AS goals_for,
        home_score               AS goals_against,
        tournament_tier
    FROM curated.fact_international_match
    WHERE match_date >= DATE '2022-01-01'
),

weighted AS (
    SELECT
        team_match.team_code,
        team_match.goals_for,
        team_match.goals_against,
        tier_weight.weight
    FROM team_match
    JOIN curated.dim_tournament_tier_weight tier_weight USING (tournament_tier)
),

means AS (
    SELECT
        team_code,
        COUNT(*)                                  AS match_count,
        SUM(weight)                               AS weight_sum,
        SUM(weight * goals_for)     / SUM(weight) AS goals_for_mean,
        SUM(weight * goals_against) / SUM(weight) AS goals_against_mean
    FROM weighted
    GROUP BY team_code
)

SELECT
    weighted.team_code,
    means.match_count,
    means.goals_for_mean                                                                                                              AS goals_for_weighted_mean,
    SQRT(SUM(weighted.weight * (weighted.goals_for - means.goals_for_mean) * (weighted.goals_for - means.goals_for_mean)) / means.weight_sum) AS goals_for_weighted_std,
    means.goals_against_mean                                                                                                          AS goals_against_weighted_mean,
    SQRT(SUM(weighted.weight * (weighted.goals_against - means.goals_against_mean) * (weighted.goals_against - means.goals_against_mean)) / means.weight_sum) AS goals_against_weighted_std
FROM weighted
JOIN means USING (team_code)
GROUP BY weighted.team_code, means.match_count, means.goals_for_mean, means.goals_against_mean, means.weight_sum
ORDER BY weighted.team_code;
