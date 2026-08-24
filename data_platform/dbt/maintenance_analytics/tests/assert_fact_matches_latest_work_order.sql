select
    coalesce(staged.work_order_id, fact.work_order_id) as work_order_id
from {{ ref('stg_work_orders') }} as staged
full outer join {{ ref('fact_work_order') }} as fact
    on fact.work_order_id = staged.work_order_id
where staged.work_order_id is null
   or fact.work_order_id is null
   or staged.source_updated_at is distinct from fact.source_updated_at
   or staged.work_order_number is distinct from fact.work_order_number
   or staged.site_id is distinct from fact.site_id
   or staged.asset_id is distinct from fact.asset_id
   or staged.assigned_technician_id is distinct from fact.assigned_technician_id
   or staged.status is distinct from fact.status
   or staged.completed_at is distinct from fact.completed_at
