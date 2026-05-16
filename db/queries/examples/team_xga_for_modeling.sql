-- Squad-aggregate xGA per 90 for every WC2026 qualifier.
--
-- blended_xga_per_90 is the headline metric: 60% national-team xGA (avg of
-- opponent's xG across StatsBomb international tournaments) + 40% squad
-- club xGA (minutes-weighted club defense from defensive_ratings_club_2526
-- via player.current_club).
--
-- xga_vs_actual_gap: positive = defense is OVERperforming (allowing more
-- xGA than goals conceded). Belgium, Brazil, England, France all show
-- large positive gaps — defenses that have been getting bailed out by
-- goalkeeping or finishing luck.
--
-- Naming: follows db/NAMING.md.
--
-- Run via:
--   duckdb data/wc2026.duckdb < db/queries/examples/team_xga_for_modeling.sql

SELECT
    team_code,
    team_name,
    confederation,
    national_team_matches_in_sample            AS sb_matches,
    ROUND(national_team_xga_per_90,        2)  AS nat_xga,
    ROUND(national_team_goals_conceded_per_90, 2) AS nat_actual_gc,
    ROUND(national_team_xga_vs_actual_gap_per_90, 2) AS xga_vs_actual_gap,
    squad_players_with_club_xga                AS players_w_club,
    ROUND(squad_club_xga_per_game,         2)  AS club_xga,
    ROUND(blended_xga_per_90,              2)  AS blended_xga,
    sb_tournaments_in_sample
FROM curated.fact_team_xg_against
WHERE is_wc2026_qualifier
ORDER BY blended_xga_per_90 ASC NULLS LAST;
