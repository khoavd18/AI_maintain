"""Deterministic business-calendar and SLA clock calculations."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from math import ceil
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from src.ticket_management.domain import SlaClockStatus

MAX_CALENDAR_SEARCH_DAYS = 3660


class CalendarConfigurationError(ValueError):
    """Raised when a business calendar is invalid or cannot satisfy a target."""


@dataclass(frozen=True)
class WorkingPeriod:
    weekday: int
    start_time: time
    end_time: time


@dataclass(frozen=True)
class BusinessCalendarDefinition:
    timezone: str
    periods: tuple[WorkingPeriod, ...]
    holidays: frozenset[date]

    @classmethod
    def from_snapshot(cls, snapshot: dict[str, Any]) -> "BusinessCalendarDefinition":
        periods = tuple(
            WorkingPeriod(
                weekday=int(item["weekday"]),
                start_time=time.fromisoformat(str(item["start_time"])),
                end_time=time.fromisoformat(str(item["end_time"])),
            )
            for item in snapshot.get("periods", [])
        )
        holidays = frozenset(
            date.fromisoformat(str(value)) for value in snapshot.get("holidays", [])
        )
        calendar = cls(
            timezone=str(snapshot["timezone"]),
            periods=periods,
            holidays=holidays,
        )
        calendar.validate()
        return calendar

    def to_snapshot(self) -> dict[str, object]:
        self.validate()
        return {
            "timezone": self.timezone,
            "periods": [
                {
                    "weekday": period.weekday,
                    "start_time": period.start_time.isoformat(timespec="minutes"),
                    "end_time": period.end_time.isoformat(timespec="minutes"),
                }
                for period in sorted(
                    self.periods,
                    key=lambda item: (item.weekday, item.start_time, item.end_time),
                )
            ],
            "holidays": sorted(value.isoformat() for value in self.holidays),
        }

    def validate(self) -> None:
        try:
            ZoneInfo(self.timezone)
        except ZoneInfoNotFoundError as exc:
            raise CalendarConfigurationError(
                f"Timezone IANA không hợp lệ: {self.timezone}"
            ) from exc
        if not self.periods:
            raise CalendarConfigurationError("Business calendar cần ít nhất một ca làm việc.")
        by_day: dict[int, list[WorkingPeriod]] = {}
        for period in self.periods:
            if period.weekday < 0 or period.weekday > 6:
                raise CalendarConfigurationError("weekday phải nằm trong khoảng 0..6.")
            if period.start_time >= period.end_time:
                raise CalendarConfigurationError(
                    "Ca làm việc qua nửa đêm chưa được hỗ trợ trong milestone này."
                )
            by_day.setdefault(period.weekday, []).append(period)
        for periods in by_day.values():
            ordered = sorted(periods, key=lambda item: item.start_time)
            for previous, current in zip(ordered, ordered[1:], strict=False):
                if current.start_time < previous.end_time:
                    raise CalendarConfigurationError("Các ca làm việc không được chồng lấn.")

    @property
    def zone(self) -> ZoneInfo:
        return ZoneInfo(self.timezone)

    def add_working_minutes(self, start: datetime, minutes: int) -> datetime:
        """Add business minutes and return an aware UTC timestamp."""

        if minutes <= 0:
            raise ValueError("SLA target phải lớn hơn 0 phút.")
        self.validate()
        cursor = _require_aware(start).astimezone(UTC)
        remaining_seconds = minutes * 60
        local_date = cursor.astimezone(self.zone).date()

        for day_offset in range(MAX_CALENDAR_SEARCH_DAYS):
            current_date = local_date + timedelta(days=day_offset)
            for period_start, period_end in self._utc_periods(current_date):
                segment_start = max(cursor, period_start)
                if segment_start >= period_end:
                    continue
                available = int((period_end - segment_start).total_seconds())
                if remaining_seconds <= available:
                    return segment_start + timedelta(seconds=remaining_seconds)
                remaining_seconds -= available
            cursor = datetime.combine(
                current_date + timedelta(days=1), time.min, tzinfo=self.zone
            ).astimezone(UTC)
        raise CalendarConfigurationError(
            "Không thể tính SLA trong phạm vi business calendar 10 năm."
        )

    def working_minutes_between(self, start: datetime, end: datetime) -> int:
        """Count complete business minutes in a half-open UTC interval."""

        self.validate()
        start_utc = _require_aware(start).astimezone(UTC)
        end_utc = _require_aware(end).astimezone(UTC)
        if end_utc <= start_utc:
            return 0
        first_date = start_utc.astimezone(self.zone).date()
        last_date = end_utc.astimezone(self.zone).date()
        if (last_date - first_date).days > MAX_CALENDAR_SEARCH_DAYS:
            raise CalendarConfigurationError("Khoảng SLA vượt quá giới hạn 10 năm.")
        total_seconds = 0
        current_date = first_date
        while current_date <= last_date:
            for period_start, period_end in self._utc_periods(current_date):
                overlap_start = max(start_utc, period_start)
                overlap_end = min(end_utc, period_end)
                if overlap_end > overlap_start:
                    total_seconds += int((overlap_end - overlap_start).total_seconds())
            current_date += timedelta(days=1)
        return total_seconds // 60

    def _utc_periods(self, local_date: date) -> list[tuple[datetime, datetime]]:
        if local_date in self.holidays:
            return []
        periods = sorted(
            (period for period in self.periods if period.weekday == local_date.weekday()),
            key=lambda item: item.start_time,
        )
        return [
            (
                datetime.combine(local_date, period.start_time, tzinfo=self.zone).astimezone(UTC),
                datetime.combine(local_date, period.end_time, tzinfo=self.zone).astimezone(UTC),
            )
            for period in periods
        ]


def derive_clock_status(
    *,
    started_at: datetime | None,
    due_at: datetime | None,
    completed_at: datetime | None,
    paused_at: datetime | None,
    target_minutes: int | None,
    as_of: datetime,
    calendar: BusinessCalendarDefinition | None = None,
    due_soon_percent: int = 20,
    stopped: bool = False,
) -> SlaClockStatus:
    """Derive a clock state from source timestamps; clients never submit it."""

    if started_at is None or due_at is None or target_minutes is None:
        return SlaClockStatus.NOT_STARTED
    due = _require_aware(due_at).astimezone(UTC)
    if completed_at is not None:
        return (
            SlaClockStatus.MET
            if _require_aware(completed_at).astimezone(UTC) <= due
            else SlaClockStatus.BREACHED
        )
    if stopped:
        return SlaClockStatus.STOPPED
    if paused_at is not None:
        return SlaClockStatus.PAUSED
    current = _require_aware(as_of).astimezone(UTC)
    if current > due:
        return SlaClockStatus.BREACHED
    threshold = max(15, ceil(target_minutes * due_soon_percent / 100))
    minutes_until_due = (
        calendar.working_minutes_between(current, due)
        if calendar is not None
        else max(0, int((due - current).total_seconds()) // 60)
    )
    if minutes_until_due <= threshold:
        return SlaClockStatus.DUE_SOON
    return SlaClockStatus.ACTIVE


def remaining_minutes(
    due_at: datetime | None,
    as_of: datetime,
    *,
    calendar: BusinessCalendarDefinition | None = None,
) -> int | None:
    if due_at is None:
        return None
    due = _require_aware(due_at).astimezone(UTC)
    current = _require_aware(as_of).astimezone(UTC)
    if calendar is None:
        return int((due - current).total_seconds()) // 60
    if current <= due:
        return calendar.working_minutes_between(current, due)
    return -calendar.working_minutes_between(due, current)


def _require_aware(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Timestamp SLA phải có timezone.")
    return value
