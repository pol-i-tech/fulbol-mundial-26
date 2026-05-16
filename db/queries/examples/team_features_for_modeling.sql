-- Every team feature for the 48 WC2026 qualifiers in one read.
-- Joins live inside curated.dim_team_current (denormalized view); the modeler
-- never has to think about fact_team_economics or fact_team_fifa_ranking.
--
-- Use this as the canonical model input for country-context features.
-- Plan: docs/plans/2026-05-14-002-feat-fact-team-economics-and-fifa-ranking-plan.md

SELECT
    team_code,
    team_name,
    confederation,
    fifa_rank,
    fifa_points,
    fifa_rank_change,
    gdp_per_capita_usd_latest,
    population_latest,
    economics_year,
    fifa_snapshot_date
FROM curated.dim_team_current
WHERE is_wc2026_qualifier
ORDER BY fifa_rank NULLS LAST;
