"""Controlled preventive-maintenance recurrence tests."""

from datetime import date

import pytest

from src.maintenance_management.domain import IntervalUnit, recurrence_summary
from src.maintenance_management.recurrence import (
    RecurrenceSpec,
    RecurrenceValidationError,
    advance_occurrence,
    first_occurrence_on_or_after,
    occurrences_between,
)


def _spec(
    start: date,
    *,
    value: int = 1,
    unit: IntervalUnit = IntervalUnit.DAY,
    end: date | None = None,
) -> RecurrenceSpec:
    return RecurrenceSpec(
        interval_value=value,
        interval_unit=unit,
        start_date=start,
        end_date=end,
        local_timezone="Asia/Ho_Chi_Minh",
    )


@pytest.mark.parametrize(
    ("spec", "current", "expected"),
    [
        (_spec(date(2026, 1, 1), value=3), date(2026, 1, 1), date(2026, 1, 4)),
        (
            _spec(date(2026, 1, 1), value=2, unit=IntervalUnit.WEEK),
            date(2026, 1, 1),
            date(2026, 1, 15),
        ),
        (
            _spec(date(2026, 1, 31), unit=IntervalUnit.MONTH),
            date(2026, 1, 31),
            date(2026, 2, 28),
        ),
        (
            _spec(date(2024, 2, 29), unit=IntervalUnit.YEAR),
            date(2024, 2, 29),
            date(2025, 2, 28),
        ),
    ],
)
def test_advance_occurrence_for_supported_intervals(
    spec: RecurrenceSpec, current: date, expected: date
) -> None:
    assert advance_occurrence(current, spec) == expected


def test_month_end_and_leap_year_keep_original_anchor() -> None:
    monthly = _spec(date(2026, 1, 31), unit=IntervalUnit.MONTH)
    february = advance_occurrence(monthly.start_date, monthly)
    assert february == date(2026, 2, 28)
    assert advance_occurrence(february, monthly) == date(2026, 3, 31)

    yearly = _spec(date(2024, 2, 29), unit=IntervalUnit.YEAR)
    current = yearly.start_date
    for _ in range(4):
        current = advance_occurrence(current, yearly)
    assert current == date(2028, 2, 29)


def test_bounded_expansion_respects_end_date_and_inclusive_range() -> None:
    spec = _spec(date(2026, 1, 1), value=2, end=date(2026, 1, 7))
    assert occurrences_between(
        spec,
        start=date(2026, 1, 2),
        end=date(2026, 1, 31),
    ) == [date(2026, 1, 3), date(2026, 1, 5), date(2026, 1, 7)]


def test_resume_helper_skips_paused_backlog_without_rewriting_history() -> None:
    spec = _spec(date(2026, 1, 31), unit=IntervalUnit.MONTH)
    assert first_occurrence_on_or_after(spec, date(2026, 3, 1)) == date(2026, 3, 31)


def test_invalid_timezone_interval_and_unbounded_range_are_rejected() -> None:
    with pytest.raises(RecurrenceValidationError, match="Timezone"):
        RecurrenceSpec(
            interval_value=1,
            interval_unit=IntervalUnit.DAY,
            start_date=date(2026, 1, 1),
            end_date=None,
            local_timezone="Invalid/Nowhere",
        ).validate()
    with pytest.raises(RecurrenceValidationError, match="interval_value"):
        _spec(date(2026, 1, 1), value=0).validate()
    with pytest.raises(RecurrenceValidationError, match="vượt quá"):
        occurrences_between(
            _spec(date(2020, 1, 1)),
            start=date(2020, 1, 1),
            end=date(2025, 1, 1),
        )


def test_recurrence_summary_is_vietnamese_and_controlled() -> None:
    assert recurrence_summary(3, IntervalUnit.MONTH) == "Mỗi 3 tháng"
