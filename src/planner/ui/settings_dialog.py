from __future__ import annotations

from datetime import time

from PySide6.QtCore import QTime
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QTimeEdit,
    QVBoxLayout,
    QWidget,
)

from planner.settings import PlannerSettings


DAY_NAMES = ("Mo", "Di", "Mi", "Do", "Fr", "Sa", "So")


class SettingsDialog(QDialog):
    def __init__(self, current: PlannerSettings, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Einstellungen")
        self.setModal(True)
        self.resize(520, 360)

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 16, 18, 16)
        root.setSpacing(12)

        form = QFormLayout()
        form.setLabelAlignment(form.labelAlignment())
        form.setHorizontalSpacing(16)
        form.setVerticalSpacing(10)

        self._start = QTimeEdit(self)
        self._start.setDisplayFormat("HH:mm")
        self._start.setTime(_to_qtime(current.work_start))

        self._end = QTimeEdit(self)
        self._end.setDisplayFormat("HH:mm")
        self._end.setTime(_to_qtime(current.work_end))

        self._residence = QLineEdit(self)
        self._residence.setPlaceholderText("z. B. Berlin, Bayern oder NW")
        self._residence.setText(current.residence)

        form.addRow("Arbeitszeit Start", self._start)
        form.addRow("Arbeitszeit Ende", self._end)
        form.addRow("Wohnort", self._residence)

        day_container = QWidget(self)
        day_layout = QGridLayout(day_container)
        day_layout.setContentsMargins(0, 0, 0, 0)
        day_layout.setHorizontalSpacing(10)
        day_layout.setVerticalSpacing(6)

        self._day_checks: list[QCheckBox] = []
        for index, day_name in enumerate(DAY_NAMES):
            checkbox = QCheckBox(day_name, day_container)
            checkbox.setChecked(current.workdays[index])
            self._day_checks.append(checkbox)
            day_layout.addWidget(checkbox, 0 if index < 4 else 1, index if index < 4 else index - 4)

        form.addRow("Arbeitstage", day_container)

        hint = QLabel(
            "Feiertage werden anhand des Wohnorts als Nicht-Arbeitstage markiert.",
            self,
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #6b7280; font-size: 12px;")

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, self)
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)

        root.addLayout(form)
        root.addWidget(hint)
        root.addStretch(1)
        root.addWidget(buttons)

        self._result = current

    @property
    def value(self) -> PlannerSettings:
        return self._result

    def _accept(self) -> None:
        start = self._start.time()
        end = self._end.time()
        if start >= end:
            QMessageBox.warning(self, "Ungueltige Arbeitszeit", "Die Startzeit muss vor der Endzeit liegen.")
            return

        workdays_raw = tuple(checkbox.isChecked() for checkbox in self._day_checks)
        if not any(workdays_raw):
            QMessageBox.warning(self, "Ungueltige Arbeitstage", "Mindestens ein Arbeitstag muss aktiv sein.")
            return

        workdays = (
            bool(workdays_raw[0]),
            bool(workdays_raw[1]),
            bool(workdays_raw[2]),
            bool(workdays_raw[3]),
            bool(workdays_raw[4]),
            bool(workdays_raw[5]),
            bool(workdays_raw[6]),
        )

        self._result = PlannerSettings(
            work_start=time(hour=start.hour(), minute=start.minute()),
            work_end=time(hour=end.hour(), minute=end.minute()),
            workdays=workdays,
            residence=self._residence.text().strip(),
        )
        self.accept()


def _to_qtime(value: time) -> QTime:
    return QTime(value.hour, value.minute)
