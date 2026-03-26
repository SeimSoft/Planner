from __future__ import annotations

from datetime import time

from PySide6.QtCore import QSettings

from planner.settings import PlannerSettings, SettingsStore


def test_settings_store_roundtrip(tmp_path) -> None:
    settings_file = tmp_path / "planner_settings.ini"
    qsettings = QSettings(str(settings_file), QSettings.IniFormat)
    store = SettingsStore(qsettings)

    expected = PlannerSettings(
        work_start=time(hour=7, minute=30),
        work_end=time(hour=15, minute=45),
        workdays=(True, True, True, True, False, False, False),
        residence="Berlin",
    )

    store.save(expected)
    loaded = store.load()

    assert loaded == expected
