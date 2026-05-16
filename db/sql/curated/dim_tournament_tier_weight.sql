-- curated.dim_tournament_tier_weight
-- Primary key: tournament_tier
-- Source: db/masters/tournament_tier_weights.csv
--
-- Single source of truth for the per-tier match-importance weight applied
-- when computing weighted historical statistics (e.g., per-team goal mean and
-- std-dev in methodology/curated-poisson-luck/queries/team_goal_stats.sql).
--
-- Replaces hardcoded CASE blocks scattered across query files. Future models
-- that need a tier weight JOIN this dim; they do not introduce new literals.
--
-- The four tier slugs must agree with the tier set produced by
-- curated.fact_international_match.tournament_tier (verified in
-- tools/verify_duckdb.py).

CREATE OR REPLACE TABLE curated.dim_tournament_tier_weight AS
SELECT * FROM read_csv(
    'db/masters/tournament_tier_weights.csv',
    header = true,
    delim = ',',
    quote = '"',
    columns = {
        'tournament_tier': 'VARCHAR',
        'weight':          'DOUBLE',
        'rationale':       'VARCHAR'
    }
);
