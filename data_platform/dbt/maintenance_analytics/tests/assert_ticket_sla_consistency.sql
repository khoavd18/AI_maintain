select ticket_id
from {{ ref('fact_ticket_sla') }}
where first_response_due_at < opened_at
   or resolution_due_at < opened_at
   or (resolved_at is not null and resolved_at < opened_at)
   or (closed_at is not null and closed_at < resolved_at)
   or (status in ('resolved', 'closed') and resolution_summary is null)
