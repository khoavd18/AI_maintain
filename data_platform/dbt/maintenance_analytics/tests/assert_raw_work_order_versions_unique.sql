select work_order_id, source_updated_at
from {{ source('raw', 'work_orders') }}
group by work_order_id, source_updated_at
having count(*) > 1
