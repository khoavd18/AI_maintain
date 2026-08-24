select
    date_trunc(
        'month',
        w.created_at at time zone '{{ var("reporting_timezone") }}'
    )::date as month_start_date,
    c.site_id,
    s.site_code,
    s.site_name,
    count(*)::bigint as work_order_count,
    sum(c.total_estimated_cost) as total_estimated_cost,
    sum(c.total_actual_cost) as total_actual_cost,
    sum(c.cost_variance) as total_cost_variance,
    count(*) filter (where c.cost_variance > 0)::bigint as over_budget_work_order_count,
    round(avg(c.cost_variance), 2) as average_cost_variance,
    min(c.currency_code) as currency_code,
    current_timestamp as dbt_loaded_at
from {{ ref('fact_work_order_cost') }} c
join {{ ref('fact_work_order') }} w using (work_order_id)
join {{ ref('dim_site') }} s on s.site_id = c.site_id
group by month_start_date, c.site_id, s.site_code, s.site_name
