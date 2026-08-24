with ranked_assets as (
    select
        ingestion_batch_id,
        asset_id,
        asset_name,
        site_id,
        manufacturer,
        model,
        asset_type,
        criticality,
        lifecycle_status,
        operational_status,
        installed_at,
        source_created_at,
        source_updated_at,
        source_extracted_at,
        ingested_at,
        row_number() over (
            partition by asset_id
            order by
                source_updated_at desc,
                source_extracted_at desc,
                ingested_at desc,
                ingestion_batch_id desc
        ) as version_rank
    from {{ source('raw', 'assets') }}
)

select
    asset_id,
    btrim(asset_name) as asset_name,
    site_id,
    nullif(btrim(manufacturer), '') as manufacturer,
    nullif(btrim(model), '') as model,
    lower(btrim(asset_type)) as asset_type,
    lower(btrim(criticality)) as criticality,
    lower(btrim(lifecycle_status)) as lifecycle_status,
    lower(btrim(operational_status)) as operational_status,
    installed_at,
    source_created_at,
    source_updated_at,
    ingestion_batch_id,
    source_extracted_at,
    ingested_at
from ranked_assets
where version_rank = 1
