-- curated.dim_team_recent_form (VIEW)
-- Grain: one row per team_code -- the read-optimized recent-form projection
--        modelers consume to get every form feature in one query.
-- Source: staging.team_match (long-form team-grain unpivot) plus
--         curated.fact_team_fifa_ranking (snapshot ranks for strength-of-schedule).
-- Plan: docs/plans/2026-05-15-001-feat-fact-international-match-plan.md (Unit 3)
--
-- Two recency windows exposed: last-5 (current form) and last-10 (qualifying-cycle
-- form). Competitive-only variants use an independent recency ranking so a team
-- whose last 10 matches are 6 competitive + 4 friendlies has
-- competitive_matches_last_10 counted over the last 10 *competitive* matches,
-- which may extend further back than the last-10 overall.
--
-- SoS LIMITATION: avg_opponent_fifa_rank_last_10 joins fact_team_fifa_ranking,
-- which currently holds only a single snapshot (the latest edition). So this is
-- "average current opponent rank", not "average rank at time of match". A future
-- fact_team_fifa_ranking_history fact (deferred) would let this column become
-- temporally accurate.
--
-- Naming: this file follows the project SQL nomenclature standard. See db/NAMING.md.

CREATE OR REPLACE VIEW curated.dim_team_recent_form AS

WITH
ranked AS (
    SELECT
        team_match.*,
        ROW_NUMBER() OVER (
            PARTITION BY team_match.team_code
            ORDER BY team_match.match_date DESC
        ) AS recency_rank,
        ROW_NUMBER() OVER (
            PARTITION BY team_match.team_code, team_match.is_competitive
            ORDER BY team_match.match_date DESC
        ) AS competitive_recency_rank
    FROM staging.team_match
),

per_team AS (
    SELECT
        team_code,
        MAX(match_date)                                                                  AS last_match_date,

        -- last-10 window (all matches)
        COUNT(*)            FILTER (WHERE recency_rank <= 10)                            AS matches_last_10,
        COUNT(*)            FILTER (WHERE recency_rank <= 10 AND outcome = 'W')          AS wins_last_10,
        COUNT(*)            FILTER (WHERE recency_rank <= 10 AND outcome = 'D')          AS draws_last_10,
        COUNT(*)            FILTER (WHERE recency_rank <= 10 AND outcome = 'L')          AS losses_last_10,
        SUM(team_score)     FILTER (WHERE recency_rank <= 10)                            AS goals_for_last_10,
        SUM(opponent_score) FILTER (WHERE recency_rank <= 10)                            AS goals_against_last_10,
        SUM(goal_difference) FILTER (WHERE recency_rank <= 10)                           AS goal_difference_last_10,
        SUM(CASE outcome WHEN 'W' THEN 3 WHEN 'D' THEN 1 ELSE 0 END)
            FILTER (WHERE recency_rank <= 10)                                            AS form_points_last_10,

        -- last-5 window (all matches)
        COUNT(*)            FILTER (WHERE recency_rank <= 5)                             AS matches_last_5,
        COUNT(*)            FILTER (WHERE recency_rank <= 5 AND outcome = 'W')           AS wins_last_5,
        COUNT(*)            FILTER (WHERE recency_rank <= 5 AND outcome = 'D')           AS draws_last_5,
        COUNT(*)            FILTER (WHERE recency_rank <= 5 AND outcome = 'L')           AS losses_last_5,
        SUM(team_score)     FILTER (WHERE recency_rank <= 5)                             AS goals_for_last_5,
        SUM(opponent_score) FILTER (WHERE recency_rank <= 5)                             AS goals_against_last_5,
        SUM(goal_difference) FILTER (WHERE recency_rank <= 5)                            AS goal_difference_last_5,
        SUM(CASE outcome WHEN 'W' THEN 3 WHEN 'D' THEN 1 ELSE 0 END)
            FILTER (WHERE recency_rank <= 5)                                             AS form_points_last_5,

        -- competitive-only last-10 (independent recency window)
        COUNT(*)
            FILTER (WHERE is_competitive AND competitive_recency_rank <= 10)             AS competitive_matches_last_10,
        SUM(goal_difference)
            FILTER (WHERE is_competitive AND competitive_recency_rank <= 10)             AS competitive_goal_difference_last_10,
        SUM(CASE outcome WHEN 'W' THEN 3 WHEN 'D' THEN 1 ELSE 0 END)
            FILTER (WHERE is_competitive AND competitive_recency_rank <= 10)             AS competitive_form_points_last_10
    FROM ranked
    GROUP BY team_code
),

last_match AS (
    SELECT
        team_code,
        opponent_team_code AS last_match_opponent_team_code,
        outcome            AS last_match_outcome
    FROM ranked
    WHERE recency_rank = 1
),

strength_of_schedule AS (
    -- Average opponent FIFA rank over last 10 matches. LEFT JOIN means
    -- opponents missing from fact_team_fifa_ranking contribute NULL,
    -- which AVG ignores.
    SELECT
        ranked.team_code,
        AVG(ranking.rank)::DOUBLE AS avg_opponent_fifa_rank_last_10
    FROM ranked
    LEFT JOIN curated.fact_team_fifa_ranking ranking
        ON ranking.team_code = ranked.opponent_team_code
    WHERE ranked.recency_rank <= 10
    GROUP BY ranked.team_code
)

SELECT
    team.team_code,
    team.team_name,
    per_team.last_match_date,
    last_match.last_match_opponent_team_code,
    last_match.last_match_outcome,

    per_team.matches_last_10,
    per_team.wins_last_10,
    per_team.draws_last_10,
    per_team.losses_last_10,
    per_team.goals_for_last_10,
    per_team.goals_against_last_10,
    per_team.goal_difference_last_10,
    per_team.form_points_last_10,

    per_team.matches_last_5,
    per_team.wins_last_5,
    per_team.draws_last_5,
    per_team.losses_last_5,
    per_team.goals_for_last_5,
    per_team.goals_against_last_5,
    per_team.goal_difference_last_5,
    per_team.form_points_last_5,

    per_team.competitive_matches_last_10,
    per_team.competitive_goal_difference_last_10,
    per_team.competitive_form_points_last_10,

    strength_of_schedule.avg_opponent_fifa_rank_last_10,

    CURRENT_DATE AS as_of_date
FROM curated.dim_team team
LEFT JOIN per_team             ON per_team.team_code             = team.team_code
LEFT JOIN last_match           ON last_match.team_code           = team.team_code
LEFT JOIN strength_of_schedule ON strength_of_schedule.team_code = team.team_code;
