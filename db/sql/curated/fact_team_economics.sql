-- curated.fact_team_economics
-- Grain: one row per (team_code, year)
-- Sources: raw.country_gdp_per_capita, raw.country_population
-- FK integrity: every team_code MUST exist in curated.dim_team (LEFT JOIN then split).
-- Plan: docs/plans/2026-05-14-002-feat-fact-team-economics-and-fifa-ranking-plan.md (Unit 2)
--
-- Style (R9): CTEs declared top-to-bottom in data-flow order, LEFT JOIN against
-- dim_team, then split via WHERE-clause on dim_team_code IS NOT NULL.
-- The mirror quarantine table (db/sql/quarantine/unmatched_team_economics.sql)
-- holds the inverse split.

CREATE OR REPLACE TABLE curated.fact_team_economics AS

WITH
gdp_raw AS (
    SELECT team_code, year, gdp_per_capita_usd
    FROM raw.country_gdp_per_capita
),

pop_raw AS (
    SELECT team_code, year, population
    FROM raw.country_population
),

merged AS (
    -- FULL OUTER so a (team, year) with only one of the two measures still appears.
    -- World Bank GDP coverage is thinner than population coverage for some economies
    -- (notably 1980s data for smaller states), so this avoids dropping those rows.
    SELECT
        COALESCE(g.team_code, p.team_code) AS team_code,
        COALESCE(g.year,      p.year)      AS year,
        g.gdp_per_capita_usd,
        p.population
    FROM gdp_raw g
    FULL OUTER JOIN pop_raw p USING (team_code, year)
),

resolved AS (
    -- LEFT JOIN: rows with dim_team_code IS NULL route to quarantine,
    -- rows with dim_team_code IS NOT NULL feed the fact.
    SELECT
        m.team_code,
        m.year,
        m.gdp_per_capita_usd,
        m.population,
        d.team_code AS dim_team_code
    FROM merged m
    LEFT JOIN curated.dim_team d ON d.team_code = m.team_code
)

SELECT
    team_code,
    CAST(year AS INTEGER)            AS year,
    CAST(gdp_per_capita_usd AS DOUBLE) AS gdp_per_capita_usd,
    CAST(population AS DOUBLE)       AS population
FROM resolved
WHERE dim_team_code IS NOT NULL;
