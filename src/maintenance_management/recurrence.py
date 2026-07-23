"""Deterministic bounded recurrence calculations over local business dates."""

from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from src.maintenance_management.domain import IntervalUnit

MAX_EXPANSION_DAYS = 366 * 3
MAX_OCCURRENCES = 256


class RecurrenceValidationError(ValueError):
    """Raised for invalid or unbounded recurrence requests."""


@dataclass(frozen=True)
class RecurrenceSpec:
    """Controlled interval recurrence anchored to its original start date."""

    interval_value: int
    interval_unit: IntervalUnit
    start_date: date
    end_date: date | None
    local_timezone: str

    def validate(self) -> None:
        if self.interval_value < 1 or self.interval_value > 366:
            raise RecurrenceValidationError("interval_value phải nằm trong khoảng 1–366.")
        if self.end_date is not None and self.end_date < self.start_date:
            raise RecurrenceValidationError("end_date không được sớm hơn start_date.")
        try:
            ZoneInfo(self.local_timezone)
        except ZoneInfoNotFoundError as exc:
            raise RecurrenceValidationError(
                f"Timezone IANA không được hỗ trợ: {self.local_timezone}"
            ) from exc


def advance_occurrence(current: date, spec: RecurrenceSpec) -> date:
    """Advance once while preserving the original month/day anchor."""

    spec.validate()
    if spec.interval_unit is IntervalUnit.DAY:
        return current + timedelta(days=spec.interval_value)
    if spec.interval_unit is IntervalUnit.WEEK:
        return current + timedelta(weeks=spec.interval_value)
    if spec.interval_unit is IntervalUnit.MONTH:
        month_index = current.year * 12 + current.month - 1 + spec.interval_value
        year, zero_based_month = divmod(month_index, 12)
        month = zero_based_month + 1
        day = min(spec.start_date.day, calendar.monthrange(year, month)[1])
        return date(year, month, day)
    year = current.year + spec.interval_value
    month = spec.start_date.month
    day = min(spec.start_date.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def occurrences_between(
    spec: RecurrenceSpec,
    *,
    start: date,
    end: date,
    first_due: date | None = None,
    max_occurrences: int = MAX_OCCURRENCES,
) -> list[date]:
    """Expand an inclusive, bounded date range without timezone conversion."""

    spec.validate()
    if end < start:
        raise RecurrenceValidationError("Khoảng ngày occurrence không hợp lệ.")
    if (end - start).days > MAX_EXPANSION_DAYS:
        raise RecurrenceValidationError(
            f"Khoảng occurrence không được vượt quá {MAX_EXPANSION_DAYS} ngày."
        )
    if max_occurrences < 1 or max_occurrences > MAX_OCCURRENCES:
        raise RecurrenceValidationError(
            f"max_occurrences phải nằm trong khoảng 1–{MAX_OCCURRENCES}."
        )

    current = first_due or spec.start_date
    if current < spec.start_date:
        current = spec.start_date
    guard = 0
    while current < start:
        current = advance_occurrence(current, spec)
        guard += 1
        if guard > MAX_OCCURRENCES * 20:
            raise RecurrenceValidationError("Không thể xác định occurrence trong giới hạn an toàn.")

    result: list[date] = []
    while current <= end and (spec.end_date is None or current <= spec.end_date):
        result.append(current)
        if len(result) >= max_occurrences:
            next_date = advance_occurrence(current, spec)
            if next_date <= end and (spec.end_date is None or next_date <= spec.end_date):
                raise RecurrenceValidationError(
                    "Số occurrence vượt giới hạn; hãy thu hẹp khoảng ngày."
                )
            break
        current = advance_occurrence(current, spec)
    return result


def first_occurrence_on_or_after(spec: RecurrenceSpec, target: date) -> date | None:
    """Return the first due date on/after target, respecting the plan end date."""

    spec.validate()
    current = spec.start_date
    guard = 0
    while current < target:
        current = advance_occurrence(current, spec)
        guard += 1
        if guard > MAX_OCCURRENCES * 20:
            raise RecurrenceValidationError("Không thể xác định next_due_date an toàn.")
    if spec.end_date is not None and current > spec.end_date:
        return None
    return current

