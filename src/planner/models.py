from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(slots=True, frozen=True)
class CalendarEvent:
    identifier: str
    title: str
    start: datetime
    end: datetime
    is_all_day: bool = False
    is_recurring: bool = False
    calendar_name: str | None = None
    location: str | None = None
    notes: str | None = None
    availability: str = "busy"


@dataclass(slots=True, frozen=True)
class TimedEventLayout:
    event: CalendarEvent
    day_index: int
    start_minutes: int
    end_minutes: int
    column: int
    column_count: int


@dataclass(slots=True, frozen=True)
class AllDayEventLayout:
    event: CalendarEvent
    day_index: int
    row: int


@dataclass(slots=True, frozen=True)
class DayStatus:
    day_index: int
    is_workday: bool
    holiday_name: str | None = None


@dataclass(slots=True, frozen=True)
class WeekLayout:
    week_start: datetime
    timed_events: tuple[TimedEventLayout, ...]
    all_day_events: tuple[AllDayEventLayout, ...]
    day_statuses: tuple[DayStatus, ...] = ()
