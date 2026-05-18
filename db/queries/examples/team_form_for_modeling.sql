-- Recent-form features for every WC2026 qualifier, single-table read.
-- Joins live inside curated.dim_team_recent_form; modelers don't see them.
-- Run via:  duckdb data/wc2026.duckdb < db/queries/examples/team_form_for_modeling.sql

SELECT
    f.team_code,
    f.team_name,
    f.last_match_date,
    f.matches_last_10,
    f.wins_last_10,
    f.draws_last_10,
    f.losses_last_10,
    f.goal_diff_last_10,
    f.form_points_last_10,
    f.competitive_matches_last_10,
    f.competitive_goal_diff_last_10,
    f.competitive_form_points_last_10,
    f.avg_opponent_fifa_rank_last_10
FROM curated.dim_team_recent_form f
JOIN curated.dim_team d USING (team_code)
WHERE d.is_wc2026_qualifier
ORDER BY f.form_points_last_10 DESC NULLS LAST,
         f.goal_diff_last_10 DESC NULLS LAST;
