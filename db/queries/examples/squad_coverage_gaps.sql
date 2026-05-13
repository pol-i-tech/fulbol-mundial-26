-- Players in dim_player (WC2026 candidate pool) with NO row in fact_player_xg —
-- i.e., players we have zero xG data for. These rows surface data-quality
-- gaps to chase (more Understat coverage, missing minutes thresholds, etc.).
--
-- Run:
--   duckdb data/wc2026.duckdb -c "$(cat db/queries/examples/squad_coverage_gaps.sql)"

SELECT
    p.country_code,
    COUNT(*) AS players_with_no_xg,
    LIST(p.display_name ORDER BY p.display_name) AS player_names
FROM curated.dim_player p
LEFT JOIN curated.fact_player_xg f USING (player_id)
WHERE p.is_active
  AND f.player_id IS NULL
GROUP BY p.country_code
ORDER BY players_with_no_xg DESC;
