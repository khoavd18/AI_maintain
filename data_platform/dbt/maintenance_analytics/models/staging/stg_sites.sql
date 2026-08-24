with ranked_sites as (
    select
        ingestion_batch_id,
        site_id,
        site_code,
        site_name,
        location_type,
        parent_site_id,
        is_active,
        source_created_at,
        source_updated_at,
        source_extracted_at,
        ingested_at,
        row_number() over (
            partition by site_id
            order by
                source_updated_at desc,
                source_extracted_at desc,
                ingested_at desc,
                ingestion_batch_id desc
        ) as version_rank
    from {{ source('raw', 'sites') }}
)

select
    site_id,
    upper(btrim(site_code)) as site_code,
    btrim(site_name) as site_name,
    lower(btrim(location_type)) as location_type,
    parent_site_id,
    is_active,
    source_created_at,
    source_updated_at,
    ingestion_batch_id,
    source_extracted_at,
    ingested_at
from ranked_sites
where version_rank = 1
