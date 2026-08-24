with ranked as (
    select
        *,
        row_number() over (
            partition by part_id
            order by source_available_at desc, source_extracted_at desc,
                ingested_at desc, ingestion_batch_id desc
        ) as version_rank
    from {{ source('raw', 'spare_parts') }}
)

select
    part_id,
    upper(btrim(part_number)) as part_number,
    btrim(part_name) as part_name,
    category_id,
    upper(btrim(category_code)) as category_code,
    unit_of_measure_id,
    upper(btrim(unit_code)) as unit_code,
    lower(btrim(lifecycle_status)) as lifecycle_status,
    minimum_stock,
    reorder_point,
    maximum_stock,
    unit_cost,
    upper(btrim(currency_code)) as currency_code,
    source_available_at,
    source_extracted_at,
    ingested_at,
    ingestion_batch_id
from ranked
where version_rank = 1
