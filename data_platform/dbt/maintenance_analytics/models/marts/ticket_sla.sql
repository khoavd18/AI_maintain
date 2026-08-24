select
    t.site_id,
    s.site_code,
    s.site_name,
    t.priority,
    count(*)::bigint as ticket_count,
    count(*) filter (where t.resolved_at is null)::bigint as unresolved_ticket_count,
    count(*) filter (where t.is_first_response_met)::bigint as first_response_met_count,
    count(*) filter (where t.is_resolution_breached)::bigint as resolution_breach_count,
    count(*) filter (where t.is_escalated)::bigint as escalated_ticket_count,
    round(
        100.0 * count(*) filter (where t.is_resolution_breached) / nullif(count(*), 0),
        4
    ) as resolution_breach_rate_percent,
    current_timestamp as dbt_loaded_at
from {{ ref('fact_ticket_sla') }} t
join {{ ref('dim_site') }} s using (site_id)
group by t.site_id, s.site_code, s.site_name, t.priority
