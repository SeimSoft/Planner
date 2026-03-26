from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from planner.models import CalendarEvent, DayStatus
from planner.settings import PlannerSettings


MINUTES_PER_DAY = 24 * 60


@dataclass(slots=True, frozen=True)
class ProductivityDaySummary:
    day_index: int
    total_work_minutes: int
    busy_minutes: int
    free_minutes: int


@dataclass(slots=True, frozen=True)
class ProductivitySummary:
    total_work_minutes: int
    busy_minutes: int
    free_minutes: int
    days: tuple[ProductivityDaySummary, ...]


@dataclass(slots=True, frozen=True)
class FreeSlot:
    day_index: int
    start_minutes: int
    end_minutes: int


def calculate_productive_time(
    week_start: datetime,
    events: list[CalendarEvent],
    settings: PlannerSettings,
    day_statuses: tuple[DayStatus, ...],
) -> ProductivitySummary:
    days: list[ProductivityDaySummary] = []

    for day_index in range(7):
        status = _find_day_status(day_statuses, day_index)
        if status is not None and not status.is_workday:
            days.append(
                ProductivityDaySummary(
                    day_index=day_index,
                    total_work_minutes=0,
                    busy_minutes=0,
                    free_minutes=0,
                )
            )
            continue

        day_start = week_start + timedelta(days=day_index)
        work_start_minutes = settings.work_start.hour * 60 + settings.work_start.minute
        work_end_minutes = settings.work_end.hour * 60 + settings.work_end.minute
        work_start = day_start + timedelta(minutes=work_start_minutes)
        work_end = day_start + timedelta(minutes=work_end_minutes)
        total_work_minutes = max(0, int((work_end - work_start).total_seconds() // 60))

        busy_segments = _daily_busy_segments(day_start, work_start, work_end, events)
        busy_minutes = _sum_merged_segments(busy_segments)
        free_minutes = max(0, total_work_minutes - busy_minutes)

        days.append(
            ProductivityDaySummary(
                day_index=day_index,
                total_work_minutes=total_work_minutes,
                busy_minutes=busy_minutes,
                free_minutes=free_minutes,
            )
        )

    total_work = sum(day.total_work_minutes for day in days)
    total_busy = sum(day.busy_minutes for day in days)
    total_free = sum(day.free_minutes for day in days)

    return ProductivitySummary(
        total_work_minutes=total_work,
        busy_minutes=total_busy,
        free_minutes=total_free,
        days=tuple(days),
    )


def calculate_free_slots(
    week_start: datetime,
    events: list[CalendarEvent],
    settings: PlannerSettings,
    day_statuses: tuple[DayStatus, ...],
) -> tuple[FreeSlot, ...]:
    slots: list[FreeSlot] = []

    for day_index in range(7):
        status = _find_day_status(day_statuses, day_index)
        if status is not None and not status.is_workday:
            continue

        day_start = week_start + timedelta(days=day_index)
        work_start_minutes = settings.work_start.hour * 60 + settings.work_start.minute
        work_end_minutes = settings.work_end.hour * 60 + settings.work_end.minute
        if work_end_minutes <= work_start_minutes:
            continue

        work_start = day_start + timedelta(minutes=work_start_minutes)
        work_end = day_start + timedelta(minutes=work_end_minutes)
        busy_segments = _daily_busy_segments(day_start, work_start, work_end, events)
        merged_busy = _merge_segments(busy_segments)

        cursor = work_start_minutes
        for busy_start, busy_end in merged_busy:
            if busy_start > cursor:
                slots.append(FreeSlot(day_index=day_index, start_minutes=cursor, end_minutes=busy_start))
            cursor = max(cursor, busy_end)

        if cursor < work_end_minutes:
            slots.append(FreeSlot(day_index=day_index, start_minutes=cursor, end_minutes=work_end_minutes))

    return tuple(slots)


def _is_blocking_event(event: CalendarEvent) -> bool:
    return event.availability.strip().lower() not in {"free"}


def _sum_merged_segments(segments: list[tuple[int, int]]) -> int:
    merged = _merge_segments(segments)
    return sum(max(0, end - start) for start, end in merged)


def _merge_segments(segments: list[tuple[int, int]]) -> list[tuple[int, int]]:
    if not segments:
        return []

    ordered = sorted(segments)
    merged: list[tuple[int, int]] = []
    current_start, current_end = ordered[0]

    for start, end in ordered[1:]:
        if start <= current_end:
            current_end = max(current_end, end)
            continue

        merged.append((current_start, current_end))
        current_start, current_end = start, end

    merged.append((current_start, current_end))
    return merged


def _daily_busy_segments(
    day_start: datetime,
    work_start: datetime,
    work_end: datetime,
    events: list[CalendarEvent],
) -> list[tuple[int, int]]:
    busy_segments: list[tuple[int, int]] = []
    if work_end <= work_start:
        return busy_segments

    for event in events:
        if not _is_blocking_event(event):
            continue
        if event.end <= work_start or event.start >= work_end:
            continue

        segment_start = max(event.start, work_start)
        segment_end = min(event.end, work_end)
        if segment_end <= segment_start:
            continue

        start_minutes = int((segment_start - day_start).total_seconds() // 60)
        end_minutes = int((segment_end - day_start).total_seconds() // 60)
        busy_segments.append((max(0, start_minutes), min(MINUTES_PER_DAY, end_minutes)))

    return busy_segments


def _find_day_status(day_statuses: tuple[DayStatus, ...], day_index: int) -> DayStatus | None:
    for status in day_statuses:
        if status.day_index == day_index:
            return status
    return None
