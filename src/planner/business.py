from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, time, timedelta

from .models import AllDayEventLayout, CalendarEvent, DayStatus, TimedEventLayout, WeekLayout


MINUTES_PER_DAY = 24 * 60


def week_bounds(reference: date | datetime | None = None) -> tuple[datetime, datetime]:
    if reference is None:
        current = datetime.now()
    elif isinstance(reference, datetime):
        current = reference
    else:
        current = datetime.combine(reference, time.min)

    week_start = datetime.combine((current - timedelta(days=current.weekday())).date(), time.min)
    week_end = week_start + timedelta(days=7)
    return week_start, week_end


def layout_week_events(
    events: list[CalendarEvent],
    week_start: datetime,
    day_statuses: tuple[DayStatus, ...] | None = None,
) -> WeekLayout:
    week_end = week_start + timedelta(days=7)
    all_day_rows: dict[int, int] = defaultdict(int)
    all_day_layouts: list[AllDayEventLayout] = []
    timed_segments_by_day: dict[int, list[tuple[CalendarEvent, int, int]]] = defaultdict(list)

    for event in sorted(events, key=lambda item: (item.start, item.end, item.title.lower())):
        if event.end <= week_start or event.start >= week_end:
            continue

        clipped_start = max(event.start, week_start)
        clipped_end = min(event.end, week_end)

        for day_index in range(7):
            day_start = week_start + timedelta(days=day_index)
            day_end = day_start + timedelta(days=1)
            segment_start = max(clipped_start, day_start)
            segment_end = min(clipped_end, day_end)
            if segment_end <= segment_start:
                continue

            if _is_effective_all_day(event):
                row = all_day_rows[day_index]
                all_day_layouts.append(AllDayEventLayout(event=event, day_index=day_index, row=row))
                all_day_rows[day_index] += 1
                continue

            start_minutes = _minutes_since_midnight(segment_start)
            end_minutes = _minutes_since_midnight(segment_end)
            if segment_end == day_end:
                end_minutes = MINUTES_PER_DAY
            end_minutes = max(end_minutes, start_minutes + 15)
            timed_segments_by_day[day_index].append((event, start_minutes, min(end_minutes, MINUTES_PER_DAY)))

    timed_layouts: list[TimedEventLayout] = []
    for day_index, segments in timed_segments_by_day.items():
        timed_layouts.extend(_layout_day_segments(day_index, segments))

    timed_layouts.sort(key=lambda item: (item.day_index, item.start_minutes, item.column))
    all_day_layouts.sort(key=lambda item: (item.day_index, item.row, item.event.title.lower()))

    return WeekLayout(
        week_start=week_start,
        timed_events=tuple(timed_layouts),
        all_day_events=tuple(all_day_layouts),
        day_statuses=day_statuses or (),
    )


def _layout_day_segments(
    day_index: int,
    segments: list[tuple[CalendarEvent, int, int]],
) -> list[TimedEventLayout]:
    segments = sorted(segments, key=lambda item: (item[1], item[2], item[0].title.lower()))
    clusters: list[list[tuple[CalendarEvent, int, int]]] = []
    current_cluster: list[tuple[CalendarEvent, int, int]] = []
    current_cluster_end = -1

    for segment in segments:
        _, start_minutes, end_minutes = segment
        if current_cluster and start_minutes >= current_cluster_end:
            clusters.append(current_cluster)
            current_cluster = []
            current_cluster_end = -1

        current_cluster.append(segment)
        current_cluster_end = max(current_cluster_end, end_minutes)

    if current_cluster:
        clusters.append(current_cluster)

    layouts: list[TimedEventLayout] = []
    for cluster in clusters:
        active_until: list[int] = []
        assigned: list[tuple[CalendarEvent, int, int, int]] = []
        max_columns = 0

        for event, start_minutes, end_minutes in cluster:
            reused_column = None
            for index, active_end in enumerate(active_until):
                if active_end <= start_minutes:
                    reused_column = index
                    active_until[index] = end_minutes
                    break

            if reused_column is None:
                reused_column = len(active_until)
                active_until.append(end_minutes)

            max_columns = max(max_columns, len(active_until))
            assigned.append((event, start_minutes, end_minutes, reused_column))

        for event, start_minutes, end_minutes, column in assigned:
            layouts.append(
                TimedEventLayout(
                    event=event,
                    day_index=day_index,
                    start_minutes=start_minutes,
                    end_minutes=end_minutes,
                    column=column,
                    column_count=max_columns,
                )
            )

    return layouts


def _minutes_since_midnight(value: datetime) -> int:
    return value.hour * 60 + value.minute


def _is_effective_all_day(event: CalendarEvent) -> bool:
    if event.is_all_day:
        return True

    start = event.start
    end = event.end
    if end <= start:
        return False

    starts_at_midnight = start.time() == time.min
    ends_at_midnight = end.time() == time.min
    ends_at_last_minute = end.time().hour == 23 and end.time().minute >= 59
    spans_full_day = (end - start) >= timedelta(hours=23, minutes=59)

    if starts_at_midnight and spans_full_day and (ends_at_midnight or ends_at_last_minute):
        return True

    return False
