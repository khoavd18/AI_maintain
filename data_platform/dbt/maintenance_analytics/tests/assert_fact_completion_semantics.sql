select work_order_id
from {{ ref('fact_work_order') }}
where (
        status in ('completed', 'verified')
        and (completed_at is null or completed_work_order_count <> 1)
      )
   or (
        status not in ('completed', 'verified')
        and (completed_at is not null or completed_work_order_count <> 0)
      )
