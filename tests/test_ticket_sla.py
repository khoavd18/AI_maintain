"""Unit tests for the canonical ticket priority matrix and SLA calendar."""

from datetime import UTC, date, datetime, time

import pytest

from src.ticket_management.domain import (
    PRIORITY_MATRIX,
    Impact,
    SlaClockStatus,
    TicketPriority,
    Urgency,
    calculate_priority,
)
from src.ticket_management.sla import (
    BusinessCalendarDefinition,
    CalendarConfigurationError,
    WorkingPeriod,
    derive_clock_status,
    remaining_minutes,
)


@pytest.mark.parametrize(
    ("impact", "urgency", "expected"),
    [
        (impact, urgency, priority)
        for impact, row in PRIORITY_MATRIX.items()
        for urgency, priority in row.items()
    ],
)
def test_priority_matrix_is_deterministic(
    impact: Impact, urgency: Urgency, expected: TicketPriority
) -> None:
    assert calculate_priority(impact, urgency) is expected
    assert calculate_priority(impact.value, urgency.value) is expected


def test_business_calendar_moves_outside_hours_over_weekend_and_holiday() -> None:
    calendar = _weekday_calendar(holidays={date(2026, 7, 20)})
    friday_after_hours = datetime(2026, 7, 17, 12, 0, tzinfo=UTC)  # 19:00 local

    due = calendar.add_working_minutes(friday_after_hours, 120)

    assert due == datetime(2026, 7, 21, 3, 0, tzinfo=UTC)  # Tuesday 10:00 local
    assert calendar.working_minutes_between(friday_after_hours, due) == 120


def test_business_calendar_handles_timezone_transition() -> None:
    calendar = BusinessCalendarDefinition(
        timezone="America/New_York",
        periods=(WorkingPeriod(6, time(1, 0), time(4, 0)),),
        holidays=frozenset(),
    )
    before_spring_forward = datetime(2026, 3, 8, 6, 0, tzinfo=UTC)

    assert calendar.add_working_minutes(before_spring_forward, 120) == datetime(
        2026, 3, 8, 8, 0, tzinfo=UTC
    )


def test_calendar_rejects_cross_midnight_and_overlapping_periods() -> None:
    cross_midnight = BusinessCalendarDefinition(
        timezone="Asia/Ho_Chi_Minh",
        periods=(WorkingPeriod(0, time(22), time(6)),),
        holidays=frozenset(),
    )
    overlapping = BusinessCalendarDefinition(
        timezone="Asia/Ho_Chi_Minh",
        periods=(
            WorkingPeriod(0, time(8), time(12)),
            WorkingPeriod(0, time(11), time(13)),
        ),
        holidays=frozenset(),
    )

    with pytest.raises(CalendarConfigurationError, match="nửa đêm"):
        cross_midnight.validate()
    with pytest.raises(CalendarConfigurationError, match="chồng lấn"):
        overlapping.validate()


def test_clock_status_uses_business_minutes_and_source_timestamps() -> None:
    calendar = _weekday_calendar()
    started = datetime(2026, 7, 20, 1, 0, tzinfo=UTC)
    due = calendar.add_working_minutes(started, 120)

    assert (
        derive_clock_status(
            started_at=started,
            due_at=due,
            completed_at=None,
            paused_at=None,
            target_minutes=120,
            as_of=datetime(2026, 7, 20, 2, 40, tzinfo=UTC),
            calendar=calendar,
            due_soon_percent=20,
        )
        is SlaClockStatus.DUE_SOON
    )
    assert (
        derive_clock_status(
            started_at=started,
            due_at=due,
            completed_at=due,
            paused_at=None,
            target_minutes=120,
            as_of=due,
            calendar=calendar,
        )
        is SlaClockStatus.MET
    )
    assert remaining_minutes(due, datetime(2026, 7, 20, 2, 0, tzinfo=UTC), calendar=calendar) == 60


def _weekday_calendar(
    holidays: set[date] | None = None,
) -> BusinessCalendarDefinition:
    return BusinessCalendarDefinition(
        timezone="Asia/Ho_Chi_Minh",
        periods=tuple(WorkingPeriod(day, time(8), time(17)) for day in range(5)),
        holidays=frozenset(holidays or set()),
    )
