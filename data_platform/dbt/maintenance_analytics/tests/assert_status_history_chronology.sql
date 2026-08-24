select events.event_id
from {{ ref('stg_work_order_status_history') }} events
join {{ ref('stg_work_orders') }} work_orders using (work_order_id)
where events.transitioned_at < work_orders.created_at
   or (
       events.next_transitioned_at is not null
       and events.next_transitioned_at < events.transitioned_at
   )
