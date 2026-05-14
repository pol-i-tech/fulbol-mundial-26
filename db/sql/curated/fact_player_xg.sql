-- curated.fact_player_xg
-- Grain: one row per (player_id, source, period_id)
-- Sources unioned:
--   1. staging.matched_sb_player_summary       (source='statsbomb', period_id='sb_career_aggregated')
--   2. staging.matched_sb_player_stats_pedigree (source='statsbomb', period_id=<tournament_id>)
--   3. staging.matched_understat_player_xg     (source='understat', period_id='understat_career_aggregated')
--   4. staging.matched_understat_2526_players  (source='understat', period_id='club_2526')
-- Notes:
--   team_code is populated for tournament-grain rows (national team) and NULL for
--   club-grain rows (where 'team' is a club, not a national team).
--   xa is NULL for sources that do not carry it.

CREATE OR REPLACE TABLE curated.fact_player_xg AS

WITH sb_summary AS (
    SELECT
        s.player_id,
        'statsbomb' AS source,
        'sb_career_aggregated' AS period_id,
        tnr.team_code AS team_code,
        NULL AS club_name,
        CAST(s.minutes_played AS INTEGER) AS minutes,
        CAST(s.goals AS INTEGER) AS goals,
        CAST(s.xg AS DOUBLE) AS xg_total,
        CAST(s.xg_per_90 AS DOUBLE) AS xg_per_90,
        NULL::DOUBLE AS xa_total,
        NULL::DOUBLE AS xa_per_90,
        CAST(s.shots AS INTEGER) AS shots,
        s.as_of_date
    FROM staging.matched_sb_player_summary s
    LEFT JOIN staging.team_name_resolution tnr ON tnr.nation_name = s.team
    WHERE s.player_id IS NOT NULL
),

sb_pedigree AS (
    SELECT
        s.player_id,
        'statsbomb' AS source,
        s.season AS period_id,
        tnr.team_code AS team_code,
        NULL AS club_name,
        CAST(s.minutes AS INTEGER) AS minutes,
        CAST(s.goals AS INTEGER) AS goals,
        CAST(s.xg_total AS DOUBLE) AS xg_total,
        CAST(s.xg_per_90 AS DOUBLE) AS xg_per_90,
        NULL::DOUBLE AS xa_total,
        NULL::DOUBLE AS xa_per_90,
        CAST(s.shots AS INTEGER) AS shots,
        s.as_of_date
    FROM staging.matched_sb_player_stats_pedigree s
    LEFT JOIN staging.team_name_resolution tnr ON tnr.nation_name = s.team
    WHERE s.player_id IS NOT NULL
),

und_aggregated AS (
    SELECT
        u.player_id,
        'understat' AS source,
        'understat_career_aggregated' AS period_id,
        NULL AS team_code,
        u.last_team AS club_name,
        CAST(u.total_minutes AS INTEGER) AS minutes,
        CAST(u.total_goals AS INTEGER) AS goals,
        CAST(u.total_xg AS DOUBLE) AS xg_total,
        CAST(u.xg_per_90 AS DOUBLE) AS xg_per_90,
        CAST(u.total_xa AS DOUBLE) AS xa_total,
        CAST(u.xa_per_90 AS DOUBLE) AS xa_per_90,
        CAST(u.total_shots AS INTEGER) AS shots,
        u.as_of_date
    FROM staging.matched_understat_player_xg u
    WHERE u.player_id IS NOT NULL
),

und_2526 AS (
    SELECT
        u.player_id,
        'understat' AS source,
        'club_2526' AS period_id,
        NULL AS team_code,
        u.club AS club_name,
        CAST(u.time AS INTEGER) AS minutes,
        CAST(u.goals AS INTEGER) AS goals,
        CAST(u.xG AS DOUBLE) AS xg_total,
        CAST(u.xg_per_90 AS DOUBLE) AS xg_per_90,
        CAST(u.xA AS DOUBLE) AS xa_total,
        CAST(u.xa_per_90 AS DOUBLE) AS xa_per_90,
        CAST(u.shots AS INTEGER) AS shots,
        u.as_of_date
    FROM staging.matched_understat_2526_players u
    WHERE u.player_id IS NOT NULL
)

SELECT * FROM sb_summary
UNION ALL SELECT * FROM sb_pedigree
UNION ALL SELECT * FROM und_aggregated
UNION ALL SELECT * FROM und_2526
;
