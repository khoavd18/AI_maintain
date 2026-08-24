with latest_raw as (
    select
        work_order_id,
        source_updated_at,
        ingestion_batch_id,
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
    coalesce(raw.work_order_id, staged.work_order_id) as work_order_id
from latest_raw as raw
full outer join {{ ref('stg_work_orders') }} as staged
    on staged.work_order_id = raw.work_order_id
   and raw.version_rank = 1
where (raw.version_rank = 1 or raw.version_rank is null)
  and (
      raw.work_order_id is null
      or staged.work_order_id is null
      or raw.source_updated_at is distinct from staged.source_updated_at
      or raw.ingestion_batch_id is distinct from staged.ingestion_batch_id
  )
