with ranked as (
    select
        *,
        row_number() over (
            partition by work_order_id
            order by source_available_at desc, source_extracted_at desc,
                ingested_at desc, ingestion_batch_id desc
        ) as version_rank
    from {{ source('raw', 'work_order_costs') }}
)

select
    work_order_id,
    upper(btrim(work_order_number)) as work_order_number,
    site_id,
    asset_id,
    estimated_labor_cost,
    actual_labor_cost,
    planned_part_cost,
    actual_part_cost,
    external_service_cost,
    total_estimated_cost,
    total_actual_cost,
    cost_variance,
    upper(btrim(currency_code)) as currency_code,
    source_available_at,
    source_extracted_at,
    ingested_at,
    ingestion_batch_id
from ranked
where version_rank = 1
