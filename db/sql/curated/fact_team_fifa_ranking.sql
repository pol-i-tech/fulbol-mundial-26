-- curated.fact_team_fifa_ranking
-- Grain: one row per (team_code, snapshot_date)
-- Source: raw.fifa_world_ranking_current (single snapshot — latest FIFA ranking edition)
-- FK integrity: every team_code MUST exist in curated.dim_team (LEFT JOIN then split).
-- Plan: docs/plans/2026-05-14-002-feat-fact-team-economics-and-fifa-ranking-plan.md (Unit 3)
--
-- CREATE OR REPLACE semantics: this fact holds the MOST RECENT snapshot only.
-- A future plan can add a separate fact_team_fifa_ranking_history table for
-- historical accumulation.

CREATE OR REPLACE TABLE curated.fact_team_fifa_ranking AS

WITH
source AS (
    SELECT
        team_code,
        CAST(rank AS INTEGER)               AS rank,
        CAST(points AS DOUBLE)              AS points,
        TRY_CAST(rank_change AS INTEGER)    AS rank_change,
        COALESCE(
            TRY_CAST(ranking_date AS DATE),
            TRY_CAST(fetched_at  AS DATE),
            CURRENT_DATE
        )                                   AS snapshot_date
    FROM raw.fifa_world_ranking_current
),

resolved AS (
    SELECT
        s.team_code,
        s.rank,
        s.points,
        s.rank_change,
        s.snapshot_date,
        d.team_code AS dim_team_code
    FROM source s
    LEFT JOIN curated.dim_team d ON d.team_code = s.team_code
)

SELECT
    team_code,
    rank,
    points,
    rank_change,
    snapshot_date,
    CURRENT_TIMESTAMP AS built_at
FROM resolved
WHERE dim_team_code IS NOT NULL;
