-- Squad-aggregate xG per 90 for every WC2026 qualifier.
--
-- top_11_blended_xg_per_90 is the headline metric: take the 11 players per
-- team with the most national-team minutes (proxy for likely starting XI),
-- sum their blended (club+national) xG per 90. This is the team's expected
-- goal output per match, suitable as a model feature.
--
-- club_data_coverage_percent flags teams whose Understat coverage is thin
-- (e.g., Brazil's domestic league is not in Understat). Low coverage means
-- the xi_club_xg column is unreliable for that team; xi_nat_xg is fine.
--
-- Naming: follows db/NAMING.md.
--
-- Run via:
--   duckdb data/wc2026.duckdb < db/queries/examples/team_xg_for_modeling.sql

SELECT
    team_code,
    team_name,
    confederation,
    players_in_pool,
    club_data_coverage_percent,
    ROUND(top_11_blended_xg_per_90,        2) AS xi_xg_per_90,
    ROUND(top_11_national_team_xg_per_90,  2) AS xi_national_team_xg,
    ROUND(top_11_club_xg_per_90,           2) AS xi_club_xg,
    ROUND(top_11_club_xa_per_90,           2) AS xi_club_xa,
    ROUND(top_3_attackers_blended_xg_per_90, 2) AS top_3_attackers_xg,
    forwards_in_pool,
    ROUND(all_pool_avg_blended_xg_per_90,  3) AS squad_avg_xg_per_90
FROM curated.fact_team_xg
WHERE is_wc2026_qualifier
ORDER BY top_11_blended_xg_per_90 DESC NULLS LAST;
