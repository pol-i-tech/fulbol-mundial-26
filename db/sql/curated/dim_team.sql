-- curated.dim_team
-- Primary key: team_code (FIFA 3-letter natural key)
-- Source: db/masters/teams.csv (FIFA dicts, hand-curated confederations)
--       + data/derived/wc2026_squads_clean.parquet (ESPN squad status)
-- Grain: one row per team_code
--
-- squad_status semantics (WC2026 qualifiers only; NULL otherwise):
--   'final'       → ESPN announced the final 26-man squad
--   'preliminary' → ESPN announced a preliminary/provisional roster (35-55 names)
--   'pending'     → ESPN has not announced yet

CREATE OR REPLACE TABLE curated.dim_team AS
WITH master AS (
    SELECT * FROM read_csv(
        'db/masters/teams.csv',
        header = true,
        delim = ',',
        nullstr = '',
        columns = {
            'team_code': 'VARCHAR',
            'team_name': 'VARCHAR',
            'iso2_code': 'VARCHAR',
            'confederation': 'VARCHAR',
            'is_wc2026_qualifier': 'BOOLEAN'
        }
    )
),
squad_status AS (
    SELECT
        country_code              AS team_code,
        ANY_VALUE(announce_type)  AS announce_type,
        ANY_VALUE(announced_date) AS announced_date,
        COUNT(*)                  AS announced_player_count
    FROM read_parquet('data/derived/wc2026_squads_clean.parquet')
    GROUP BY country_code
)
SELECT
    m.team_code,
    m.team_name,
    m.iso2_code,
    m.confederation,
    m.is_wc2026_qualifier,
    CASE
        WHEN NOT m.is_wc2026_qualifier THEN NULL
        ELSE COALESCE(s.announce_type, 'pending')
    END                                   AS squad_status,
    s.announced_date                      AS squad_announced_date,
    COALESCE(s.announced_player_count, 0) AS squad_player_count
FROM master m
LEFT JOIN squad_status s USING (team_code);
