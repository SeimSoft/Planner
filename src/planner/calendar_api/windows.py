from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

import pywintypes
import win32com.client

from planner.models import CalendarEvent

from .base import CalendarAccessError, CalendarProvider


@dataclass(slots=True)
class _EventCacheWindow:
    start: datetime
    end: datetime
    events: list[CalendarEvent]


class WindowsOutlookCalendarProvider(CalendarProvider):
    def __init__(self) -> None:
        try:
            application = win32com.client.Dispatch("Outlook.Application")
            self._namespace = application.GetNamespace("MAPI")
        except pywintypes.com_error as exc:
            raise CalendarAccessError("Outlook ist nicht verfuegbar oder nicht korrekt konfiguriert") from exc
        self._event_cache_windows: list[_EventCacheWindow] = []
        self._max_cache_windows = 6

    def get_events(self, start: datetime, end: datetime) -> list[CalendarEvent]:
        query_end = _cap_windows_query_end(start, end)
        if query_end <= start:
            return []

        cached_events = self._read_from_cache(start, query_end)
        if cached_events is not None:
            return cached_events

        fetch_end = _cap_windows_query_end(start, start + timedelta(days=31))
        if fetch_end <= start:
            return []

        window_events = self._fetch_events(start, fetch_end)
        self._write_cache(start, fetch_end, window_events)
        return _clip_events(window_events, start, query_end)

    def _fetch_events(self, start: datetime, end: datetime) -> list[CalendarEvent]:
        if end <= start:
            return []

        events: list[CalendarEvent] = []
        for folder in _iter_calendar_folders(self._namespace):
            try:
                items = folder.Items
                items.Sort("[Start]")
                items.IncludeRecurrences = True
                restricted = items.Restrict(_outlook_filter(start, end))
            except pywintypes.com_error:
                # Skip folders that intermittently fail to materialize in COM.
                continue

            # Recurrence expansion can return very large collections. Keep a hard
            # safety cap so startup stays responsive even on huge mailboxes.
            for item in _iter_outlook_items(restricted, max_count=5000):
                if _is_canceled_event(item):
                    continue

                start_value = getattr(item, "Start", None)
                end_value = getattr(item, "End", None)
                if start_value is None or end_value is None:
                    continue

                availability = _resolve_event_availability(item)
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
                        availability=availability,
                    )
                )

        return events

    def _read_from_cache(self, start: datetime, end: datetime) -> list[CalendarEvent] | None:
        for window in self._event_cache_windows:
            if start >= window.start and end <= window.end:
                return _clip_events(window.events, start, end)
        return None

    def _write_cache(self, start: datetime, end: datetime, events: list[CalendarEvent]) -> None:
        self._event_cache_windows.insert(0, _EventCacheWindow(start=start, end=end, events=events))
        if len(self._event_cache_windows) > self._max_cache_windows:
            self._event_cache_windows = self._event_cache_windows[: self._max_cache_windows]


def _iter_outlook_items(items: object, max_count: int | None = None):
    """Iterate Outlook collections without Python COM enumerator indexing.

    `for item in collection` can fail with intermittent OLE errors on Windows.
    Using GetFirst/GetNext is more robust with Outlook COM collections.
    """
    if items is None:
        return

    get_first = getattr(items, "GetFirst", None)
    get_next = getattr(items, "GetNext", None)

    # Some Outlook collections (e.g., Items) expose GetFirst/GetNext.
    if callable(get_first) and callable(get_next):
        try:
            item = get_first()
        except pywintypes.com_error:
            return

        yielded = 0
        while item is not None:
            yield item
            yielded += 1
            if max_count is not None and yielded >= max_count:
                return
            try:
                item = get_next()
            except pywintypes.com_error:
                return
        return

    # Other collections (e.g., Stores/Folders) are indexed with Count/Item(i).
    count_value = _safe_attr(items, "Count")
    if count_value is None:
        return

    try:
        count = int(count_value)
    except (TypeError, ValueError):
        return

    if max_count is not None:
        count = min(count, max_count)

    get_item = getattr(items, "Item", None)
    if not callable(get_item):
        return

    for index in range(1, count + 1):
        try:
            item = get_item(index)
        except pywintypes.com_error:
            continue
        if item is not None:
            yield item


