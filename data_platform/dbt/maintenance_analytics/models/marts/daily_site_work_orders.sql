{{
    config(
        indexes=[
            {'columns': ['created_date_key', 'site_key'], 'unique': true},
            {'columns': ['site_key']}
        ]
    )
}}

with facts as (
    select *
    from {{ ref('fact_work_order') }}
),

sites as (
    select
        site_key,
        site_id,
        site_code,
        site_name,
        location_type,
        is_active
    from {{ ref('dim_site') }}
    where site_id <> {{ unknown_uuid() }}
),

dates as (
    select
        date_key,
        date_day,
        year_number,
        quarter_number,
        month_number,
        month_name,
        day_of_month,
        day_of_week,
        day_name,
        is_weekend
    from {{ ref('dim_date') }}
    where date_key <> 0
),

date_bounds as (
    select
        least(
            coalesce(
                min(d.date_day),
                (current_timestamp at time zone '{{ var("reporting_timezone") }}')::date
            ),
            (current_timestamp at time zone '{{ var("reporting_timezone") }}')::date
        ) as minimum_date,
        greatest(
            coalesce(
                max(d.date_day),
                (current_timestamp at time zone '{{ var("reporting_timezone") }}')::date
            ),
            (current_timestamp at time zone '{{ var("reporting_timezone") }}')::date
        ) as maximum_date
    from facts as f
    left join dates as d
        on d.date_key = f.created_date_key
),

calendar as (
    select d.*
    from dates as d
    cross join date_bounds as bounds
    where d.date_day between bounds.minimum_date and bounds.maximum_date
),

site_date_spine as (
    select
        s.site_key,
        s.site_id,
        s.site_code,
        s.site_name,
        s.location_type,
        s.is_active,
        d.date_key as created_date_key,
        d.date_day as created_date,
        d.year_number,
        d.quarter_number,
        d.month_number,
        d.month_name,
        d.day_of_month,
        d.day_of_week,
        d.day_name,
        d.is_weekend
    from sites as s
    cross join calendar as d
),

daily_facts as (
    select
        site_key,
        created_date_key,
        sum(work_order_count) as total_work_orders,
        sum(completed_work_order_count) as completed_work_orders,
        sum(critical_work_order_count) as critical_work_orders,
        sum(unassigned_work_order_count) as unassigned_work_orders,
        sum(estimated_cost) as total_estimated_cost,
        sum(actual_cost) as total_actual_cost,
        sum(cost_variance) as total_cost_variance,
        sum(repair_hours) as total_repair_hours,
        count(repair_hours) as repair_duration_work_orders
    from facts
    where site_key <> {{ unknown_surrogate_key() }}
      and created_date_key <> 0
    group by site_key, created_date_key
)

select
    {{
        generate_surrogate_key(
            'daily_site_work_orders',
            "concat(spine.site_key, '||', spine.created_date_key)"
        )
    }} as daily_site_work_orders_key,
    spine.site_key,
    spine.site_id,
    spine.site_code,
    spine.site_name,
    spine.location_type,
    spine.is_active as site_is_active,
    spine.created_date_key,
    spine.created_date,
    spine.year_number,
    spine.quarter_number,
    spine.month_number,
    spine.month_name,
    spine.day_of_month,
    spine.day_of_week,
    spine.day_name,
    spine.is_weekend,
    coalesce(daily.total_work_orders, 0)::bigint as total_work_orders,
    coalesce(daily.completed_work_orders, 0)::bigint as completed_work_orders,
    coalesce(daily.critical_work_orders, 0)::bigint as critical_work_orders,
    coalesce(daily.unassigned_work_orders, 0)::bigint as unassigned_work_orders,
    daily.total_estimated_cost,
    daily.total_actual_cost,
    daily.total_cost_variance,
    daily.total_repair_hours,
    coalesce(daily.repair_duration_work_orders, 0)::bigint
        as repair_duration_work_orders,
    case
        when coalesce(daily.repair_duration_work_orders, 0) = 0 then null
        else round(
            daily.total_repair_hours / daily.repair_duration_work_orders,
            2
        )
    end as average_repair_hours,
    case
        when coalesce(daily.total_work_orders, 0) = 0 then 0::numeric
        else round(
            100.0 * daily.completed_work_orders / daily.total_work_orders,
            2
        )
    end as completion_rate_percent,
    current_timestamp as dbt_loaded_at
from site_date_spine as spine
left join daily_facts as daily
    on daily.site_key = spine.site_key
   and daily.created_date_key = spine.created_date_key
