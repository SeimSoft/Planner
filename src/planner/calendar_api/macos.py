from __future__ import annotations

import logging
from datetime import datetime

import EventKit
import Foundation

from planner.models import CalendarEvent

from .base import CalendarAccessError, CalendarProvider

logger = logging.getLogger(__name__)


class MacOSCalendarProvider(CalendarProvider):
    def __init__(self) -> None:
        self._store = EventKit.EKEventStore.alloc().init()
        self._ensure_access()

    def get_events(self, start: datetime, end: datetime) -> list[CalendarEvent]:
        predicate = self._store.predicateForEventsWithStartDate_endDate_calendars_(
            _as_nsdate(start),
            _as_nsdate(end),
            None,
        )
        events = self._store.eventsMatchingPredicate_(predicate) or []
        normalized: list[CalendarEvent] = []

        for event in events:
            calendar = _objc_attr(event, "calendar")
            normalized.append(
                CalendarEvent(
                    identifier=str(_objc_attr(event, "eventIdentifier") or ""),
                    title=str(_objc_attr(event, "title") or "Ohne Titel"),
                    start=_nsdate_to_datetime(_objc_attr(event, "startDate")),
                    end=_nsdate_to_datetime(_objc_attr(event, "endDate")),
                    is_all_day=bool(_objc_attr(event, "isAllDay")),
                    is_recurring=bool(_objc_attr(event, "hasRecurrenceRules")),
                    calendar_name=str(_objc_attr(calendar, "title") or "Kalender"),
                    location=_optional_str(_objc_attr(event, "location")),
                    notes=_optional_str(_objc_attr(event, "notes")),
                    availability=_map_eventkit_availability(_objc_attr(event, "availability")),
                )
            )

        return normalized

    def _ensure_access(self) -> None:
        if hasattr(self._store, "authorizationStatusForEntityType_"):
            current_status = self._store.authorizationStatusForEntityType_(EventKit.EKEntityTypeEvent)
            logger.info(f"EventKit authorization status: {current_status}")

            if current_status == EventKit.EKAuthorizationStatusAuthorized:
                return

            if current_status == EventKit.EKAuthorizationStatusDenied:
                raise CalendarAccessError(
                    "Kalenderzugriff verweigert. Bitte geben Sie die Berechtigung in "
                    "Systemeinstellungen > Datenschutz > Kalender frei."
                )

            if current_status == EventKit.EKAuthorizationStatusRestricted:
                raise CalendarAccessError("Kalenderzugriff ist eingeschränkt (Elternkontrollen oder MDM).")

        granted = False
        error: str | None = None
        condition = Foundation.NSCondition.alloc().init()

        def completion(access_granted: bool, access_error: object) -> None:
            nonlocal granted, error
            granted = bool(access_granted)
            if access_error is not None:
                error = str(access_error)
            logger.info(f"EventKit completion: granted={granted}, error={error}")
            condition.lock()
            condition.signal()
            condition.unlock()

        logger.info("Requesting EventKit access...")
        condition.lock()
        try:
            if hasattr(self._store, "requestFullAccessToEventsWithCompletion_"):
                logger.info("Using requestFullAccessToEventsWithCompletion_")
                self._store.requestFullAccessToEventsWithCompletion_(completion)
            else:
                logger.info("Using requestAccessToEntityType_completion_")
                self._store.requestAccessToEntityType_completion_(EventKit.EKEntityTypeEvent, completion)
            success = condition.waitUntilDate_(Foundation.NSDate.dateWithTimeIntervalSinceNow_(10))
        finally:
            condition.unlock()

        if not success:
            raise CalendarAccessError(
                "Zeitüberschreitung beim Anfordern des Kalenderzugriffs. "
                "Überprüfen Sie die Systemeinstellungen > Datenschutz > Kalender."
            )

        if error:
            raise CalendarAccessError(f"Kalenderzugriff fehlgeschlagen: {error}")
        if not granted:
            raise CalendarAccessError(
                "Kalenderzugriff wurde verweigert. Bitte geben Sie die Berechtigung in "
                "Systemeinstellungen > Datenschutz > Kalender frei."
            )


def _as_nsdate(value: datetime) -> Foundation.NSDate:
    return Foundation.NSDate.dateWithTimeIntervalSince1970_(value.timestamp())


def _nsdate_to_datetime(value: Foundation.NSDate) -> datetime:
    return datetime.fromtimestamp(value.timeIntervalSince1970())


def _objc_attr(obj: object, name: str) -> object | None:
    if obj is None:
        return None
    value = getattr(obj, name, None)
    if callable(value):
        return value()
    return value


def _optional_str(value: object | None) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _map_eventkit_availability(value: object | None) -> str:
    if value is None:
        return "busy"

    try:
        status = int(value)
    except (TypeError, ValueError):
        return "busy"

    if status == EventKit.EKEventAvailabilityFree:
        return "free"
    if status == EventKit.EKEventAvailabilityTentative:
        return "tentative"
    if status == EventKit.EKEventAvailabilityUnavailable:
        return "out_of_office"
    if status == EventKit.EKEventAvailabilityNotSupported:
        return "busy"
    if status == EventKit.EKEventAvailabilityBusy:
        return "busy"
    return "busy"
