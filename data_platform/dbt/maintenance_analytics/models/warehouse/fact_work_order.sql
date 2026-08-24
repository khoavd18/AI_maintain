{{
    config(
        materialized='incremental',
        unique_key='work_order_id',
        incremental_strategy='delete+insert',
        on_schema_change='fail',
        indexes=[
            {'columns': ['work_order_id'], 'unique': true},
            {'columns': ['source_updated_at', 'work_order_id']}
        ],
        post_hook=[
            "create index if not exists ix_fact_work_order_site_created "
            ~ "on {{ this }} (site_id, created_at, work_order_id)"
        ]
    )
}}

with work_orders as (
    select w.*
    from {{ ref('stg_work_orders') }} as w

    {% if is_incremental() %}
    where
        not exists (select 1 from {{ this }})
        or (w.source_updated_at, w.work_order_id) > (
            select
                existing.source_updated_at,
                existing.work_order_id
            from {{ this }} as existing
            order by
                existing.source_updated_at desc,
                existing.work_order_id desc
            limit 1
        )
    {% endif %}
),

sites as (
    select site_key, site_id
    from {{ ref('dim_site') }}
),

assets as (
    select asset_key, asset_id
    from {{ ref('dim_asset') }}
),

technicians as (
    select technician_key, technician_id
    from {{ ref('dim_technician') }}
),

dates as (
    select date_key, date_day
    from {{ ref('dim_date') }}
),

enriched_work_orders as (
    select
        {{ generate_surrogate_key('work_order', 'w.work_order_id') }} as work_order_key,
        w.work_order_id,
        w.work_order_number,
        coalesce(s.site_key, {{ unknown_surrogate_key() }}) as site_key,
        coalesce(a.asset_key, {{ unknown_surrogate_key() }}) as asset_key,
        coalesce(t.technician_key, {{ unknown_surrogate_key() }}) as technician_key,
        coalesce(created_date.date_key, 0) as created_date_key,
        coalesce(scheduled_date.date_key, 0) as scheduled_start_date_key,
        coalesce(started_date.date_key, 0) as started_date_key,
        coalesce(completed_date.date_key, 0) as completed_date_key,
        coalesce(due_date.date_key, 0) as due_date_key,
        w.site_id,
        w.asset_id,
        w.assigned_technician_id,
        w.work_order_type,
        w.priority,
        w.status,
        w.title,
        w.description,
        w.created_at,
        w.scheduled_start_at,
        w.started_at,
        w.completed_at,
        w.due_date,
        w.estimated_duration_minutes,
        w.labor_minutes,
        w.resolution_note,
        w.estimated_cost,
        w.actual_cost,
        case
            when w.estimated_cost is not null and w.actual_cost is not null
                then w.actual_cost - w.estimated_cost
            else null
        end as cost_variance,
        case
            when w.estimated_cost is not null and w.actual_cost is not null
                then w.actual_cost > w.estimated_cost
            else null
        end as is_over_budget,
        case
            when w.started_at is not null
             and w.completed_at is not null
             and w.completed_at >= w.started_at
                then round(extract(epoch from (w.completed_at - w.started_at)) / 3600.0, 2)
            else null
        end as repair_hours,
        1::integer as work_order_count,
        case when w.status in ('completed', 'verified') then 1 else 0 end::integer
            as completed_work_order_count,
        case when w.priority = 'critical' then 1 else 0 end::integer
            as critical_work_order_count,
        case when w.assigned_technician_id is null then 1 else 0 end::integer
            as unassigned_work_order_count,
        w.source_updated_at,
        w.ingestion_batch_id,
        w.source_extracted_at,
        w.ingested_at as source_ingested_at,
        w.source_system,
        current_timestamp as dbt_loaded_at
    from work_orders as w
    left join sites as s
        on s.site_id = w.site_id
       and s.site_id <> {{ unknown_uuid() }}
    left join assets as a
        on a.asset_id = w.asset_id
       and a.asset_id <> {{ unknown_text_id() }}
    left join technicians as t
        on t.technician_id = w.assigned_technician_id
       and t.technician_id <> {{ unknown_uuid() }}
    left join dates as created_date
        on created_date.date_day = (
            w.created_at at time zone '{{ var("reporting_timezone") }}'
        )::date
       and created_date.date_key <> 0
    left join dates as scheduled_date
        on scheduled_date.date_day = (
            w.scheduled_start_at at time zone '{{ var("reporting_timezone") }}'
        )::date
       and scheduled_date.date_key <> 0
    left join dates as started_date
        on started_date.date_day = (
            w.started_at at time zone '{{ var("reporting_timezone") }}'
        )::date
       and started_date.date_key <> 0
    left join dates as completed_date
        on completed_date.date_day = (
            w.completed_at at time zone '{{ var("reporting_timezone") }}'
        )::date
       and completed_date.date_key <> 0
    left join dates as due_date
        on due_date.date_day = w.due_date
       and due_date.date_key <> 0
)

select *
from enriched_work_orders
