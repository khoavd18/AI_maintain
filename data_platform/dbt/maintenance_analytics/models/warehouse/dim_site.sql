with current_sites as (
    select
        {{ generate_surrogate_key('site', 's.site_id') }} as site_key,
        s.site_id,
        s.site_code,
        s.site_name,
        s.location_type,
        s.parent_site_id,
        s.is_active,
        s.source_created_at,
        s.source_updated_at,
        s.ingestion_batch_id,
        s.source_extracted_at,
        s.ingested_at as source_ingested_at,
        current_timestamp as dbt_loaded_at
    from {{ ref('stg_sites') }} as s
),

unknown_site as (
    select
        {{ unknown_surrogate_key() }}::text as site_key,
        {{ unknown_uuid() }} as site_id,
        'UNKNOWN'::text as site_code,
        'Unknown Site'::text as site_name,
        'UNKNOWN'::text as location_type,
        null::uuid as parent_site_id,
        false::boolean as is_active,
        null::timestamptz as source_created_at,
        null::timestamptz as source_updated_at,
        null::uuid as ingestion_batch_id,
        null::timestamptz as source_extracted_at,
        null::timestamptz as source_ingested_at,
        current_timestamp as dbt_loaded_at
)

select * from unknown_site
union all
select * from current_sites
