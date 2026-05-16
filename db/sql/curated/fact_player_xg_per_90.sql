-- curated.fact_player_xg_per_90
-- Grain: one row per player_id (1:1 with curated.dim_player active rows).
-- Source: raw.squad_xg_ratings — the WC2026 candidate-pool table that already
--         carries pre-blended xG per 90 combining StatsBomb national-team xG
--         and Understat club xG.
-- Naming: follows db/NAMING.md.
--
-- The squad_xg_ratings pipeline (upstream of this database) produces
-- blended_xg90 from two ingredients:
--   - nat_xg_per_90: derived from StatsBomb shot-event data across the
--                    player's national-team tournament history.
--   - club_xg_per_90: derived from Understat club-season aggregations
--                     (2024–25 season as of v1).
-- The blend formula is owned by the upstream pipeline. This fact preserves
-- both components plus the blend so downstream models can re-mix if needed.
--
-- low_confidence flags players whose nat or club sample is too small for
-- the per-90 rate to be stable (e.g., Dybala 3.07 xg/90 in 23 nat minutes).

CREATE OR REPLACE TABLE curated.fact_player_xg_per_90 AS

WITH joined AS (
    SELECT
        dim_player.player_id,
        dim_player.country_code                 AS team_code,
        squad.position,
        squad.club                              AS current_club,
        squad.league                            AS current_league,
        squad.nat_matches                       AS national_team_matches,
        squad.nat_minutes                       AS national_team_minutes,
        squad.nat_xg_per_90                     AS national_team_xg_per_90,
        squad.nat_shots_per_90                  AS national_team_shots_per_90,
        squad.nat_key_passes_per_90             AS national_team_key_passes_per_90,
        squad.nat_prog_passes_per_90            AS national_team_prog_passes_per_90,
        squad.nat_prog_carries_per_90           AS national_team_prog_carries_per_90,
        squad.nat_pressures_per_90              AS national_team_pressures_per_90,
        squad.club_minutes_2425                 AS club_minutes,
        squad.club_xg_per_90,
        squad.club_xa_per_90,
        squad.blended_xg90                      AS blended_xg_per_90,
        squad.found_in_understat,
        squad.low_confidence
    FROM raw.squad_xg_ratings AS squad
    JOIN curated.dim_player ON dim_player.display_name = squad.player
                           AND dim_player.nation_name  = squad.nation
)
SELECT
    player_id,
    team_code,
    position,
    current_club,
    current_league,
    national_team_matches,
    national_team_minutes,
    national_team_xg_per_90,
    national_team_shots_per_90,
    national_team_key_passes_per_90,
    national_team_prog_passes_per_90,
    national_team_prog_carries_per_90,
    national_team_pressures_per_90,
    club_minutes,
    club_xg_per_90,
    club_xa_per_90,
    blended_xg_per_90,
    found_in_understat,
    low_confidence,
    CURRENT_DATE AS as_of_date
FROM joined;
