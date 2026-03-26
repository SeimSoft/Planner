from __future__ import annotations

from datetime import date, datetime, timedelta
from functools import lru_cache

from planner.models import DayStatus
from planner.settings import PlannerSettings

try:
    import holidays as holidays_lib
except Exception:  # pragma: no cover - defensive fallback
    holidays_lib = None


_SUBDIVISION_ALIASES: dict[str, tuple[str, ...]] = {
    "BW": ("bw", "baden-wuerttemberg", "baden wurttemberg", "stuttgart"),
    "BY": ("by", "bayern", "muenchen", "munich", "augsburg", "nuernberg", "nurnberg"),
    "BE": ("be", "berlin"),
    "BB": ("bb", "brandenburg", "potsdam"),
    "HB": ("hb", "bremen"),
    "HH": ("hh", "hamburg"),
    "HE": ("he", "hessen", "frankfurt", "wiesbaden"),
    "MV": ("mv", "mecklenburg-vorpommern", "rostock", "schwerin"),
    "NI": ("ni", "niedersachsen", "hannover"),
    "NW": ("nw", "nrw", "nordrhein-westfalen", "koeln", "koln", "duesseldorf", "dusseldorf"),
    "RP": ("rp", "rheinland-pfalz", "mainz"),
    "SL": ("sl", "saarland", "saarbruecken", "saarbrucken"),
    "SN": ("sn", "sachsen", "leipzig", "dresden"),
    "ST": ("st", "sachsen-anhalt", "magdeburg", "halle"),
    "SH": ("sh", "schleswig-holstein", "kiel", "luebeck", "lubek"),
    "TH": ("th", "thueringen", "thuringen", "erfurt"),
}


def build_day_statuses(week_start: datetime, settings: PlannerSettings) -> tuple[DayStatus, ...]:
    statuses: list[DayStatus] = []
    for day_index in range(7):
        current_day = (week_start + timedelta(days=day_index)).date()
        enabled_workday = settings.workdays[current_day.weekday()]
        holiday_name = get_holiday_name(current_day, settings.residence)
        is_workday = enabled_workday and holiday_name is None
        statuses.append(DayStatus(day_index=day_index, is_workday=is_workday, holiday_name=holiday_name))

    return tuple(statuses)


def get_holiday_name(current_day: date, residence: str) -> str | None:
    if holidays_lib is None:
        return None

    subdivision = infer_german_subdivision(residence)
    holiday_map = _holidays_for_year(current_day.year, subdivision)
    value = holiday_map.get(current_day)
    if value is None:
        return None
    return str(value)


def infer_german_subdivision(residence: str) -> str | None:
    normalized = residence.strip().lower()
    if not normalized:
        return None

    for subdivision, aliases in _SUBDIVISION_ALIASES.items():
        if normalized == subdivision.lower() or normalized in aliases:
            return subdivision
        if any(alias in normalized for alias in aliases):
            return subdivision

    return None


@lru_cache(maxsize=64)
def _holidays_for_year(year: int, subdivision: str | None) -> dict[date, str]:
    if holidays_lib is None:
        return {}

    kwargs: dict[str, str] = {}
    if subdivision:
        kwargs["subdiv"] = subdivision

    calendar = holidays_lib.country_holidays("DE", years=[year], **kwargs)
    return {item_date: str(name) for item_date, name in calendar.items()}
