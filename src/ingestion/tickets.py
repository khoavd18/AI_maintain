"""Ticket ingestion helpers."""

import pandas as pd

from src.config.value_mappings import PRIORITY_VI_TO_SCORE, STATUS_VI_TO_CODE


def normalize_ticket_frame(tickets: pd.DataFrame) -> pd.DataFrame:
    """Normalize imported maintenance tickets to the MVP column contract."""

    required_columns = {"asset_id", "issue_description", "priority", "status"}
    missing = required_columns - set(tickets.columns)
    if missing:
        raise ValueError(f"Missing ticket columns: {sorted(missing)}")

    normalized = tickets.copy()
    normalized["priority"] = normalized["priority"].str.strip()
    normalized["status"] = normalized["status"].str.strip()

    unknown_priorities = set(normalized["priority"]) - set(PRIORITY_VI_TO_SCORE)
    if unknown_priorities:
        raise ValueError(f"Unknown priority values: {sorted(unknown_priorities)}")

    unknown_statuses = set(normalized["status"]) - set(STATUS_VI_TO_CODE)
    if unknown_statuses:
        raise ValueError(f"Unknown status values: {sorted(unknown_statuses)}")

    return normalized
