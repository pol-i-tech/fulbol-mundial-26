-- Attack rating vs defense rating per WC2026 qualifier.
-- Scatter-plot-ready: top-right quadrant = balanced strong sides,
-- top-left = high-scoring leaky teams, bottom-right = defensive specialists.
--
-- Run:
--   duckdb data/wc2026.duckdb -c "$(cat db/queries/examples/attack_vs_defense_per_team.sql)"

WITH attack AS (
    SELECT team_code, rating_value AS attack_rating
    FROM curated.fact_team_rating
    WHERE rating_type = 'attack'
),
defense AS (
    SELECT team_code, rating_value AS defense_rating
    FROM curated.fact_team_rating
    WHERE rating_type = 'defense'
)
SELECT
    t.team_code,
    t.team_name,
    t.confederation,
    ROUND(a.attack_rating, 4)  AS attack_rating,
    ROUND(d.defense_rating, 4) AS defense_rating,
    ROUND(a.attack_rating - d.defense_rating, 4) AS attack_minus_defense
FROM curated.dim_team t
LEFT JOIN attack a USING (team_code)
LEFT JOIN defense d USING (team_code)
WHERE t.is_wc2026_qualifier
  AND a.attack_rating IS NOT NULL
ORDER BY attack_minus_defense DESC NULLS LAST;
