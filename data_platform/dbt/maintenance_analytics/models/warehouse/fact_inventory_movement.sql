{{
    config(
        materialized='incremental',
        unique_key='movement_id',
        incremental_strategy='delete+insert',
        on_schema_change='fail',
        indexes=[
            {'columns': ['movement_id'], 'unique': true},
            {'columns': ['part_id', 'occurred_at']},
            {'columns': ['site_id', 'movement_type', 'occurred_at']}
        ]
    )
}}

select
    m.movement_id,
    m.movement_number,
    m.operation_id,
    p.part_key,
    m.part_id,
    m.stock_location_id,
    w.site_id,
    m.quantity,
    case
        when m.movement_type in ('issue', 'transfer_out', 'adjustment_decrease', 'damaged_scrapped')
            then -m.quantity
        else m.quantity
    end as signed_quantity,
    m.movement_type,
    m.business_reference,
    m.actor_user_id,
    m.occurred_at,
    m.work_order_id,
    m.unit_cost_snapshot,
    m.resulting_on_hand_quantity,
    m.resulting_reserved_quantity,
    m.source_available_at,
    m.source_extracted_at,
    m.ingested_at as source_ingested_at,
    m.ingestion_batch_id,
    current_timestamp as dbt_loaded_at
from {{ ref('stg_inventory_movements') }} m
join {{ ref('dim_spare_part') }} p using (part_id)
left join {{ ref('fact_work_order') }} w using (work_order_id)
{% if is_incremental() %}
where m.ingested_at > coalesce(
    (select max(source_ingested_at) from {{ this }}),
    '1970-01-01'::timestamptz
)
{% endif %}
