select work_order_id
from {{ ref('fact_work_order') }}
where (
        estimated_cost is not null
        and actual_cost is not null
        and cost_variance is distinct from actual_cost - estimated_cost
      )
   or (
        (estimated_cost is null or actual_cost is null)
        and (cost_variance is not null or is_over_budget is not null)
      )
