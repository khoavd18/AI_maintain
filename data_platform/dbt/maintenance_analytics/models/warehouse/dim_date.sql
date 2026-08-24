with work_order_bounds as (
    select
        min((created_at at time zone '{{ var("reporting_timezone") }}')::date)
            as minimum_created_date,
        min((scheduled_start_at at time zone '{{ var("reporting_timezone") }}')::date)
            as minimum_scheduled_date,
        min((started_at at time zone '{{ var("reporting_timezone") }}')::date)
            as minimum_started_date,
        min((completed_at at time zone '{{ var("reporting_timezone") }}')::date)
            as minimum_completed_date,
        min(due_date) as minimum_due_date,
        max((created_at at time zone '{{ var("reporting_timezone") }}')::date)
            as maximum_created_date,
        max((scheduled_start_at at time zone '{{ var("reporting_timezone") }}')::date)
            as maximum_scheduled_date,
        max((started_at at time zone '{{ var("reporting_timezone") }}')::date)
            as maximum_started_date,
        max((completed_at at time zone '{{ var("reporting_timezone") }}')::date)
            as maximum_completed_date,
        max(due_date) as maximum_due_date
    from {{ ref('stg_work_orders') }}
),

date_bounds as (
    select
        date_trunc(
            'year',
            least(
                minimum_created_date,
                minimum_scheduled_date,
                minimum_started_date,
                minimum_completed_date,
                minimum_due_date,
                (current_timestamp at time zone '{{ var("reporting_timezone") }}')::date
            )
        )::date as minimum_date,
        (
            date_trunc(
                'year',
                greatest(
                    maximum_created_date,
                    maximum_scheduled_date,
                    maximum_started_date,
                    maximum_completed_date,
                    maximum_due_date,
                    (
                        current_timestamp at time zone '{{ var("reporting_timezone") }}'
                        + interval '5 years'
                    )::date
                )
            ) + interval '1 year' - interval '1 day'
        )::date as maximum_date
    from work_order_bounds
),

date_spine as (
    select generated_date::date as date_day
    from date_bounds
    cross join lateral generate_series(
        minimum_date,
        maximum_date,
        interval '1 day'
    ) as generated_date
),

calendar_dates as (
    select
        to_char(date_day, 'YYYYMMDD')::integer as date_key,
        date_day,
        extract(year from date_day)::integer as year_number,
        extract(quarter from date_day)::integer as quarter_number,
        extract(month from date_day)::integer as month_number,
        btrim(to_char(date_day, 'Month')) as month_name,
        date_trunc('month', date_day)::date as month_start_date,
        extract(week from date_day)::integer as week_number,
        extract(day from date_day)::integer as day_of_month,
        extract(isodow from date_day)::integer as day_of_week,
        btrim(to_char(date_day, 'Day')) as day_name,
        extract(isodow from date_day) in (6, 7) as is_weekend,
        current_timestamp as dbt_loaded_at
    from date_spine
),

unknown_date as (
    select
        0::integer as date_key,
        date '0001-01-01' as date_day,
        1::integer as year_number,
        0::integer as quarter_number,
        0::integer as month_number,
        'Unknown'::text as month_name,
        date '0001-01-01' as month_start_date,
        0::integer as week_number,
        0::integer as day_of_month,
        0::integer as day_of_week,
        'Unknown'::text as day_name,
        false::boolean as is_weekend,
        current_timestamp as dbt_loaded_at
)

select * from unknown_date
union all
select * from calendar_dates
