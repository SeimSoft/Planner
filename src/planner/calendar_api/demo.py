from __future__ import annotations

from datetime import datetime, timedelta

from planner.models import CalendarEvent

from .base import CalendarProvider


class DemoCalendarProvider(CalendarProvider):
    """Dummy provider für Demo-Zwecke und Tests."""

    def get_events(self, start: datetime, end: datetime) -> list[CalendarEvent]:
        """Returns demo events within the requested range."""
        events: list[CalendarEvent] = []
        current = start.replace(hour=0, minute=0, second=0, microsecond=0)

        while current < end:
            day_name = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"][current.weekday()]

            # Different events for different days
            if current.weekday() < 5:  # Weekday
                events.extend([
                    CalendarEvent(
                        identifier=f"demo_{current.strftime('%Y%m%d')}_1",
                        title=f"Standup - {day_name}",
                        start=current.replace(hour=9, minute=0),
                        end=current.replace(hour=9, minute=30),
                        calendar_name="Arbeit",
                    ),
                    CalendarEvent(
                        identifier=f"demo_{current.strftime('%Y%m%d')}_2",
                        title=f"Arbeitszeit - {day_name}",
                        start=current.replace(hour=10, minute=0),
                        end=current.replace(hour=12, minute=0),
                        calendar_name="Arbeit",
                    ),
                    CalendarEvent(
                        identifier=f"demo_{current.strftime('%Y%m%d')}_3",
                        title="Mittagessen",
                        start=current.replace(hour=12, minute=0),
                        end=current.replace(hour=13, minute=0),
                        calendar_name="Persönlich",
                    ),
                ])

                if current.weekday() == 2:  # Wednesday
                    events.append(CalendarEvent(
                        identifier=f"demo_{current.strftime('%Y%m%d')}_4",
                        title="Team Meeting",
                        start=current.replace(hour=14, minute=0),
                        end=current.replace(hour=15, minute=30),
                        calendar_name="Arbeit",
                    ))
            else:  # Weekend
                events.append(CalendarEvent(
                    identifier=f"demo_{current.strftime('%Y%m%d')}_weekend",
                    title=f"Freizeit - {day_name}",
                    start=current.replace(hour=10, minute=0),
                    end=current.replace(hour=18, minute=0),
                    is_all_day=False,
                    calendar_name="Persönlich",
                ))

            # Add one all-day event every other week on Friday
            if current.weekday() == 4 and (current.day % 14 < 7):
                events.append(CalendarEvent(
                    identifier=f"demo_{current.strftime('%Y%m%d')}_allday",
                    title="Ganztägiges Event",
                    start=current.replace(hour=0, minute=0),
                    end=(current + timedelta(days=2)).replace(hour=0, minute=0),
                    is_all_day=True,
                    calendar_name="Persönlich",
                ))

            current += timedelta(days=1)

        return events
