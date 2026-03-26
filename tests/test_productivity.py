from __future__ import annotations

from datetime import datetime, time

from planner.holidays import build_day_statuses
from planner.models import CalendarEvent
from planner.productivity import calculate_free_slots, calculate_productive_time
from planner.settings import PlannerSettings


def test_free_events_do_not_reduce_productive_time() -> None:
    week_start = datetime(2026, 3, 23, 0, 0)
    settings = PlannerSettings(
        work_start=time(hour=9, minute=0),
        work_end=time(hour=17, minute=0),
        workdays=(True, True, True, True, True, False, False),
        residence="",
    )
    day_statuses = build_day_statuses(week_start, settings)

    events = [
        CalendarEvent(
            identifier="busy",
            title="Busy",
            start=datetime(2026, 3, 23, 10, 0),
            end=datetime(2026, 3, 23, 12, 0),
            availability="busy",
        ),
        CalendarEvent(
            identifier="free",
            title="Free Slot",
            start=datetime(2026, 3, 23, 13, 0),
            end=datetime(2026, 3, 23, 15, 0),
            availability="free",
        ),
    ]

    summary = calculate_productive_time(week_start, events, settings, day_statuses)

    # Wochenarbeitszeit: 5 * 8h = 40h
    assert summary.total_work_minutes == 2400
    # Nur der Busy-Termin blockiert: 2h
    assert summary.busy_minutes == 120
    assert summary.free_minutes == 2280


def test_overlapping_busy_events_are_merged() -> None:
    week_start = datetime(2026, 3, 23, 0, 0)
    settings = PlannerSettings(
        work_start=time(hour=9, minute=0),
        work_end=time(hour=17, minute=0),
        workdays=(True, False, False, False, False, False, False),
        residence="",
    )
    day_statuses = build_day_statuses(week_start, settings)

    events = [
        CalendarEvent("1", "A", datetime(2026, 3, 23, 9, 0), datetime(2026, 3, 23, 11, 0), availability="busy"),
        CalendarEvent("2", "B", datetime(2026, 3, 23, 10, 0), datetime(2026, 3, 23, 12, 0), availability="out_of_office"),
    ]

    summary = calculate_productive_time(week_start, events, settings, day_statuses)

    # Montag: 8h Arbeitszeit, geblockt 9-12 = 3h
    assert summary.total_work_minutes == 480
    assert summary.busy_minutes == 180
    assert summary.free_minutes == 300


def test_free_slots_are_reported_inside_work_window() -> None:
    week_start = datetime(2026, 3, 23, 0, 0)
    settings = PlannerSettings(
        work_start=time(hour=9, minute=0),
        work_end=time(hour=17, minute=0),
        workdays=(True, False, False, False, False, False, False),
        residence="",
    )
    day_statuses = build_day_statuses(week_start, settings)
    events = [
        CalendarEvent("1", "A", datetime(2026, 3, 23, 10, 0), datetime(2026, 3, 23, 11, 0), availability="busy"),
        CalendarEvent("2", "B", datetime(2026, 3, 23, 12, 0), datetime(2026, 3, 23, 14, 0), availability="busy"),
        CalendarEvent("3", "C", datetime(2026, 3, 23, 15, 0), datetime(2026, 3, 23, 16, 0), availability="free"),
    ]

    slots = calculate_free_slots(week_start, events, settings, day_statuses)

    monday_slots = [slot for slot in slots if slot.day_index == 0]
    assert [(slot.start_minutes, slot.end_minutes) for slot in monday_slots] == [
        (9 * 60, 10 * 60),
        (11 * 60, 12 * 60),
        (14 * 60, 17 * 60),
    ]
