{{
    config(
        indexes=[
            {'columns': ['net_consumed_quantity', 'part_id']},
            {'columns': ['site_id', 'part_id']}
        ]
    )
}}

select
    m.part_id,
    p.part_number,
    p.part_name,
    m.site_id,
    count(*) filter (where m.movement_type = 'issue')::bigint as issue_movement_count,
    coalesce(sum(m.quantity) filter (where m.movement_type = 'issue'), 0)
        as issued_quantity,
    coalesce(sum(m.quantity) filter (where m.movement_type = 'return'), 0)
        as returned_quantity,
    coalesce(sum(m.quantity) filter (where m.movement_type = 'issue'), 0)
        - coalesce(sum(m.quantity) filter (where m.movement_type = 'return'), 0)
        as net_consumed_quantity,
    max(m.occurred_at) as latest_movement_at,
    current_timestamp as dbt_loaded_at
from {{ ref('fact_inventory_movement') }} m
join {{ ref('dim_spare_part') }} p using (part_id)
where m.work_order_id is not null
group by m.part_id, p.part_number, p.part_name, m.site_id
