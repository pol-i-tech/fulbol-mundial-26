-- Attack rating vs defense rating per WC2026 qualifier.
-- Scatter-plot-ready: top-right quadrant = balanced strong sides,
-- top-left = high-scoring leaky teams, bottom-right = defensive specialists.
-- Naming: follows db/NAMING.md.
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
    team.team_code,
    team.team_name,
    team.confederation,
    ROUND(attack.attack_rating, 4)   AS attack_rating,
    ROUND(defense.defense_rating, 4) AS defense_rating,
    ROUND(attack.attack_rating - defense.defense_rating, 4) AS attack_minus_defense
FROM curated.dim_team team
LEFT JOIN attack  USING (team_code)
LEFT JOIN defense USING (team_code)
WHERE team.is_wc2026_qualifier
  AND attack.attack_rating IS NOT NULL
ORDER BY attack_minus_defense DESC NULLS LAST;
