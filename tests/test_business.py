from __future__ import annotations

from datetime import datetime, timedelta

from planner.business import layout_week_events, week_bounds
from planner.models import CalendarEvent


def test_week_bounds_starts_on_monday() -> None:
    week_start, week_end = week_bounds(datetime(2026, 3, 25, 15, 30))

    assert week_start == datetime(2026, 3, 23, 0, 0)
    assert week_end == datetime(2026, 3, 30, 0, 0)


def test_timed_events_are_split_across_days() -> None:
    week_start = datetime(2026, 3, 23, 0, 0)
    event = CalendarEvent(
        identifier="1",
        title="Deployment",
        start=datetime(2026, 3, 24, 22, 0),
        end=datetime(2026, 3, 25, 1, 0),
    )

    layout = layout_week_events([event], week_start)

    assert len(layout.timed_events) == 2
    assert layout.timed_events[0].day_index == 1
    assert layout.timed_events[0].start_minutes == 22 * 60
    assert layout.timed_events[0].end_minutes == 24 * 60
    assert layout.timed_events[1].day_index == 2
    assert layout.timed_events[1].start_minutes == 0
    assert layout.timed_events[1].end_minutes == 60


def test_overlapping_events_receive_columns() -> None:
    week_start = datetime(2026, 3, 23, 0, 0)
    events = [
        CalendarEvent("1", "Sync", datetime(2026, 3, 23, 9, 0), datetime(2026, 3, 23, 10, 0)),
        CalendarEvent("2", "Review", datetime(2026, 3, 23, 9, 30), datetime(2026, 3, 23, 11, 0)),
        CalendarEvent("3", "Call", datetime(2026, 3, 23, 10, 30), datetime(2026, 3, 23, 11, 30)),
    ]

    layout = layout_week_events(events, week_start)

    assert [item.column for item in layout.timed_events] == [0, 1, 0]
    assert all(item.column_count == 2 for item in layout.timed_events)


def test_all_day_events_are_mapped_per_day() -> None:
    week_start = datetime(2026, 3, 23, 0, 0)
    event = CalendarEvent(
        identifier="4",
        title="Konferenz",
        start=datetime(2026, 3, 26, 0, 0),
        end=datetime(2026, 3, 28, 0, 0),
        is_all_day=True,
    )

    layout = layout_week_events([event], week_start)

    assert [item.day_index for item in layout.all_day_events] == [3, 4]
    assert [item.row for item in layout.all_day_events] == [0, 0]


def test_full_day_event_without_all_day_flag_is_treated_as_all_day() -> None:
    week_start = datetime(2026, 4, 20, 0, 0)
    event = CalendarEvent(
        identifier="5",
        title="Hausmuell",
        start=datetime(2026, 4, 23, 0, 0),
        end=datetime(2026, 4, 23, 23, 59),
        is_all_day=False,
    )

    layout = layout_week_events([event], week_start)

    assert len(layout.timed_events) == 0
    assert [item.day_index for item in layout.all_day_events] == [3]


def test_multi_day_full_day_event_without_all_day_flag_is_treated_as_all_day() -> None:
    week_start = datetime(2026, 4, 20, 0, 0)
    event = CalendarEvent(
        identifier="6",
        title="Containerdienst",
        start=datetime(2026, 4, 22, 0, 0),
        end=datetime(2026, 4, 24, 23, 59),
        is_all_day=False,
    )

    layout = layout_week_events([event], week_start)

    assert len(layout.timed_events) == 0
    assert [item.day_index for item in layout.all_day_events] == [2, 3, 4]


def test_navigation_to_next_week_returns_events() -> None:
    week_start1 = datetime(2026, 3, 23, 0, 0)
    week_start2 = week_start1 + timedelta(days=7)

    event1 = CalendarEvent("1", "Event", datetime(2026, 3, 24, 10, 0), datetime(2026, 3, 24, 11, 0))
    event2 = CalendarEvent("2", "Event", datetime(2026, 3, 31, 14, 0), datetime(2026, 3, 31, 15, 0))

    layout1 = layout_week_events([event1, event2], week_start1)
    layout2 = layout_week_events([event1, event2], week_start2)

    assert len(layout1.timed_events) == 1
    assert layout1.timed_events[0].event.title == "Event"
    assert layout1.timed_events[0].day_index == 1

    assert len(layout2.timed_events) == 1
    assert layout2.timed_events[0].event.title == "Event"
    assert layout2.timed_events[0].day_index == 1


def test_week_bounds_is_idempotent() -> None:
    week_start1, week_end1 = week_bounds(datetime(2026, 3, 25, 15, 30))
    week_start2, week_end2 = week_bounds(week_start1)

    assert week_start1 == week_start2
    assert week_end1 == week_end2
