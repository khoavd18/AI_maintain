{{
    config(
        materialized='incremental',
        unique_key='work_order_id',
        incremental_strategy='delete+insert',
        on_schema_change='fail',
        indexes=[
            {'columns': ['work_order_id'], 'unique': true},
            {'columns': ['site_id', 'source_available_at']},
            {'columns': ['cost_variance']}
        ]
    )
}}

select
    c.work_order_id,
    c.work_order_number,
    w.work_order_key,
    c.site_id,
    c.asset_id,
    c.estimated_labor_cost,
    c.actual_labor_cost,
    c.planned_part_cost,
    c.actual_part_cost,
    c.external_service_cost,
    c.total_estimated_cost,
    c.total_actual_cost,
    c.cost_variance,
    c.currency_code,
    c.source_available_at,
    c.source_extracted_at,
    c.ingested_at as source_ingested_at,
    c.ingestion_batch_id,
    current_timestamp as dbt_loaded_at
from {{ ref('stg_work_order_costs') }} c
join {{ ref('fact_work_order') }} w using (work_order_id)
{% if is_incremental() %}
where c.ingested_at > coalesce(
    (select max(source_ingested_at) from {{ this }}),
    '1970-01-01'::timestamptz
)
{% endif %}
