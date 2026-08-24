with work_orders as (
    select
        site_id,
        count(*)::bigint as work_order_count,
        count(*) filter (where status in ('completed', 'verified'))::bigint
            as completed_work_order_count,
        count(*) filter (where status = 'cancelled')::bigint as cancelled_work_order_count,
        avg(repair_hours) filter (where repair_hours is not null) as average_repair_hours
    from {{ ref('fact_work_order') }}
    group by site_id
),

status_history as (
    select
        site_id,
        count(*)::bigint as status_event_count,
        sum(duration_seconds)::bigint as observed_status_seconds,
        sum(duration_seconds) filter (where status = 'on_hold')::bigint as on_hold_seconds
    from {{ ref('fact_work_order_status_duration') }}
    group by site_id
)

select
    s.site_id,
    s.site_code,
    s.site_name,
    w.work_order_count,
    w.completed_work_order_count,
    w.cancelled_work_order_count,
    round(100.0 * w.completed_work_order_count / nullif(w.work_order_count, 0), 4)
        as completion_rate_percent,
    round(w.average_repair_hours, 4) as average_repair_hours,
    h.status_event_count,
    h.observed_status_seconds,
    coalesce(h.on_hold_seconds, 0) as on_hold_seconds,
    current_timestamp as dbt_loaded_at
from work_orders w
join {{ ref('dim_site') }} s using (site_id)
join status_history h using (site_id)
where s.site_id <> {{ unknown_uuid() }}
