with latest as (
    select distinct on (work_order_id)
        work_order_id,
        status
    from {{ ref('stg_work_order_status_history') }}
    order by work_order_id, sequence_number desc
)

select latest.work_order_id
from latest
join {{ ref('stg_work_orders') }} work_orders using (work_order_id)
where latest.status <> work_orders.status
