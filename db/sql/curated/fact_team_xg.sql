-- curated.fact_team_xg
-- Grain: one row per team_code (1:1 with curated.dim_team teams that have
--        at least one player in raw.squad_xg_ratings — i.e., the 52 nations
--        with squad data).
-- Source: curated.fact_player_xg_per_90 — aggregated up to team level.
-- Naming: follows db/NAMING.md.
--
-- The headline model-facing metric is **top_11_blended_xg_per_90**: take the
-- 11 players per team with the most national-team minutes (the closest proxy
-- we have to a likely starting XI without an actual lineup), then SUM their
-- blended_xg_per_90. That gives the team's expected goal output per 90.
--
-- The math: per-90 rates are additive in the team-aggregate sense. If 11
-- players each produce blended_xg_per_90 = 0.18 in a typical match, the
-- team's expected goals per match ≈ 11 × 0.18 = 1.98. (xG is allocated to
-- the shooter, so summing each player's expected contribution gives the
-- team's expected goals modulo within-squad assist-vs-shot double-count
-- which is small.)
--
-- Alternative aggregations exposed for sanity-checking and downstream use:
--   - all_pool_avg_blended_xg_per_90: simple per-player mean across the
--     full squad pool (less directly interpretable as team xG, but useful
--     as a "squad depth" comparator).
--   - forwards_blended_xg_per_90: SUM over players whose position contains
--     'F' (any history of playing as a forward).
--   - top_3_attackers_blended_xg_per_90: SUM of top-3 by blended_xg_per_90
--     among forwards — a more concentrated "front line" view.

CREATE OR REPLACE TABLE curated.fact_team_xg AS

WITH ranked AS (
    SELECT
        player_xg.*,
        ROW_NUMBER() OVER (
            PARTITION BY team_code
            ORDER BY national_team_minutes DESC NULLS LAST,
                     blended_xg_per_90    DESC NULLS LAST
        ) AS national_minutes_rank,
        ROW_NUMBER() OVER (
            PARTITION BY team_code
            ORDER BY blended_xg_per_90 DESC NULLS LAST
        ) AS blended_xg_rank,
        ROW_NUMBER() OVER (
            PARTITION BY team_code, (position LIKE '%F%')
            ORDER BY blended_xg_per_90 DESC NULLS LAST
        ) AS forward_rank
    FROM curated.fact_player_xg_per_90 AS player_xg
),

per_team_top_11 AS (
    SELECT
        team_code,
        SUM(blended_xg_per_90)                      AS top_11_blended_xg_per_90,
        SUM(national_team_xg_per_90)                AS top_11_national_team_xg_per_90,
        SUM(club_xg_per_90)                         AS top_11_club_xg_per_90,
        SUM(club_xa_per_90)                         AS top_11_club_xa_per_90,
        SUM(national_team_minutes)                  AS top_11_national_team_minutes
    FROM ranked
    WHERE national_minutes_rank <= 11
    GROUP BY team_code
),

per_team_forwards AS (
    SELECT
        team_code,
        COUNT(*)                                    AS forwards_in_pool,
        SUM(blended_xg_per_90)                      AS forwards_blended_xg_per_90,
        AVG(blended_xg_per_90)                      AS forwards_avg_blended_xg_per_90
    FROM ranked
    WHERE position LIKE '%F%'
    GROUP BY team_code
),

per_team_top_3_attackers AS (
    SELECT
        team_code,
        SUM(blended_xg_per_90) AS top_3_attackers_blended_xg_per_90
    FROM ranked
    WHERE position LIKE '%F%' AND forward_rank <= 3
    GROUP BY team_code
),

per_team_pool AS (
    SELECT
        team_code,
        COUNT(*)                                    AS players_in_pool,
        COUNT(*) FILTER (WHERE found_in_understat)  AS players_with_club_data,
        AVG(blended_xg_per_90)                      AS all_pool_avg_blended_xg_per_90,
        SUM(national_team_minutes)                  AS total_national_team_minutes,
        SUM(club_minutes)                           AS total_club_minutes
    FROM curated.fact_player_xg_per_90
    GROUP BY team_code
)

SELECT
    dim_team.team_code,
    dim_team.team_name,
    dim_team.confederation,
    dim_team.is_wc2026_qualifier,
    per_team_pool.players_in_pool,
    per_team_pool.players_with_club_data,
    ROUND(per_team_pool.players_with_club_data * 100.0 / NULLIF(per_team_pool.players_in_pool, 0), 1)
                                                                  AS club_data_coverage_percent,
    per_team_top_11.top_11_blended_xg_per_90,
    per_team_top_11.top_11_national_team_xg_per_90,
    per_team_top_11.top_11_club_xg_per_90,
    per_team_top_11.top_11_club_xa_per_90,
    per_team_top_11.top_11_national_team_minutes,
    per_team_forwards.forwards_in_pool,
    per_team_forwards.forwards_blended_xg_per_90,
    per_team_forwards.forwards_avg_blended_xg_per_90,
    per_team_top_3_attackers.top_3_attackers_blended_xg_per_90,
    per_team_pool.all_pool_avg_blended_xg_per_90,
    per_team_pool.total_national_team_minutes,
    per_team_pool.total_club_minutes,
    CURRENT_DATE                                                  AS as_of_date
FROM curated.dim_team
JOIN per_team_pool             USING (team_code)
LEFT JOIN per_team_top_11      USING (team_code)
LEFT JOIN per_team_forwards    USING (team_code)
LEFT JOIN per_team_top_3_attackers USING (team_code);
