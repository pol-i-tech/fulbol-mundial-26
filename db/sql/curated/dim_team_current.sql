-- curated.dim_team_current (VIEW)
-- Grain: one row per team_code
-- Denormalized read-optimized view: dim_team enriched with the latest
-- fact_team_economics row and the current fact_team_fifa_ranking row.
-- This is the model-facing read path -- one query, every team feature.
-- Plan: docs/plans/2026-05-14-002-feat-fact-team-economics-and-fifa-ranking-plan.md (Unit 4)
--
-- Why a VIEW and not a TABLE:
--   * Zero storage cost; recomputes at query time so it never goes stale.
--   * 48-row window function on read is trivial.
--   * Keeps curated.dim_team as the pure master projection (MDM-pure).

CREATE OR REPLACE VIEW curated.dim_team_current AS

WITH
economics_reported AS (
    -- Pre-filter to rows with at least one non-null measure BEFORE picking the
    -- latest year. Otherwise World Bank's unreported-latest-year all-NULL rows
    -- (e.g., 2025 at the time of writing) would shadow the prior year's real
    -- data. Scotland (SCO) has no non-null rows at all and therefore drops out
    -- of this CTE — the LEFT JOIN below preserves the dim row with NULL
    -- measure columns, which is the correct semantics.
    SELECT team_code, year, gdp_per_capita_usd, population
    FROM curated.fact_team_economics
    WHERE gdp_per_capita_usd IS NOT NULL OR population IS NOT NULL
),

latest_economics AS (
    -- One row per team_code: the most recent reported (year, gdp, pop) tuple.
    SELECT
        team_code,
        year                 AS economics_year,
        gdp_per_capita_usd   AS gdp_per_capita_usd_latest,
        population           AS population_latest
    FROM economics_reported
    QUALIFY ROW_NUMBER() OVER (PARTITION BY team_code ORDER BY year DESC) = 1
),

current_ranking AS (
    SELECT
        team_code,
        rank          AS fifa_rank,
        points        AS fifa_points,
        rank_change   AS fifa_rank_change,
        snapshot_date AS fifa_snapshot_date
    FROM curated.fact_team_fifa_ranking
)

SELECT
    d.team_code,
    d.team_name,
    d.iso2_code,
    d.confederation,
    d.is_wc2026_qualifier,
    e.economics_year,
    e.gdp_per_capita_usd_latest,
    e.population_latest,
    r.fifa_rank,
    r.fifa_points,
    r.fifa_rank_change,
    r.fifa_snapshot_date
FROM curated.dim_team d
LEFT JOIN latest_economics e ON e.team_code = d.team_code
LEFT JOIN current_ranking  r ON r.team_code = d.team_code;
