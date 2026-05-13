-- Per-team rating matrix across the three internal rating layers
-- (M1_History / M2_Season / M3_RecentForm). The "Golden Zone" rule
-- (all three layers agree on a team being top-tier) is a one-step
-- filter away.
--
-- Run:
--   duckdb data/wc2026.duckdb -c "$(cat db/queries/examples/model_agreement_matrix.sql)"

PIVOT (
    SELECT
        t.team_code,
        t.team_name,
        t.confederation,
        ftr.rating_type,
        ftr.rating_value
    FROM curated.fact_team_rating ftr
    JOIN curated.dim_team t USING (team_code)
    WHERE t.is_wc2026_qualifier
      AND ftr.rating_type IN ('historical', 'season', 'recent_form')
)
ON rating_type
USING ROUND(MAX(rating_value), 4)
ORDER BY season DESC NULLS LAST;
