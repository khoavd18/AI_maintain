select 'daily'::text as mart_name, daily_site_work_orders_key as mart_key
from {{ ref('daily_site_work_orders') }}
where completion_rate_percent < 0
   or completion_rate_percent > 100
   or completion_rate_percent is distinct from (
        case
            when total_work_orders = 0 then 0::numeric
            else round(100.0 * completed_work_orders / total_work_orders, 2)
        end
   )

union all

select 'monthly'::text as mart_name, monthly_site_work_orders_key as mart_key
from {{ ref('monthly_site_work_orders') }}
where completion_rate_percent < 0
   or completion_rate_percent > 100
   or completion_rate_percent is distinct from (
        case
            when total_work_orders = 0 then 0::numeric
            else round(100.0 * completed_work_orders / total_work_orders, 2)
        end
   )
