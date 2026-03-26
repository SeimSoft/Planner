from __future__ import annotations

from pathlib import Path

from planner.productivity import FreeSlot
from datetime import datetime

from planner.scheduling import PersistedScheduledTodo, ScheduleStore, schedule_todos, trim_free_slots_from_now
from planner.todos import TodoItem


def test_schedule_todos_fills_slots_in_priority_order() -> None:
    todos = [
        TodoItem(title="Wichtig", effort_hours=2, category="A"),
        TodoItem(title="Danach", effort_hours=1.5, category="B"),
    ]
    free_slots = (
        FreeSlot(day_index=0, start_minutes=9 * 60, end_minutes=10 * 60),
        FreeSlot(day_index=0, start_minutes=11 * 60, end_minutes=13 * 60),
        FreeSlot(day_index=1, start_minutes=9 * 60, end_minutes=10 * 60),
    )

    result = schedule_todos(todos, free_slots)

    assert [(block.title, block.day_index, block.start_minutes, block.end_minutes) for block in result.scheduled_blocks] == [
        ("Wichtig", 0, 9 * 60, 10 * 60),
        ("Wichtig", 0, 11 * 60, 12 * 60),
        ("Danach", 0, 12 * 60, 13 * 60),
        ("Danach", 1, 9 * 60, 9 * 60 + 30),
    ]
    assert result.scheduled_blocks[0].todo_key == "wichtig::a"
    assert result.scheduled_blocks[-1].todo_key == "danach::b"
    assert result.unscheduled_todos == ()


def test_schedule_todos_reports_remaining_effort() -> None:
    todos = [TodoItem(title="Zu gross", effort_hours=4)]
    free_slots = (FreeSlot(day_index=0, start_minutes=9 * 60, end_minutes=11 * 60),)

    result = schedule_todos(todos, free_slots)

    assert len(result.scheduled_blocks) == 1
    assert result.unscheduled_todos == (TodoItem(title="Zu gross", effort_hours=2),)


def test_schedule_store_roundtrip(tmp_path: Path) -> None:
    file_path = tmp_path / "planner_schedule.json"
    store = ScheduleStore(file_path)
    expected = [
        PersistedScheduledTodo(
            week_start="2026-03-23",
            title="Alpha",
            category="Fokus",
            todo_key="alpha::fokus",
            day_index=0,
            start_minutes=540,
            end_minutes=600,
            link="https://example.com",
        )
    ]

    store.save(expected)
    loaded = store.load()

    assert loaded == expected


def test_trim_free_slots_from_now_current_week() -> None:
    week_start = datetime(2026, 3, 23, 0, 0)  # Monday
    now = datetime(2026, 3, 25, 10, 15)  # Wednesday 10:15
    free_slots = (
        FreeSlot(day_index=1, start_minutes=9 * 60, end_minutes=11 * 60),
        FreeSlot(day_index=2, start_minutes=9 * 60, end_minutes=10 * 60),
        FreeSlot(day_index=2, start_minutes=10 * 60, end_minutes=12 * 60),
        FreeSlot(day_index=4, start_minutes=9 * 60, end_minutes=11 * 60),
    )

    trimmed = trim_free_slots_from_now(week_start, free_slots, now=now)

    assert trimmed == (
        FreeSlot(day_index=2, start_minutes=10 * 60 + 15, end_minutes=12 * 60),
        FreeSlot(day_index=4, start_minutes=9 * 60, end_minutes=11 * 60),
    )