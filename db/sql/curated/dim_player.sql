-- curated.dim_player
-- Primary key: player_id
-- Source: db/masters/players.csv (the player master, system of record)
-- Grain: one row per player_id; SCD Type 1 (attributes overwritten on master refresh)
-- See db/SCHEMA.md "Curated dims" section for full column docs.

CREATE OR REPLACE TABLE curated.dim_player AS
SELECT * FROM read_csv(
    'db/masters/players.csv',
    header = true,
    delim = ',',
    nullstr = '',
    columns = {
        'player_id': 'VARCHAR',
        'display_name': 'VARCHAR',
        'normalized_name': 'VARCHAR',
        'country_code': 'VARCHAR',
        'nation_name': 'VARCHAR',
        'birth_date': 'DATE',
        'birth_year': 'INTEGER',
        'position': 'VARCHAR',
        'current_club': 'VARCHAR',
        'current_league': 'VARCHAR',
        'statsbomb_name': 'VARCHAR',
        'understat_id': 'VARCHAR',
        'understat_name': 'VARCHAR',
        'is_active': 'BOOLEAN',
        'first_seen_at': 'DATE',
        'last_updated_at': 'DATE'
    }
);
