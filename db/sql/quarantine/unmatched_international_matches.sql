-- quarantine.unmatched_international_matches
-- Grain: one row per source-match whose home OR away team_code fails to resolve
--        to curated.dim_team (either normalize_country returned NULL, or the
--        returned FIFA3 is not a row in dim_team).
-- Source: raw.international_matches
-- Plan: docs/plans/2026-05-15-001-feat-fact-international-match-plan.md (Unit 2)
--
-- Same CTE pipeline as curated.fact_international_match, opposite WHERE filter.
-- Future-fixture rows are excluded here too (they're not unmatched results;
-- they're scheduled fixtures).

CREATE OR REPLACE TABLE quarantine.unmatched_international_matches AS

WITH
source AS (
    SELECT
        match_date,
        home_team_name,
        home_team_code,
        away_team_name,
        away_team_code,
        CAST(home_score AS INTEGER) AS home_score,
        CAST(away_score AS INTEGER) AS away_score,
        tournament
    FROM raw.international_matches
    WHERE home_score IS NOT NULL
      AND away_score IS NOT NULL
),

resolved AS (
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
    home_team_name,
    home_team_code,
    away_team_name,
    away_team_code,
    home_score,
    away_score,
    tournament,
    CASE
        WHEN home_team_code IS NULL AND away_team_code IS NULL THEN 'both_unresolved'
        WHEN home_team_code IS NULL                            THEN 'home_unresolved'
        WHEN away_team_code IS NULL                            THEN 'away_unresolved'
        WHEN dim_home_code  IS NULL AND dim_away_code IS NULL  THEN 'both_not_in_dim'
        WHEN dim_home_code  IS NULL                            THEN 'home_not_in_dim'
        WHEN dim_away_code  IS NULL                            THEN 'away_not_in_dim'
    END AS reason
FROM resolved
WHERE dim_home_code IS NULL
   OR dim_away_code IS NULL;
