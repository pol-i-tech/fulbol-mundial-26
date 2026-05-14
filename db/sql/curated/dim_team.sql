-- curated.dim_team
-- Primary key: team_code (FIFA 3-letter natural key)
-- Source: db/masters/teams.csv (derived from weekly_pull.py FIFA dicts)
-- Grain: one row per team_code

CREATE OR REPLACE TABLE curated.dim_team AS
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
);
