from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
import json
from pathlib import Path

from planner.productivity import FreeSlot
from planner.todos import TodoItem, todo_key


DEFAULT_SCHEDULE_FILE = Path(__file__).resolve().parents[2] / "planner_schedule.json"


@dataclass(slots=True, frozen=True)
class ScheduledTodoBlock:
    title: str
    category: str
    link: str | None
    todo_key: str
    day_index: int
    start_minutes: int
    end_minutes: int
    source_effort_hours: float
    split_part: int = 1
    split_total: int = 1


@dataclass(slots=True, frozen=True)
class SchedulingResult:
    scheduled_blocks: tuple[ScheduledTodoBlock, ...]
    unscheduled_todos: tuple[TodoItem, ...]


@dataclass(slots=True, frozen=True)
class PersistedScheduledTodo:
    week_start: str
    title: str
    category: str
    todo_key: str
    day_index: int
    start_minutes: int
    end_minutes: int
    link: str | None = None


class ScheduleStore:
    def __init__(self, file_path: Path | None = None) -> None:
        self._file_path = file_path or DEFAULT_SCHEDULE_FILE

    @property
    def file_path(self) -> Path:
        return self._file_path

    def load(self) -> list[PersistedScheduledTodo]:
        if not self._file_path.exists():
            return []

        try:
            payload = json.loads(self._file_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return []

        items = payload.get("scheduled_todos", []) if isinstance(payload, dict) else []
        loaded: list[PersistedScheduledTodo] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            try:
                loaded.append(
                    PersistedScheduledTodo(
                        week_start=str(item["week_start"]),
                        title=str(item["title"]),
                        category=str(item.get("category", "")),
                        todo_key=str(item.get("todo_key", todo_key(str(item["title"]), str(item.get("category", ""))))),
                        day_index=int(item["day_index"]),
                        start_minutes=int(item["start_minutes"]),
                        end_minutes=int(item["end_minutes"]),
                        link=str(item["link"]) if item.get("link") else None,
                    )
                )
            except (KeyError, TypeError, ValueError):
                continue
        return loaded

    def save(self, items: list[PersistedScheduledTodo]) -> None:
        payload = {
            "scheduled_todos": [
                {
                    "week_start": item.week_start,
                    "title": item.title,
                    "category": item.category,
                    "todo_key": item.todo_key,
                    "day_index": item.day_index,
                    "start_minutes": item.start_minutes,
                    "end_minutes": item.end_minutes,
                    "link": item.link,
                }
                for item in items
            ]
        }
        self._file_path.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")


def schedule_todos(todos: list[TodoItem], free_slots: tuple[FreeSlot, ...]) -> SchedulingResult:
    working_slots = [
        [slot.day_index, slot.start_minutes, slot.end_minutes]
        for slot in sorted(free_slots, key=lambda item: (item.day_index, item.start_minutes))
    ]

    scheduled_blocks: list[ScheduledTodoBlock] = []
    unscheduled: list[TodoItem] = []
    slot_index = 0

    for todo in todos:
        title = todo.title.strip()
        category = todo.category.strip()
        remaining_minutes = max(0, int(round(todo.effort_hours * 60)))
        if not title or remaining_minutes <= 0:
            continue

        provisional: list[tuple[int, int, int]] = []
        while remaining_minutes > 0 and slot_index < len(working_slots):
            day_index, slot_start, slot_end = working_slots[slot_index]
            available = max(0, slot_end - slot_start)
            if available <= 0:
                slot_index += 1
                continue

            allocation = min(remaining_minutes, available)
            provisional.append((day_index, slot_start, slot_start + allocation))
            working_slots[slot_index][1] = slot_start + allocation
            remaining_minutes -= allocation

            if working_slots[slot_index][1] >= slot_end:
                slot_index += 1

        if remaining_minutes > 0:
            unscheduled.append(
                TodoItem(title=title, effort_hours=remaining_minutes / 60, category=category, link=todo.link)
            )

        total_parts = len(provisional)
        for part_index, (day_index, start_minutes, end_minutes) in enumerate(provisional, start=1):
            scheduled_blocks.append(
                ScheduledTodoBlock(
                    title=title,
                    category=category,
                    link=todo.link,
                    todo_key=todo_key(title, category),
                    day_index=day_index,
                    start_minutes=start_minutes,
                    end_minutes=end_minutes,
                    source_effort_hours=todo.effort_hours,
                    split_part=part_index,
                    split_total=total_parts or 1,
                )
            )

    return SchedulingResult(scheduled_blocks=tuple(scheduled_blocks), unscheduled_todos=tuple(unscheduled))


def to_persisted(
    week_start: date,
    blocks: tuple[ScheduledTodoBlock, ...],
) -> list[PersistedScheduledTodo]:
    week_start_iso = week_start.isoformat()
    return [
        PersistedScheduledTodo(
            week_start=week_start_iso,
            title=block.title,
            category=block.category,
            todo_key=block.todo_key,
            day_index=block.day_index,
            start_minutes=block.start_minutes,
            end_minutes=block.end_minutes,
            link=block.link,
        )
        for block in blocks
    ]


def trim_free_slots_from_now(
    week_start: datetime,
    free_slots: tuple[FreeSlot, ...],
    now: datetime | None = None,
) -> tuple[FreeSlot, ...]:
    """Remove/clip slots in the past for the current week.

    For future weeks this returns slots unchanged. For past weeks it returns empty.
    """
    current = now or datetime.now()
    current_week_start = current - timedelta(days=current.weekday())
    current_week_start = datetime.combine(current_week_start.date(), datetime.min.time())

    if week_start < current_week_start:
        return ()
    if week_start > current_week_start:
        return free_slots

    day_index = current.weekday()
    minute_now = current.hour * 60 + current.minute
    clipped: list[FreeSlot] = []
    for slot in free_slots:
        if slot.day_index < day_index:
            continue
        if slot.day_index > day_index:
            clipped.append(slot)
            continue
        if slot.end_minutes <= minute_now:
            continue
        clipped.append(
            FreeSlot(day_index=slot.day_index, start_minutes=max(slot.start_minutes, minute_now), end_minutes=slot.end_minutes)
        )
    return tuple(clipped)