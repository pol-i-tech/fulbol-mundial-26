-- staging.team_match
-- Grain: one row per (team_code, match_date, opponent_team_code).
-- Source: curated.fact_international_match (unpivoted; each match contributes
--         two rows -- one from each team's perspective).
-- Plan: docs/plans/2026-05-15-001-feat-fact-international-match-plan.md (Unit 3)
--
-- This is the team-grain view of the match-grain fact. Downstream queries that
-- ask "what has team X done recently" read from here -- the symmetry between
-- home and away is broken into team_score / opponent_score, and venue is
-- 'H'/'A'/'N'.
--
-- This file is the project's first SQL-defined staging table. The convention
-- mirrors curated/quarantine: CREATE OR REPLACE TABLE, header docstring, one
-- terminal SELECT after named CTEs.

CREATE OR REPLACE TABLE staging.team_match AS

WITH
home_side AS (
    SELECT
        home_team_code                                                   AS team_code,
        away_team_code                                                   AS opponent_team_code,
        match_date,
        home_score                                                       AS team_score,
        away_score                                                       AS opponent_score,
        home_score - away_score                                          AS goal_difference,
        CASE
            WHEN home_score > away_score THEN 'W'
            WHEN home_score < away_score THEN 'L'
            ELSE 'D'
        END                                                              AS outcome,
        CASE WHEN neutral_site THEN 'N' ELSE 'H' END                     AS venue,
        tournament,
        tournament_tier,
        is_competitive
    FROM curated.fact_international_match
),

away_side AS (
    SELECT
        away_team_code                                                   AS team_code,
        home_team_code                                                   AS opponent_team_code,
        match_date,
        away_score                                                       AS team_score,
        home_score                                                       AS opponent_score,
        away_score - home_score                                          AS goal_difference,
        CASE
            WHEN away_score > home_score THEN 'W'
            WHEN away_score < home_score THEN 'L'
            ELSE 'D'
        END                                                              AS outcome,
        CASE WHEN neutral_site THEN 'N' ELSE 'A' END                     AS venue,
        tournament,
        tournament_tier,
        is_competitive
    FROM curated.fact_international_match
)

SELECT * FROM home_side
UNION ALL
SELECT * FROM away_side;
