-- Top 20 players by total xG across all matched sources (StatsBomb + Understat).
-- Demonstrates: player_id-based cross-source aggregation, JOIN to dim_player.
--
-- Run:
--   duckdb data/wc2026.duckdb -c "$(cat db/queries/examples/top_scorers_blended_xg.sql)"

SELECT
    p.player_id,
    p.display_name,
    p.country_code,
    p.current_club,
    COUNT(DISTINCT f.source)                      AS sources,
    SUM(CASE WHEN f.source = 'statsbomb' THEN f.xg_total ELSE 0 END) AS xg_statsbomb,
    SUM(CASE WHEN f.source = 'understat' THEN f.xg_total ELSE 0 END) AS xg_understat,
    SUM(f.xg_total)                               AS xg_total_all_sources,
    SUM(f.minutes)                                AS minutes_total
FROM curated.fact_player_xg f
JOIN curated.dim_player p USING (player_id)
WHERE f.xg_total IS NOT NULL
GROUP BY 1, 2, 3, 4
HAVING SUM(f.xg_total) > 0
ORDER BY xg_total_all_sources DESC
LIMIT 20;
