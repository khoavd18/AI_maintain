select work_order_id
from {{ ref('fact_work_order_cost') }}
where total_estimated_cost <> estimated_labor_cost + planned_part_cost
   or total_actual_cost <> actual_labor_cost + actual_part_cost + external_service_cost
   or cost_variance <> total_actual_cost - total_estimated_cost
   or least(
       estimated_labor_cost,
       actual_labor_cost,
       planned_part_cost,
       actual_part_cost,
       external_service_cost,
       total_estimated_cost,
       total_actual_cost
   ) < 0
