with assets as (
    select *
    from {{ ref('stg_assets') }}
),

sites as (
    select
        site_key,
        site_id,
        site_code,
        site_name
    from {{ ref('dim_site') }}
),

current_assets as (
    select
        {{ generate_surrogate_key('asset', 'a.asset_id') }} as asset_key,
        a.asset_id,
        a.asset_name,
        coalesce(s.site_key, {{ unknown_surrogate_key() }}) as site_key,
        a.site_id,
        coalesce(s.site_code, 'UNKNOWN') as site_code,
        coalesce(s.site_name, 'Unknown Site') as site_name,
        a.manufacturer,
        a.model,
        a.asset_type,
        a.criticality,
        a.lifecycle_status,
        a.operational_status,
        a.installed_at,
        a.source_created_at,
        a.source_updated_at,
        a.ingestion_batch_id,
        a.source_extracted_at,
        a.ingested_at as source_ingested_at,
        current_timestamp as dbt_loaded_at
    from assets as a
    left join sites as s
        on s.site_id = a.site_id
       and s.site_id <> {{ unknown_uuid() }}
),

unknown_asset as (
    select
        {{ unknown_surrogate_key() }}::text as asset_key,
        {{ unknown_text_id() }} as asset_id,
        'Unknown Asset'::text as asset_name,
        {{ unknown_surrogate_key() }}::text as site_key,
        {{ unknown_uuid() }} as site_id,
        'UNKNOWN'::text as site_code,
        'Unknown Site'::text as site_name,
        null::text as manufacturer,
        null::text as model,
        'UNKNOWN'::text as asset_type,
        'UNKNOWN'::text as criticality,
        'UNKNOWN'::text as lifecycle_status,
        'UNKNOWN'::text as operational_status,
        null::timestamptz as installed_at,
        null::timestamptz as source_created_at,
        null::timestamptz as source_updated_at,
        null::uuid as ingestion_batch_id,
        null::timestamptz as source_extracted_at,
        null::timestamptz as source_ingested_at,
        current_timestamp as dbt_loaded_at
)

select * from unknown_asset
union all
select * from current_assets
