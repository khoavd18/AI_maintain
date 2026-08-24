with current_technicians as (
    select
        {{ generate_surrogate_key('technician', 't.technician_id') }} as technician_key,
        t.technician_id,
        t.employee_code,
        t.display_name,
        t.role,
        t.is_active,
        t.source_created_at,
        t.source_updated_at,
        t.ingestion_batch_id,
        t.source_extracted_at,
        t.ingested_at as source_ingested_at,
        current_timestamp as dbt_loaded_at
    from {{ ref('stg_technicians') }} as t
),

unknown_technician as (
    select
        {{ unknown_surrogate_key() }}::text as technician_key,
        {{ unknown_uuid() }} as technician_id,
        'UNKNOWN'::text as employee_code,
        'Unknown / Unassigned Technician'::text as display_name,
        'UNKNOWN'::text as role,
        false::boolean as is_active,
        null::timestamptz as source_created_at,
        null::timestamptz as source_updated_at,
        null::uuid as ingestion_batch_id,
        null::timestamptz as source_extracted_at,
        null::timestamptz as source_ingested_at,
        current_timestamp as dbt_loaded_at
)

select * from unknown_technician
union all
select * from current_technicians
