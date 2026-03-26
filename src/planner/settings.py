from __future__ import annotations

from dataclasses import dataclass
from datetime import time
from urllib.parse import parse_qs, unquote, urlparse

from PySide6.QtCore import QSettings


DEFAULT_WORKDAYS = (True, True, True, True, True, False, False)


@dataclass(slots=True, frozen=True)
class PlannerSettings:
    work_start: time = time(hour=9, minute=0)
    work_end: time = time(hour=17, minute=0)
    workdays: tuple[bool, bool, bool, bool, bool, bool, bool] = DEFAULT_WORKDAYS
    residence: str = ""
    show_weekends: bool = True
    jira_base_url: str = ""
    jira_jql: str = "resolution = Unresolved AND assignee = currentUser() AND sprint in openSprints() order by updated DESC"
    jira_story_point_hours: float = 8.0
    jira_username: str = ""
    jira_password: str = ""


class SettingsStore:
    def __init__(self, qsettings: QSettings | None = None) -> None:
        self._settings = qsettings or QSettings("Planner", "Planner")

    def load(self) -> PlannerSettings:
        work_start_raw = str(self._settings.value("work/start", "09:00"))
        work_end_raw = str(self._settings.value("work/end", "17:00"))
        workdays_raw = str(self._settings.value("work/days", "1111100"))
        residence = str(self._settings.value("location/residence", "")).strip()
        show_weekends = _parse_bool(self._settings.value("view/show_weekends", True), fallback=True)
        jira_base_url = str(self._settings.value("jira/base_url", "")).strip()
        jira_jql = str(self._settings.value("jira/jql", "")).strip()
        jira_story_point_hours = _parse_float(self._settings.value("jira/story_point_hours", 8.0), fallback=8.0)
        jira_username = str(self._settings.value("jira/username", "")).strip()
        jira_password = str(self._settings.value("jira/password", "")).strip()

        if not jira_base_url and not jira_jql:
            legacy_filter_url = str(self._settings.value("jira/filter_url", "")).strip()
            legacy_base_url, legacy_jql = _parse_legacy_jira_filter_url(legacy_filter_url)
            jira_base_url = legacy_base_url
            jira_jql = legacy_jql

        workdays = _parse_workdays(workdays_raw)
        work_start = _parse_time(work_start_raw, fallback=time(hour=9, minute=0))
        work_end = _parse_time(work_end_raw, fallback=time(hour=17, minute=0))

        return PlannerSettings(
            work_start=work_start,
            work_end=work_end,
            workdays=workdays,
            residence=residence,
            show_weekends=show_weekends,
            jira_base_url=jira_base_url,
            jira_jql=jira_jql or PlannerSettings.jira_jql,
            jira_story_point_hours=max(0.1, jira_story_point_hours),
            jira_username=jira_username,
            jira_password=jira_password,
        )

    def save(self, value: PlannerSettings) -> None:
        self._settings.setValue("work/start", _format_time(value.work_start))
        self._settings.setValue("work/end", _format_time(value.work_end))
        self._settings.setValue("work/days", _format_workdays(value.workdays))
        self._settings.setValue("location/residence", value.residence.strip())
        self._settings.setValue("view/show_weekends", bool(value.show_weekends))
        self._settings.setValue("jira/base_url", value.jira_base_url.strip())
        self._settings.setValue("jira/jql", value.jira_jql.strip())
        self._settings.setValue("jira/story_point_hours", float(value.jira_story_point_hours))
        self._settings.setValue("jira/username", value.jira_username.strip())
        self._settings.setValue("jira/password", value.jira_password.strip())
        self._settings.remove("jira/filter_url")
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


def _parse_bool(value: object, fallback: bool) -> bool:
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off"}:
        return False
    return fallback


def _parse_float(value: object, fallback: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


def _parse_legacy_jira_filter_url(filter_url: str) -> tuple[str, str]:
    if not filter_url:
        return "", ""

    parsed = urlparse(filter_url)
    if not parsed.scheme or not parsed.netloc:
        return "", ""

    base_url = f"{parsed.scheme}://{parsed.netloc}"
    query = parse_qs(parsed.query)
    jql_values = query.get("jql")
    jql = unquote(jql_values[0]).strip() if jql_values else ""
    return base_url, jql
