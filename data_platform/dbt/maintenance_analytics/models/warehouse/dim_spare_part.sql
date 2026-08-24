{{
    config(
        materialized='incremental',
        unique_key='part_id',
        incremental_strategy='delete+insert',
        on_schema_change='fail',
        indexes=[
            {'columns': ['part_id'], 'unique': true},
            {'columns': ['part_number'], 'unique': true},
            {'columns': ['category_code']}
        ]
    )
}}

select
    {{ generate_surrogate_key('spare_part', 'part_id') }} as part_key,
    part_id,
    part_number,
    part_name,
    category_id,
    category_code,
    unit_of_measure_id,
    unit_code,
    lifecycle_status,
    minimum_stock,
    reorder_point,
    maximum_stock,
    unit_cost,
    currency_code,
    source_available_at,
    ingested_at as source_ingested_at,
    ingestion_batch_id,
    current_timestamp as dbt_loaded_at
from {{ ref('stg_spare_parts') }}
{% if is_incremental() %}
where source_available_at > coalesce(
    (select max(source_available_at) from {{ this }}),
    '1970-01-01'::timestamptz
)
{% endif %}
