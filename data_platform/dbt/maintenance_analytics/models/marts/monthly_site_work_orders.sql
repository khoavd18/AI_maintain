{{
    config(
        indexes=[
            {'columns': ['month_key', 'site_key'], 'unique': true},
            {'columns': ['site_key']}
        ]
    )
}}

with daily as (
    select *
    from {{ ref('daily_site_work_orders') }}
),

monthly_rollup as (
    select
        site_key,
        site_id,
        site_code,
        site_name,
        location_type,
        site_is_active,
        (year_number * 100 + month_number)::integer as month_key,
        to_char(date_trunc('month', created_date), 'YYYYMMDD')::integer
            as month_date_key,
        date_trunc('month', created_date)::date as month_start_date,
        year_number,
        quarter_number,
        month_number,
        month_name,
        sum(total_work_orders)::bigint as total_work_orders,
        sum(completed_work_orders)::bigint as completed_work_orders,
        sum(critical_work_orders)::bigint as critical_work_orders,
        sum(unassigned_work_orders)::bigint as unassigned_work_orders,
        sum(total_estimated_cost) as total_estimated_cost,
        sum(total_actual_cost) as total_actual_cost,
        sum(total_cost_variance) as total_cost_variance,
        sum(total_repair_hours) as total_repair_hours,
        sum(repair_duration_work_orders)::bigint as repair_duration_work_orders
    from daily
    group by
        site_key,
        site_id,
        site_code,
        site_name,
        location_type,
        site_is_active,
        year_number,
        quarter_number,
        month_number,
        month_name,
        date_trunc('month', created_date)
)

select
    {{
        generate_surrogate_key(
            'monthly_site_work_orders',
            "concat(site_key, '||', month_key)"
        )
    }} as monthly_site_work_orders_key,
    site_key,
    site_id,
    site_code,
    site_name,
    location_type,
    site_is_active,
    month_key,
    month_date_key,
    month_start_date,
    year_number,
    quarter_number,
    month_number,
    month_name,
    total_work_orders,
    completed_work_orders,
    critical_work_orders,
    unassigned_work_orders,
    total_estimated_cost,
    total_actual_cost,
    total_cost_variance,
    total_repair_hours,
    repair_duration_work_orders,
    case
        when repair_duration_work_orders = 0 then null
        else round(total_repair_hours / repair_duration_work_orders, 2)
    end as average_repair_hours,
    case
        when total_work_orders = 0 then 0::numeric
        else round(100.0 * completed_work_orders / total_work_orders, 2)
    end as completion_rate_percent,
    current_timestamp as dbt_loaded_at
from monthly_rollup
