with fact_daily as (
    select
        site_key,
        created_date_key,
        sum(work_order_count)::bigint as total_work_orders,
        sum(completed_work_order_count)::bigint as completed_work_orders,
        sum(critical_work_order_count)::bigint as critical_work_orders,
        sum(unassigned_work_order_count)::bigint as unassigned_work_orders,
        sum(estimated_cost) as total_estimated_cost,
        sum(actual_cost) as total_actual_cost,
        sum(cost_variance) as total_cost_variance,
        sum(repair_hours) as total_repair_hours,
        count(repair_hours)::bigint as repair_duration_work_orders
    from {{ ref('fact_work_order') }}
    where site_key <> {{ unknown_surrogate_key() }}
      and created_date_key <> 0
    group by site_key, created_date_key
)

select
    coalesce(fact.site_key, daily.site_key) as site_key,
    coalesce(fact.created_date_key, daily.created_date_key) as created_date_key
from fact_daily as fact
full outer join {{ ref('daily_site_work_orders') }} as daily
    on daily.site_key = fact.site_key
   and daily.created_date_key = fact.created_date_key
where coalesce(fact.total_work_orders, 0) <> daily.total_work_orders
   or daily.site_key is null
   or coalesce(fact.completed_work_orders, 0) <> daily.completed_work_orders
   or coalesce(fact.critical_work_orders, 0) <> daily.critical_work_orders
   or coalesce(fact.unassigned_work_orders, 0) <> daily.unassigned_work_orders
   or fact.total_estimated_cost is distinct from daily.total_estimated_cost
   or fact.total_actual_cost is distinct from daily.total_actual_cost
   or fact.total_cost_variance is distinct from daily.total_cost_variance
   or fact.total_repair_hours is distinct from daily.total_repair_hours
   or coalesce(fact.repair_duration_work_orders, 0)
      <> daily.repair_duration_work_orders
