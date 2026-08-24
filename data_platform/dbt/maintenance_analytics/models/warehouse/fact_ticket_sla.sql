{{
    config(
        materialized='incremental',
        unique_key='ticket_id',
        incremental_strategy='delete+insert',
        on_schema_change='fail',
        indexes=[
            {'columns': ['ticket_id'], 'unique': true},
            {'columns': ['site_id', 'opened_at']},
            {'columns': ['is_resolution_breached', 'is_escalated']}
        ],
        post_hook=[
            "create index if not exists ix_fact_ticket_sla_work_order "
            ~ "on {{ this }} (work_order_id) where work_order_id is not null",
            "create index if not exists ix_fact_ticket_sla_escalated_unresolved "
            ~ "on {{ this }} (opened_at, ticket_id) "
            ~ "where is_escalated and resolved_at is null"
        ]
    )
}}

with event_rollup as (
    select
        ticket_id,
        count(*)::bigint as event_count,
        count(*) filter (where event_domain = 'escalation')::bigint as escalation_count,
        count(*) filter (where event_type like '%breach%')::bigint as breach_event_count,
        max(occurred_at) as latest_event_at,
        max(ingested_at) as latest_event_ingested_at
    from {{ ref('stg_ticket_events') }}
    group by ticket_id
),

affected_tickets as (
    select ticket_id from {{ ref('stg_tickets') }}
    {% if is_incremental() %}
    where ingested_at > coalesce(
        (select max(source_ingested_at) from {{ this }}),
        '1970-01-01'::timestamptz
    )
    union
    select ticket_id from event_rollup
    where latest_event_ingested_at > coalesce(
        (select max(source_ingested_at) from {{ this }}),
        '1970-01-01'::timestamptz
    )
    {% endif %}
),

tickets as (
    select t.*
    from {{ ref('stg_tickets') }} t
    join affected_tickets a using (ticket_id)
),

enriched as (
    select
        t.*,
        case t.priority
            when 'critical' then 15
            when 'high' then 60
            when 'medium' then 120
            else 240
        end as first_response_target_minutes,
        case t.priority
            when 'critical' then 120
            when 'high' then 480
            when 'medium' then 1440
            else 2880
        end as resolution_target_minutes,
        coalesce(e.event_count, 0) as event_count,
        coalesce(e.escalation_count, 0) as escalation_count,
        coalesce(e.breach_event_count, 0) as breach_event_count,
        e.latest_event_at,
        greatest(t.ingested_at, coalesce(e.latest_event_ingested_at, t.ingested_at))
            as source_ingested_at
    from tickets t
    left join event_rollup e using (ticket_id)
)

select
    ticket_id,
    asset_id,
    site_id,
    work_order_id,
    severity,
    priority,
    status,
    category,
    assigned_user_id,
    technician_id,
    opened_at,
    first_response_at,
    resolved_at,
    closed_at,
    resolution_summary,
    technician_note,
    reopen_count,
    first_response_target_minutes,
    resolution_target_minutes,
    opened_at + make_interval(mins => first_response_target_minutes)
        as first_response_due_at,
    opened_at + make_interval(mins => resolution_target_minutes)
        as resolution_due_at,
    first_response_at is not null
        and first_response_at <= opened_at + make_interval(mins => first_response_target_minutes)
        as is_first_response_met,
    coalesce(resolved_at, current_timestamp)
        > opened_at + make_interval(mins => resolution_target_minutes)
        as is_resolution_breached,
    escalation_count > 0 as is_escalated,
    event_count,
    escalation_count,
    breach_event_count,
    latest_event_at,
    source_available_at,
    source_extracted_at,
    source_ingested_at,
    ingestion_batch_id,
    current_timestamp as dbt_loaded_at
from enriched
