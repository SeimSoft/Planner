from __future__ import annotations

from datetime import datetime

import pytest

pytest.importorskip("holidays")

from planner.holidays import build_day_statuses
from planner.settings import PlannerSettings


def test_christmas_is_non_working_day_in_berlin() -> None:
    week_start = datetime(2026, 12, 21, 0, 0)  # Monday, includes 25.12.
    settings = PlannerSettings(
        workdays=(True, True, True, True, True, False, False),
        residence="Berlin",
    )

    statuses = build_day_statuses(week_start, settings)

    friday = statuses[4]
    assert friday.day_index == 4
    assert friday.is_workday is False
    assert friday.holiday_name is not None


def test_disabled_workday_is_non_working_even_without_holiday() -> None:
    week_start = datetime(2026, 3, 23, 0, 0)
    settings = PlannerSettings(
        workdays=(False, True, True, True, True, False, False),
        residence="",
    )

    statuses = build_day_statuses(week_start, settings)

    monday = statuses[0]
    assert monday.day_index == 0
    assert monday.is_workday is False
