select work_order_id
from {{ ref('fact_work_order') }}
where source_updated_at < created_at
   or started_at < created_at
   or completed_at < created_at
   or (completed_at is not null and started_at is null)
   or completed_at < started_at
   or estimated_duration_minutes <= 0
   or labor_minutes < 0
