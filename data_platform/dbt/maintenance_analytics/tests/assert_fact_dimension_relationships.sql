select fact.work_order_id
from {{ ref('fact_work_order') }} as fact
left join {{ ref('dim_site') }} as site
    on site.site_key = fact.site_key
left join {{ ref('dim_asset') }} as asset
    on asset.asset_key = fact.asset_key
left join {{ ref('dim_technician') }} as technician
    on technician.technician_key = fact.technician_key
where site.site_key is null
   or asset.asset_key is null
   or technician.technician_key is null
   or site.site_id is distinct from fact.site_id
   or asset.asset_id is distinct from fact.asset_id
   or (
        fact.assigned_technician_id is null
        and technician.technician_id <> {{ unknown_uuid() }}
      )
   or (
        fact.assigned_technician_id is not null
        and technician.technician_id is distinct from fact.assigned_technician_id
      )
