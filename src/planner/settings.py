from __future__ import annotations

from dataclasses import dataclass
from datetime import time

from PySide6.QtCore import QSettings


DEFAULT_WORKDAYS = (True, True, True, True, True, False, False)


@dataclass(slots=True, frozen=True)
class PlannerSettings:
    work_start: time = time(hour=9, minute=0)
    work_end: time = time(hour=17, minute=0)
    workdays: tuple[bool, bool, bool, bool, bool, bool, bool] = DEFAULT_WORKDAYS
    residence: str = ""


class SettingsStore:
    def __init__(self, qsettings: QSettings | None = None) -> None:
        self._settings = qsettings or QSettings("Planner", "Planner")

    def load(self) -> PlannerSettings:
        work_start_raw = str(self._settings.value("work/start", "09:00"))
        work_end_raw = str(self._settings.value("work/end", "17:00"))
        workdays_raw = str(self._settings.value("work/days", "1111100"))
        residence = str(self._settings.value("location/residence", "")).strip()

        workdays = _parse_workdays(workdays_raw)
        work_start = _parse_time(work_start_raw, fallback=time(hour=9, minute=0))
        work_end = _parse_time(work_end_raw, fallback=time(hour=17, minute=0))

        return PlannerSettings(
            work_start=work_start,
            work_end=work_end,
            workdays=workdays,
            residence=residence,
        )

    def save(self, value: PlannerSettings) -> None:
        self._settings.setValue("work/start", _format_time(value.work_start))
        self._settings.setValue("work/end", _format_time(value.work_end))
        self._settings.setValue("work/days", _format_workdays(value.workdays))
        self._settings.setValue("location/residence", value.residence.strip())
        self._settings.sync()


def _parse_time(value: str, fallback: time) -> time:
    parts = value.split(":", 1)
    if len(parts) != 2:
        return fallback

    try:
        hour = int(parts[0])
        minute = int(parts[1])
    except ValueError:
        return fallback

    if hour < 0 or hour > 23 or minute < 0 or minute > 59:
        return fallback

    return time(hour=hour, minute=minute)


def _format_time(value: time) -> str:
    return f"{value.hour:02d}:{value.minute:02d}"


def _parse_workdays(value: str) -> tuple[bool, bool, bool, bool, bool, bool, bool]:
    if len(value) != 7 or any(char not in {"0", "1"} for char in value):
        return DEFAULT_WORKDAYS

    parsed = tuple(char == "1" for char in value)
    return parsed  # type: ignore[return-value]


def _format_workdays(value: tuple[bool, bool, bool, bool, bool, bool, bool]) -> str:
    return "".join("1" if item else "0" for item in value)
