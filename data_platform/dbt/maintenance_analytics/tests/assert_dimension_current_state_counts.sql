with dimension_counts as (
    select
        (select count(*) from {{ ref('stg_sites') }}) + 1 as expected_sites,
        (select count(*) from {{ ref('dim_site') }}) as actual_sites,
        (select count(*) from {{ ref('stg_assets') }}) + 1 as expected_assets,
        (select count(*) from {{ ref('dim_asset') }}) as actual_assets,
        (select count(*) from {{ ref('stg_technicians') }}) + 1 as expected_technicians,
        (select count(*) from {{ ref('dim_technician') }}) as actual_technicians
)

select *
from dimension_counts
where expected_sites <> actual_sites
   or expected_assets <> actual_assets
   or expected_technicians <> actual_technicians
