with ranked as (
    select
        *,
        row_number() over (
            partition by ticket_id
            order by source_available_at desc, source_extracted_at desc,
                ingested_at desc, ingestion_batch_id desc
        ) as version_rank
    from {{ source('raw', 'tickets') }}
)

select
    ticket_id,
    asset_id,
    site_id,
    work_order_id,
    lower(btrim(severity)) as severity,
    lower(btrim(priority)) as priority,
    lower(btrim(status)) as status,
    lower(btrim(category)) as category,
    btrim(issue_description) as issue_description,
    assigned_user_id,
    technician_id,
    opened_at,
    first_response_at,
    resolved_at,
    closed_at,
    nullif(btrim(resolution_summary), '') as resolution_summary,
    nullif(btrim(technician_note), '') as technician_note,
    reopen_count,
    source_available_at,
    source_extracted_at,
    ingested_at,
    ingestion_batch_id
from ranked
where version_rank = 1
