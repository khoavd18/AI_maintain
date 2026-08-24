with transitions as (
    select
        event_id,
        status,
        lag(status) over (
            partition by work_order_id order by sequence_number
        ) as prior_status
    from {{ ref('stg_work_order_status_history') }}
)

select event_id
from transitions
where status = prior_status
