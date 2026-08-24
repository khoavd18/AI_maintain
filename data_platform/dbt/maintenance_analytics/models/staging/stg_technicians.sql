with ranked_technicians as (
    select
        ingestion_batch_id,
        technician_id,
        employee_code,
        display_name,
        role,
        is_active,
        source_created_at,
        source_updated_at,
        source_extracted_at,
        ingested_at,
        row_number() over (
            partition by technician_id
            order by
                source_updated_at desc,
                source_extracted_at desc,
                ingested_at desc,
                ingestion_batch_id desc
        ) as version_rank
    from {{ source('raw', 'technicians') }}
)

select
    technician_id,
    upper(btrim(employee_code)) as employee_code,
    btrim(display_name) as display_name,
    lower(btrim(role)) as role,
    is_active,
    source_created_at,
    source_updated_at,
    ingestion_batch_id,
    source_extracted_at,
    ingested_at
from ranked_technicians
where version_rank = 1
