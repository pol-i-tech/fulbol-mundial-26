-- curated.fact_team_xg_against_wc2022
-- Grain: one row per team_code (the 32 WC2022 teams).
-- Source: raw.team_defense_ratings_wc2022 — a pre-aggregated, point-in-time
--         snapshot of defensive ratings as of WC2022 kickoff. Built upstream
--         of this database by the methodology pipeline; preserved here as a
--         held-out backtest input that does NOT leak post-WC2022 data.
-- Naming: follows db/NAMING.md.
--
-- The WC2022-cut sibling of curated.fact_team_xg_against. Used by the
-- methodology/curated-poisson-luck WC2022 backtest harness to honestly
-- include a defensive signal that reflects the team's state at the moment
-- WC2022 kicked off, not retrofitted from later tournaments.
--
-- All columns prefixed pre_wc2022_ to make the temporal lock explicit.

CREATE OR REPLACE TABLE curated.fact_team_xg_against_wc2022 AS

WITH resolved AS (
    SELECT
        dim_team.team_code,
        wc2022.nation,
        wc2022.defensive_rating,
        wc2022.tournament_xga,
        wc2022.club_xga_avg,
        wc2022.club_sample_size,
        wc2022.used_fallback
    FROM raw.team_defense_ratings_wc2022 AS wc2022
    LEFT JOIN curated.dim_team ON dim_team.team_name = wc2022.nation
)
SELECT
    team_code,
    nation                                                   AS team_name,
    defensive_rating                                         AS pre_wc2022_defensive_rating,
    tournament_xga                                           AS pre_wc2022_tournament_xga_per_90,
    club_xga_avg                                             AS pre_wc2022_club_xga_avg_per_game,
    club_sample_size                                         AS pre_wc2022_club_sample_size,
    used_fallback                                            AS pre_wc2022_used_fallback,
    -- Blended xGA per 90: 60% national + 40% club when both available.
    CASE
        WHEN tournament_xga IS NOT NULL AND club_xga_avg IS NOT NULL
            THEN ROUND(0.6 * tournament_xga + 0.4 * club_xga_avg, 4)
        WHEN tournament_xga IS NOT NULL THEN tournament_xga
        WHEN club_xga_avg IS NOT NULL THEN club_xga_avg
        ELSE NULL
    END                                                      AS pre_wc2022_blended_xga_per_90,
    CURRENT_DATE                                             AS as_of_date
FROM resolved
WHERE team_code IS NOT NULL;
