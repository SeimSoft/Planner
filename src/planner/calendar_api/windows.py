from __future__ import annotations

from datetime import datetime

import pywintypes
import win32com.client

from planner.models import CalendarEvent

from .base import CalendarAccessError, CalendarProvider


class WindowsOutlookCalendarProvider(CalendarProvider):
    def __init__(self) -> None:
        try:
            application = win32com.client.Dispatch("Outlook.Application")
            self._namespace = application.GetNamespace("MAPI")
        except pywintypes.com_error as exc:
            raise CalendarAccessError("Outlook ist nicht verfuegbar oder nicht korrekt konfiguriert") from exc

    def get_events(self, start: datetime, end: datetime) -> list[CalendarEvent]:
        events: list[CalendarEvent] = []
        for folder in _iter_calendar_folders(self._namespace.Folders):
            items = folder.Items
            items.Sort("[Start]")
            items.IncludeRecurrences = True
            restricted = items.Restrict(_outlook_filter(start, end))

            for item in restricted:
                start_value = getattr(item, "Start", None)
                end_value = getattr(item, "End", None)
                if start_value is None or end_value is None:
                    continue
                events.append(
                    CalendarEvent(
                        identifier=str(getattr(item, "EntryID", "")),
                        title=str(getattr(item, "Subject", "Ohne Titel") or "Ohne Titel"),
                        start=_as_datetime(start_value),
                        end=_as_datetime(end_value),
                        is_all_day=bool(getattr(item, "AllDayEvent", False)),
                        is_recurring=bool(getattr(item, "IsRecurring", False)),
                        calendar_name=str(getattr(folder, "Name", "Outlook")),
                        location=_optional_str(getattr(item, "Location", None)),
                        notes=_optional_str(getattr(item, "Body", None)),
                        availability=_map_outlook_busy_status(getattr(item, "BusyStatus", None)),
                    )
                )

        return events


def _iter_calendar_folders(folders: object):
    for folder in folders:
        message_class = getattr(folder, "DefaultMessageClass", "")
        if message_class == "IPM.Appointment":
            yield folder
        child_folders = getattr(folder, "Folders", None)
        if child_folders:
            yield from _iter_calendar_folders(child_folders)


def _outlook_filter(start: datetime, end: datetime) -> str:
    return (
        "[Start] < '"
        f"{end.strftime('%m/%d/%Y %I:%M %p')}"
        "' AND [End] >= '"
        f"{start.strftime('%m/%d/%Y %I:%M %p')}"
        "'"
    )


def _as_datetime(value: datetime | pywintypes.TimeType) -> datetime:
    if isinstance(value, datetime):
        return value.replace(tzinfo=None)
    return datetime.fromtimestamp(float(value))


def _optional_str(value: object | None) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _map_outlook_busy_status(value: object | None) -> str:
    status = int(value) if value is not None else 2
    mapping = {
        0: "free",
        1: "tentative",
        2: "busy",
        3: "out_of_office",
        4: "working_elsewhere",
    }
    return mapping.get(status, "busy")
