-- Last N results for one international team, with opponent display names.
-- Replace 'NED' with the FIFA3 code you want; tune the LIMIT.
-- Naming: follows db/NAMING.md.
-- Run via:  duckdb data/wc2026.duckdb < db/queries/examples/team_recent_results.sql

WITH team_view AS (
    SELECT
        match_date,
        CASE WHEN home_team_code = 'NED' THEN 'home' ELSE 'away' END AS side,
        CASE WHEN home_team_code = 'NED' THEN away_team_code ELSE home_team_code END AS opponent_code,
        CASE WHEN home_team_code = 'NED' THEN home_score ELSE away_score END        AS team_score,
        CASE WHEN home_team_code = 'NED' THEN away_score ELSE home_score END        AS opponent_score,
        result,
        tournament,
        tournament_tier,
        neutral_site
    FROM curated.fact_international_match
    WHERE home_team_code = 'NED' OR away_team_code = 'NED'
)
SELECT
    team_view.match_date,
    team_view.side,
    opponent.team_name             AS opponent,
    team_view.team_score           AS goals_for,
    team_view.opponent_score       AS goals_against,
    CASE
        WHEN team_view.side = 'home' AND team_view.result = 'H' THEN 'W'
        WHEN team_view.side = 'away' AND team_view.result = 'A' THEN 'W'
        WHEN team_view.result = 'D'                              THEN 'D'
        ELSE 'L'
    END                            AS outcome,
    team_view.tournament,
    team_view.neutral_site
FROM team_view
JOIN curated.dim_team opponent ON opponent.team_code = team_view.opponent_code
ORDER BY team_view.match_date DESC
LIMIT 15;
