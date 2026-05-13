-- curated.dim_tournament
-- Primary key: tournament_id (short slug; matches StatsBomb parquet 'season' values)
-- Source: db/masters/tournaments.csv (hand-curated enumeration)

CREATE OR REPLACE TABLE curated.dim_tournament AS
SELECT * FROM read_csv(
    'db/masters/tournaments.csv',
    header = true,
    delim = ',',
    nullstr = '',
    columns = {
        'tournament_id': 'VARCHAR',
        'tournament_name': 'VARCHAR',
        'start_date': 'DATE',
        'end_date': 'DATE',
        'host_country': 'VARCHAR',
        'competition_type': 'VARCHAR'
    }
);