def _cap_windows_query_end(start: datetime, end: datetime) -> datetime:
    max_span_end = start + timedelta(days=31)
    now_limit = datetime.now().replace(microsecond=0) + timedelta(days=31)
    return min(end, max_span_end, now_limit)


def _iter_calendar_folders(namespace: object):
    seen: set[str] = set()
    yielded = 0

    for root in _iter_calendar_roots(namespace):
        for folder in _walk_calendar_folders(root, seen, depth=0, max_depth=8):
            yield folder
            yielded += 1
            if yielded >= 400:
                return


def _iter_calendar_roots(namespace: object):
    seen: set[str] = set()
    stores = _safe_attr(namespace, "Stores")

    if stores is not None:
        for store in _iter_outlook_items(stores, max_count=50):
            root = _store_default_calendar_folder(store)
            if root is None:
                continue
            identifier = _folder_identifier(root)
            if identifier in seen:
                continue
            seen.add(identifier)
            yield root

    default_root = _namespace_default_calendar_folder(namespace)
    if default_root is None:
        return
    identifier = _folder_identifier(default_root)
    if identifier in seen:
        return
    yield default_root


def _walk_calendar_folders(folder: object, seen: set[str], depth: int, max_depth: int):
    identifier = _folder_identifier(folder)
    if identifier in seen:
        return
    seen.add(identifier)

    if _is_calendar_folder(folder):
        yield folder

    if depth >= max_depth:
        return

    child_folders = _safe_attr(folder, "Folders")
    if child_folders is None:
        return

    for child in _iter_outlook_items(child_folders, max_count=200):
        yield from _walk_calendar_folders(child, seen, depth + 1, max_depth)


def _store_default_calendar_folder(store: object):
    try:
        return store.GetDefaultFolder(9)
    except (AttributeError, pywintypes.com_error):
        return None


def _namespace_default_calendar_folder(namespace: object):
    try:
        return namespace.GetDefaultFolder(9)
    except (AttributeError, pywintypes.com_error):
        return None


def _is_calendar_folder(folder: object) -> bool:
    default_item_type = _safe_attr(folder, "DefaultItemType")
    if default_item_type is not None:
        try:
            if int(default_item_type) == 1:
                return True
        except (TypeError, ValueError):
            pass

    message_class = _safe_attr(folder, "DefaultMessageClass", "")
    return str(message_class) == "IPM.Appointment"


def _folder_identifier(folder: object) -> str:
    store_id = _safe_attr(folder, "StoreID", "")
    entry_id = _safe_attr(folder, "EntryID", "")
    name = _safe_attr(folder, "Name", "")
    return f"{store_id}:{entry_id}:{name}"


def _safe_attr(obj: object, attr: str, default: Any = None) -> Any:
    try:
        return getattr(obj, attr)
    except (AttributeError, pywintypes.com_error):
        return default


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


def _resolve_event_availability(item: object) -> str:
    if _is_not_accepted_event(item):
        return "free"
    return _map_outlook_busy_status(_safe_attr(item, "BusyStatus"))


def _is_canceled_event(item: object) -> bool:
    meeting_status = _safe_attr(item, "MeetingStatus")
    if _as_int(meeting_status) == 5:
        return True

    subject = str(_safe_attr(item, "Subject", "") or "").strip().lower()
    if subject.startswith("canceled:") or subject.startswith("cancelled:") or subject.startswith("abgesagt:"):
        return True
    return False


def _is_not_accepted_event(item: object) -> bool:
    response_status = _as_int(_safe_attr(item, "ResponseStatus"))
    # Outlook values: declined=4, not responded=5
    return response_status in {4, 5}


def _as_int(value: object | None) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _clip_events(events: list[CalendarEvent], start: datetime, end: datetime) -> list[CalendarEvent]:
    return [event for event in events if event.end > start and event.start < end]
