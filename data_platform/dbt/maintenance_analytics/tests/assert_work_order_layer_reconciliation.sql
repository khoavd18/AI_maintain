with layer_counts as (
    select
        (select count(distinct work_order_id) from {{ source('raw', 'work_orders') }})
            as raw_work_orders,
        (select count(*) from {{ ref('stg_work_orders') }}) as staged_work_orders,
        (select count(*) from {{ ref('fact_work_order') }}) as fact_work_orders
)

select *
from layer_counts
where raw_work_orders <> staged_work_orders
   or staged_work_orders <> fact_work_orders
