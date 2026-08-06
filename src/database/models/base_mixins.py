"""Shared model defaults for the domain-owned SQLAlchemy model package."""

from datetime import datetime, timezone
from uuid import UUID


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _asset_qr_token(context) -> UUID:
    from uuid import NAMESPACE_URL, uuid5

    asset_id = str(context.get_current_parameters().get("asset_id", ""))
    return uuid5(NAMESPACE_URL, f"ai-maintenance-copilot:asset:{asset_id}")

