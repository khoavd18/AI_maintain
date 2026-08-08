from datetime import date

import pytest
from pydantic import ValidationError

from src.maintenance_management.plan_schemas import MaintenancePlanCreateRequest


def test_plan_dates_use_utf8_vietnamese_validation_message() -> None:
    with pytest.raises(ValidationError, match="end_date không được sớm hơn start_date"):
        MaintenancePlanCreateRequest(
            plan_code="PM-001",
            asset_id="ASSET-001",
            name="Kiểm tra định kỳ",
            interval_value=30,
            interval_unit="day",
            start_date=date(2026, 8, 2),
            end_date=date(2026, 8, 1),
            estimated_duration_minutes=60,
            default_priority="medium",
        )
