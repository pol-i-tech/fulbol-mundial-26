-- curated.dim_model
-- Primary key: model_id (slug from results/<dir>/ name)
-- Source: db/masters/models.csv (auto-derived from results/*/MODEL.md)

CREATE OR REPLACE TABLE curated.dim_model AS
SELECT * FROM read_csv(
    'db/masters/models.csv',
    header = true,
    delim = ',',
    nullstr = '',
    columns = {
        'model_id': 'VARCHAR',
        'model_name': 'VARCHAR',
        'model_type': 'VARCHAR',
        'methodology_path': 'VARCHAR',
        'results_path': 'VARCHAR',
        'last_validation_status': 'VARCHAR'
    }
);
