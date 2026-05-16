-- curated.fact_international_match
-- Grain: one row per completed international match.
-- Source: raw.international_matches (derived from data/raw/martj42/latest/results.csv).
-- FK integrity: both home_team_code AND away_team_code MUST exist in
--   curated.dim_team (LEFT JOIN dim_team twice, then split via WHERE).
-- Plan: docs/plans/2026-05-15-001-feat-fact-international-match-plan.md (Unit 2)
--
-- Future-fixture rows (home_score/away_score NULL in the source CSV) are
-- excluded by the WHERE clause -- this fact holds RESULTS, not schedules.
--
-- tournament_tier is derived from the source `tournament` string via an
-- explicit CASE block below. New tournaments fall to tier_4_friendly_or_other;
-- tools/verify_duckdb.py logs the count as informational.

CREATE OR REPLACE TABLE curated.fact_international_match AS

WITH
source AS (
    SELECT
        match_date,
        home_team_code,
        away_team_code,
        CAST(home_score AS INTEGER)            AS home_score,
        CAST(away_score AS INTEGER)            AS away_score,
        tournament,
        city,
        country                                AS host_country,
        neutral_site,
        CASE
            WHEN tournament = 'FIFA World Cup'
                THEN 'tier_1_world_cup'
            WHEN tournament IN (
                    'UEFA Euro',
                    'Copa América',
                    'African Cup of Nations',
                    'AFC Asian Cup',
                    'Gold Cup',
                    'CONCACAF Championship',
                    'Oceania Nations Cup',
                    'Confederations Cup'
                )
                THEN 'tier_2_continental_final'
            WHEN tournament LIKE '%qualification%'
                 OR tournament IN ('UEFA Nations League', 'CONCACAF Nations League')
                THEN 'tier_3_qualifier_or_nations_league'
            ELSE 'tier_4_friendly_or_other'
        END                                    AS tournament_tier
    FROM raw.international_matches
    WHERE home_score IS NOT NULL
      AND away_score IS NOT NULL  -- exclude future fixtures
),

resolved AS (
    -- LEFT JOIN twice; unmatched rows route to quarantine.unmatched_international_matches.
    SELECT
        s.*,
        dh.team_code AS dim_home_code,
        da.team_code AS dim_away_code
    FROM source s
    LEFT JOIN curated.dim_team dh ON dh.team_code = s.home_team_code
    LEFT JOIN curated.dim_team da ON da.team_code = s.away_team_code
)

SELECT
    match_date,
    home_team_code,
    away_team_code,
    home_score,
    away_score,
    home_score - away_score                                          AS goal_difference,
    CASE
        WHEN home_score > away_score THEN 'H'
        WHEN home_score < away_score THEN 'A'
        ELSE 'D'
    END                                                              AS result,
    tournament,
    tournament_tier,
    (tournament_tier <> 'tier_4_friendly_or_other')                  AS is_competitive,
    city,
    host_country,
    neutral_site
FROM resolved
WHERE dim_home_code IS NOT NULL
  AND dim_away_code IS NOT NULL;
