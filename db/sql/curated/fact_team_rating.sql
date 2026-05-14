-- curated.fact_team_rating
-- Grain: one row per (team_code, model_id_or_NULL, rating_type, as_of_date)
-- Sources unioned:
--   1. raw.team_ratings_all_models (wide M1/M2/M3 columns → unpivoted)
--   2. raw.team_attack_ratings (rating_type='attack')
--   3. raw.team_defensive_ratings (rating_type='defense')
-- team_name → team_code resolution via staging.team_name_resolution
-- model_id is NULL for the M*-prefixed internal rating layers (not formal models in results/)
-- as_of_date is CURRENT_DATE at build time (these are point-in-time snapshots)

CREATE OR REPLACE TABLE curated.fact_team_rating AS

WITH all_models_unpivoted AS (
    SELECT
        tnr.team_code,
        NULL AS model_id,
        CAST(r.M1_History AS DOUBLE) AS rating_value,
        'historical' AS rating_type,
        CURRENT_DATE AS as_of_date
    FROM raw.team_ratings_all_models r
    LEFT JOIN staging.team_name_resolution tnr ON tnr.nation_name = r.nation
    WHERE tnr.team_code IS NOT NULL

    UNION ALL

    SELECT
        tnr.team_code,
        NULL AS model_id,
        CAST(r.M2_Season AS DOUBLE) AS rating_value,
        'season' AS rating_type,
        CURRENT_DATE AS as_of_date
    FROM raw.team_ratings_all_models r
    LEFT JOIN staging.team_name_resolution tnr ON tnr.nation_name = r.nation
    WHERE tnr.team_code IS NOT NULL

    UNION ALL

    SELECT
        tnr.team_code,
        NULL AS model_id,
        CAST(r.M3_RecentForm AS DOUBLE) AS rating_value,
        'recent_form' AS rating_type,
        CURRENT_DATE AS as_of_date
    FROM raw.team_ratings_all_models r
    LEFT JOIN staging.team_name_resolution tnr ON tnr.nation_name = r.nation
    WHERE tnr.team_code IS NOT NULL
),

attack AS (
    SELECT
        tnr.team_code,
        NULL AS model_id,
        CAST(r.attack_rating AS DOUBLE) AS rating_value,
        'attack' AS rating_type,
        CURRENT_DATE AS as_of_date
    FROM raw.team_attack_ratings r
    LEFT JOIN staging.team_name_resolution tnr ON tnr.nation_name = r.nation
    WHERE tnr.team_code IS NOT NULL
),

defense AS (
    SELECT
        tnr.team_code,
        NULL AS model_id,
        CAST(r.defensive_rating AS DOUBLE) AS rating_value,
        'defense' AS rating_type,
        CURRENT_DATE AS as_of_date
    FROM raw.team_defensive_ratings r
    LEFT JOIN staging.team_name_resolution tnr ON tnr.nation_name = r.nation
    WHERE tnr.team_code IS NOT NULL
)

SELECT * FROM all_models_unpivoted
UNION ALL SELECT * FROM attack
UNION ALL SELECT * FROM defense
;
