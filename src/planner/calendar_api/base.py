from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date, datetime

from planner.business import week_bounds
from planner.models import CalendarEvent


class CalendarProviderError(RuntimeError):
    pass


class CalendarAccessError(CalendarProviderError):
    pass


class CalendarProvider(ABC):
    @abstractmethod
    def get_events(self, start: datetime, end: datetime) -> list[CalendarEvent]:
        raise NotImplementedError

    def get_current_week_events(self, reference: date | datetime | None = None) -> tuple[datetime, list[CalendarEvent]]:
        start, end = week_bounds(reference)
        return start, self.get_events(start, end)
