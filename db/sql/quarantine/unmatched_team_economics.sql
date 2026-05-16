-- quarantine.unmatched_team_economics
-- Grain: one row per source row whose team_code is not in curated.dim_team.
-- Source: raw.country_gdp_per_capita ∪ raw.country_population
-- Plan: docs/plans/2026-05-14-002-feat-fact-team-economics-and-fifa-ranking-plan.md (Unit 2)
--
-- Same CTE pipeline as curated.fact_team_economics, opposite WHERE filter
-- (dim_team_code IS NULL).

CREATE OR REPLACE TABLE quarantine.unmatched_team_economics AS

WITH
gdp_raw AS (
    SELECT team_code, year, gdp_per_capita_usd, NULL::DOUBLE AS population, 'gdp' AS source
    FROM raw.country_gdp_per_capita
),

pop_raw AS (
    SELECT team_code, year, NULL::DOUBLE AS gdp_per_capita_usd, population, 'population' AS source
    FROM raw.country_population
),

unioned AS (
    SELECT * FROM gdp_raw
    UNION ALL
    SELECT * FROM pop_raw
),

resolved AS (
    SELECT
        u.team_code,
        u.year,
        u.gdp_per_capita_usd,
        u.population,
        u.source,
        d.team_code AS dim_team_code
    FROM unioned u
    LEFT JOIN curated.dim_team d ON d.team_code = u.team_code
)

SELECT
    team_code,
    CAST(year AS INTEGER) AS year,
    gdp_per_capita_usd,
    population,
    source,
    'team_code not in dim_team' AS reason
FROM resolved
WHERE dim_team_code IS NULL;
