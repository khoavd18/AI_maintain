with ranked_work_orders as (
    select
        ingestion_batch_id,
        work_order_id,
        work_order_number,
        site_id,
        asset_id,
        assigned_technician_id,
        work_order_type,
        priority,
        status,
        title,
        description,
        created_at,
        scheduled_start_at,
        started_at,
        completed_at,
        due_date,
        estimated_duration_minutes,
        labor_minutes,
        resolution_note,
        estimated_cost,
        actual_cost,
        source_updated_at,
        source_extracted_at,
        ingested_at,
        source_system,
        row_number() over (
            partition by work_order_id
            order by
                source_updated_at desc,
                source_extracted_at desc,
                ingested_at desc,
                ingestion_batch_id desc
        ) as version_rank
    from {{ source('raw', 'work_orders') }}
)

select
    work_order_id,
    upper(btrim(work_order_number)) as work_order_number,
    site_id,
    asset_id,
    assigned_technician_id,
    lower(btrim(work_order_type)) as work_order_type,
    lower(btrim(priority)) as priority,
    lower(btrim(status)) as status,
    btrim(title) as title,
    nullif(btrim(description), '') as description,
    created_at,
    scheduled_start_at,
    started_at,
    completed_at,
    due_date,
    estimated_duration_minutes,
    labor_minutes,
    nullif(btrim(resolution_note), '') as resolution_note,
    estimated_cost,
    actual_cost,
    source_updated_at,
    ingestion_batch_id,
    source_extracted_at,
    ingested_at,
    btrim(source_system) as source_system
from ranked_work_orders
where version_rank = 1
