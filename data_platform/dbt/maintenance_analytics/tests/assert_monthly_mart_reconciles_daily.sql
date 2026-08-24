with daily_monthly as (
    select
        site_key,
        (year_number * 100 + month_number)::integer as month_key,
        sum(total_work_orders)::bigint as total_work_orders,
        sum(completed_work_orders)::bigint as completed_work_orders,
        sum(critical_work_orders)::bigint as critical_work_orders,
        sum(unassigned_work_orders)::bigint as unassigned_work_orders,
        sum(total_estimated_cost) as total_estimated_cost,
        sum(total_actual_cost) as total_actual_cost,
        sum(total_cost_variance) as total_cost_variance,
        sum(total_repair_hours) as total_repair_hours,
        sum(repair_duration_work_orders)::bigint as repair_duration_work_orders
    from {{ ref('daily_site_work_orders') }}
    group by site_key, year_number, month_number
)

select
    coalesce(daily.site_key, monthly.site_key) as site_key,
    coalesce(daily.month_key, monthly.month_key) as month_key
from daily_monthly as daily
full outer join {{ ref('monthly_site_work_orders') }} as monthly
    on monthly.site_key = daily.site_key
   and monthly.month_key = daily.month_key
where daily.site_key is null
   or monthly.site_key is null
   or daily.total_work_orders is distinct from monthly.total_work_orders
   or daily.completed_work_orders is distinct from monthly.completed_work_orders
   or daily.critical_work_orders is distinct from monthly.critical_work_orders
   or daily.unassigned_work_orders is distinct from monthly.unassigned_work_orders
   or daily.total_estimated_cost is distinct from monthly.total_estimated_cost
   or daily.total_actual_cost is distinct from monthly.total_actual_cost
   or daily.total_cost_variance is distinct from monthly.total_cost_variance
   or daily.total_repair_hours is distinct from monthly.total_repair_hours
   or daily.repair_duration_work_orders is distinct from monthly.repair_duration_work_orders
