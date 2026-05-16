-- curated.fact_team_xg_against
-- Grain: one row per team_code (the teams with at least one row in dim_team).
-- Source: raw.statsbomb_team_xg (per-match xG; opponent's xg = our xGA via self-join)
--         + raw.defensive_ratings_club_2526 (per-club xGA per game)
--         + curated.fact_player_xg_per_90 (squad pressures per 90).
-- Naming: follows db/NAMING.md.
--
-- Defensive sibling of curated.fact_team_xg. Two independent xGA signals:
--   1. national_team_xga_per_90: AVG of opponent's xG across StatsBomb
--      international tournaments (WC2018, WC2022, Euro 2020, Euro 2024,
--      Copa 2024). Match-grain; per-90 ≈ per-match average since matches
--      are ~90 mins.
--   2. squad_club_xga_per_game: minutes-weighted average of each squad
--      player's CLUB xGA per game. Limited to leagues in
--      raw.defensive_ratings_club_2526 (~5 leagues, ~96 clubs).
--
-- Headline model-facing metric: blended_xga_per_90, which weights national
-- 60% / club 40% when both available, else uses whichever is present.
--
-- national_team_xga_vs_actual_gap_per_90 surfaces defensive luck:
--   positive value = defense is OVERperforming (more xGA than goals conceded)
--   negative value = defense is UNDERperforming
-- Belgium and Brazil both run large positive gaps — under a goals-only
-- model they look better than under-the-hood metrics suggest.

CREATE OR REPLACE TABLE curated.fact_team_xg_against AS

WITH
-- xGA per match: opponent's xg in the same match.
per_match_xga AS (
    SELECT
        self.competition,
        self.season,
        self.match_id,
        self.team           AS team_name,
        opp.xg              AS xga,
        self.goals_conceded
    FROM raw.statsbomb_team_xg self
    JOIN raw.statsbomb_team_xg opp
      ON opp.match_id = self.match_id
     AND opp.team <> self.team
),

per_team_national AS (
    SELECT
        team_name,
        COUNT(*)                                      AS national_team_matches_in_sample,
        COUNT(*) * 90                                 AS national_team_minutes_in_sample,
        ROUND(AVG(xga), 4)                            AS national_team_xga_per_90,
        ROUND(AVG(goals_conceded), 4)                 AS national_team_goals_conceded_per_90,
        STRING_AGG(DISTINCT competition, ', ' ORDER BY competition) AS sb_tournaments_in_sample
    FROM per_match_xga
    GROUP BY team_name
),

-- Resolve StatsBomb team name → team_code via dim_team.team_name.
-- Names like "South Korea" align with dim_team.team_name conventions.
national_resolved AS (
    SELECT
        dim_team.team_code,
        per_team_national.*
    FROM per_team_national
    JOIN curated.dim_team ON dim_team.team_name = per_team_national.team_name
),

-- Squad club xGA: for each player, look up their current_club in
-- raw.defensive_ratings_club_2526, then minutes-weighted average per team.
squad_club_xga AS (
    SELECT
        player_xg.team_code,
        COUNT(*) FILTER (WHERE club_def.xga_per_game IS NOT NULL)
            AS squad_players_with_club_xga,
        ROUND(
            SUM(club_def.xga_per_game * player_xg.club_minutes)
                FILTER (WHERE club_def.xga_per_game IS NOT NULL AND player_xg.club_minutes IS NOT NULL)
            / NULLIF(SUM(player_xg.club_minutes)
                FILTER (WHERE club_def.xga_per_game IS NOT NULL AND player_xg.club_minutes IS NOT NULL), 0),
            4
        ) AS squad_club_xga_per_game
    FROM curated.fact_player_xg_per_90 AS player_xg
    LEFT JOIN raw.defensive_ratings_club_2526 AS club_def
        ON club_def.club = player_xg.current_club
    GROUP BY player_xg.team_code
),

-- Top-11 national-team pressures per 90 from the squad pool
ranked_players AS (
    SELECT
        team_code,
        national_team_pressures_per_90,
        ROW_NUMBER() OVER (
            PARTITION BY team_code
            ORDER BY national_team_minutes DESC NULLS LAST
        ) AS national_minutes_rank
    FROM curated.fact_player_xg_per_90
),
squad_pressures AS (
    SELECT
        team_code,
        ROUND(SUM(national_team_pressures_per_90), 2) AS top_11_national_team_pressures_per_90
    FROM ranked_players
    WHERE national_minutes_rank <= 11
    GROUP BY team_code
)

SELECT
    dim_team.team_code,
    dim_team.team_name,
    dim_team.confederation,
    dim_team.is_wc2026_qualifier,
    national_resolved.national_team_matches_in_sample,
    national_resolved.national_team_minutes_in_sample,
    national_resolved.national_team_xga_per_90,
    national_resolved.national_team_goals_conceded_per_90,
    ROUND(national_resolved.national_team_xga_per_90
        - national_resolved.national_team_goals_conceded_per_90, 4)
        AS national_team_xga_vs_actual_gap_per_90,
    squad_club_xga.squad_players_with_club_xga,
    squad_club_xga.squad_club_xga_per_game,
    squad_pressures.top_11_national_team_pressures_per_90,
    -- Blended xGA per 90. Weight 60% national + 40% club when both available.
    CASE
        WHEN national_resolved.national_team_xga_per_90 IS NOT NULL
         AND squad_club_xga.squad_club_xga_per_game IS NOT NULL
            THEN ROUND(0.6 * national_resolved.national_team_xga_per_90
                     + 0.4 * squad_club_xga.squad_club_xga_per_game, 4)
        WHEN national_resolved.national_team_xga_per_90 IS NOT NULL
            THEN national_resolved.national_team_xga_per_90
        WHEN squad_club_xga.squad_club_xga_per_game IS NOT NULL
            THEN squad_club_xga.squad_club_xga_per_game
        ELSE NULL
    END AS blended_xga_per_90,
    national_resolved.sb_tournaments_in_sample,
    CURRENT_DATE AS as_of_date
FROM curated.dim_team
LEFT JOIN national_resolved USING (team_code)
LEFT JOIN squad_club_xga    USING (team_code)
LEFT JOIN squad_pressures   USING (team_code);
