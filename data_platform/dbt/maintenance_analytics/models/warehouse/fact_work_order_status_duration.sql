{{
    config(
        materialized='incremental',
        unique_key='event_id',
        incremental_strategy='delete+insert',
        on_schema_change='fail',
        indexes=[
            {'columns': ['event_id'], 'unique': true},
            {'columns': ['work_order_id', 'sequence_number']},
            {'columns': ['site_id', 'transitioned_at']}
        ]
    )
}}

with affected_work_orders as (
    select distinct work_order_id
    from {{ ref('stg_work_order_status_history') }}
    {% if is_incremental() %}
    where ingested_at > coalesce(
        (select max(source_ingested_at) from {{ this }}),
        '1970-01-01'::timestamptz
    )
    {% endif %}
),

events as (
    select e.*
    from {{ ref('stg_work_order_status_history') }} e
    join affected_work_orders a using (work_order_id)
)

select
    event_id,
    work_order_id,
    work_order_number,
    site_id,
    asset_id,
    sequence_number,
    status,
    next_status,
    transitioned_at,
    next_transitioned_at,
    duration_seconds,
    round(duration_seconds / 3600.0, 4) as duration_hours,
    is_late_arriving,
    source_available_at,
    source_extracted_at,
    ingested_at as source_ingested_at,
    ingestion_batch_id,
    current_timestamp as dbt_loaded_at
from events
