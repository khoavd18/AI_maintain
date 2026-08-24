with counts as (
    select
        (select count(*) from analytics_source.work_order_status_history) as source_status,
        (select count(*) from {{ ref('stg_work_order_status_history') }}) as staging_status,
        (select count(*) from {{ ref('fact_work_order_status_duration') }}) as fact_status,
        (select count(*) from analytics_source.tickets) as source_tickets,
        (select count(*) from {{ ref('stg_tickets') }}) as staging_tickets,
        (select count(*) from {{ ref('fact_ticket_sla') }}) as fact_tickets,
        (select count(*) from analytics_source.ticket_events) as source_ticket_events,
        (select count(*) from {{ ref('stg_ticket_events') }}) as staging_ticket_events,
        (select count(*) from analytics_source.spare_parts) as source_parts,
        (select count(*) from {{ ref('stg_spare_parts') }}) as staging_parts,
        (select count(*) from {{ ref('dim_spare_part') }}) as dimension_parts,
        (select count(*) from analytics_source.inventory_movements) as source_movements,
        (select count(*) from {{ ref('stg_inventory_movements') }}) as staging_movements,
        (select count(*) from {{ ref('fact_inventory_movement') }}) as fact_movements,
        (select count(*) from analytics_source.work_order_costs) as source_costs,
        (select count(*) from {{ ref('stg_work_order_costs') }}) as staging_costs,
        (select count(*) from {{ ref('fact_work_order_cost') }}) as fact_costs
)

select *
from counts
where source_status <> staging_status
   or source_status <> fact_status
   or source_tickets <> staging_tickets
   or source_tickets <> fact_tickets
   or source_ticket_events <> staging_ticket_events
   or source_parts <> staging_parts
   or source_parts <> dimension_parts
   or source_movements <> staging_movements
   or source_movements <> fact_movements
   or source_costs <> staging_costs
   or source_costs <> fact_costs
