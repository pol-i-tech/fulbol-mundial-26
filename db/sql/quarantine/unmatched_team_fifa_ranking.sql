-- quarantine.unmatched_team_fifa_ranking
-- Grain: one row per source row whose team_code is not in curated.dim_team.
-- Source: raw.fifa_world_ranking_current
-- Plan: docs/plans/2026-05-14-002-feat-fact-team-economics-and-fifa-ranking-plan.md (Unit 3)
--
-- Same CTE pipeline as curated.fact_team_fifa_ranking, opposite WHERE filter
-- (dim_team_code IS NULL).

CREATE OR REPLACE TABLE quarantine.unmatched_team_fifa_ranking AS

WITH
source AS (
    SELECT
        team_code,
        CAST(rank AS INTEGER)            AS rank,
        CAST(points AS DOUBLE)           AS points,
        TRY_CAST(rank_change AS INTEGER) AS rank_change
    FROM raw.fifa_world_ranking_current
),

resolved AS (
    SELECT
        s.team_code,
        s.rank,
        s.points,
        s.rank_change,
        d.team_code AS dim_team_code
    FROM source s
    LEFT JOIN curated.dim_team d ON d.team_code = s.team_code
)

SELECT
    team_code,
    rank,
    points,
    rank_change,
    'team_code not in dim_team' AS reason
FROM resolved
WHERE dim_team_code IS NULL;
