select
    event_id,
    ticket_id,
    lower(btrim(event_domain)) as event_domain,
    lower(btrim(event_type)) as event_type,
    lower(btrim(clock_type)) as clock_type,
    occurrence_number,
    occurred_at,
    details,
    created_by_user_id,
    source_available_at,
    source_extracted_at,
    ingested_at,
    ingestion_batch_id
from {{ source('raw', 'ticket_events') }}
