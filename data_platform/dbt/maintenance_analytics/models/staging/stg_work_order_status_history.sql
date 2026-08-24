with events as (
    select
        event_id,
        work_order_id,
        work_order_number,
        site_id,
        asset_id,
        sequence_number,
        lower(btrim(status)) as status,
        transitioned_at,
        is_late_arriving,
        source_available_at,
        source_extracted_at,
        ingested_at,
        ingestion_batch_id
    from {{ source('raw', 'work_order_status_history') }}
),

sequenced as (
    select
        *,
        lead(transitioned_at) over (
            partition by work_order_id order by sequence_number
        ) as next_transitioned_at,
        lead(status) over (
            partition by work_order_id order by sequence_number
        ) as next_status
    from events
)

select
    *,
    greatest(
        extract(epoch from (coalesce(next_transitioned_at, transitioned_at) - transitioned_at)),
        0
    )::bigint as duration_seconds
from sequenced
