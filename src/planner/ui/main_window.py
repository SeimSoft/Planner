from __future__ import annotations

import logging
from datetime import datetime, timedelta

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QDockWidget,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from planner.business import layout_week_events, week_bounds
from planner.calendar_api.base import CalendarProvider, CalendarProviderError
from planner.holidays import build_day_statuses
from planner.productivity import ProductivitySummary, calculate_free_slots, calculate_productive_time
from planner.settings import SettingsStore

from .settings_dialog import SettingsDialog
from .week_view import WeekView

logger = logging.getLogger(__name__)


class MainWindow(QMainWindow):
    def __init__(self, provider: CalendarProvider) -> None:
        super().__init__()
        self._provider = provider
        self._reference = datetime.now()
        self._settings_store = SettingsStore()
        self._settings = self._settings_store.load()
        self._latest_summary: ProductivitySummary | None = None

        self.setWindowTitle("Planner")
        self.resize(1380, 900)

        root = QWidget(self)
        self.setCentralWidget(root)

        layout = QVBoxLayout(root)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(14)

        controls = QHBoxLayout()
        controls.setSpacing(10)

        title_block = QVBoxLayout()
        title_block.setSpacing(2)

        self._title = QLabel("Kalender")
        self._title.setStyleSheet("font-size: 30px; font-weight: 700; color: #1f2937;")
        self._subtitle = QLabel()
        self._subtitle.setStyleSheet("font-size: 14px; color: #6b7280;")
        title_block.addWidget(self._title)
        title_block.addWidget(self._subtitle)

        controls.addLayout(title_block)
        controls.addStretch(1)

        previous_button = QPushButton("Vorherige Woche")
        previous_button.clicked.connect(self._show_previous_week)
        today_button = QPushButton("Diese Woche")
        today_button.clicked.connect(self._show_current_week)
        next_button = QPushButton("Naechste Woche")
        next_button.clicked.connect(self._show_next_week)

        for button in (previous_button, today_button, next_button):
            button.setCursor(Qt.PointingHandCursor)
            button.setMinimumHeight(38)
            button.setStyleSheet(
                "QPushButton {"
                "background: #f8fafc; border: 1px solid #cbd5e1; border-radius: 10px;"
                "padding: 0 16px; color: #0f172a; font-weight: 600;"
                "}"
                "QPushButton:hover { background: #eef2ff; border-color: #94a3b8; }"
            )
            controls.addWidget(button)

        self._week_view = WeekView()
        layout.addLayout(controls)
        layout.addWidget(self._week_view, 1)
        self._create_productivity_dock()

        root.setStyleSheet("background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #fffdf8, stop:1 #eef6ff);")
        self._create_menu()
        self.reload()

    def _create_menu(self) -> None:
        settings_menu = self.menuBar().addMenu("Einstellungen")
        open_settings = QAction("Kalender-Einstellungen", self)
        open_settings.triggered.connect(self._open_settings_dialog)
        settings_menu.addAction(open_settings)

    def _create_productivity_dock(self) -> None:
        dock = QDockWidget("Produktive Zeit", self)
        dock.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)
        dock.setFeatures(QDockWidget.DockWidgetMovable | QDockWidget.DockWidgetFloatable)

        container = QWidget(dock)
        content = QVBoxLayout(container)
        content.setContentsMargins(16, 16, 16, 16)
        content.setSpacing(8)

        title = QLabel("Freie Zeit in Arbeitszeit", container)
        title.setStyleSheet("font-size: 13px; color: #6b7280; font-weight: 600;")

        self._productive_hours_label = QLabel("0,0 h", container)
        self._productive_hours_label.setStyleSheet("font-size: 36px; color: #0f172a; font-weight: 800;")

        content.addWidget(title)
        content.addWidget(self._productive_hours_label)
        content.addStretch(1)

        container.setStyleSheet("background: #f8fafc;")
        dock.setWidget(container)
        self.addDockWidget(Qt.RightDockWidgetArea, dock)

    def reload(self) -> None:
        week_start, _ = week_bounds(self._reference)
        # Keep the navigation anchor aligned to Monday 00:00 for stable week hops.
        self._reference = week_start
        week_end = week_start + timedelta(days=6)
        day_statuses = build_day_statuses(week_start, self._settings)

        logger.info(f"Loading events for week {week_start:%Y-%m-%d} to {week_end:%Y-%m-%d}")
        self._subtitle.setText(f"{week_start:%d.%m.%Y} bis {week_end:%d.%m.%Y}")

        try:
            _, events = self._provider.get_current_week_events(self._reference)
            logger.info(f"Loaded {len(events)} events")
            self._week_view.set_week(layout_week_events(events, week_start, day_statuses=day_statuses))
            self._update_productivity(week_start, events, day_statuses)
        except CalendarProviderError as exc:
            logger.error(f"Calendar access error: {exc}", exc_info=True)
            QMessageBox.critical(self, "Kalenderzugriff", f"Fehler beim Laden der Kalendereinträge:\n\n{exc}")
            self._week_view.set_week(layout_week_events([], week_start, day_statuses=day_statuses))
            self._update_productivity(week_start, [], day_statuses)
        except Exception as exc:
            logger.error(f"Unexpected error loading events: {exc}", exc_info=True)
            QMessageBox.critical(self, "Fehler", f"Unerwarteter Fehler:\n\n{exc}")
            self._week_view.set_week(layout_week_events([], week_start, day_statuses=day_statuses))
            self._update_productivity(week_start, [], day_statuses)

    def _open_settings_dialog(self) -> None:
        dialog = SettingsDialog(self._settings, self)
        if dialog.exec() != dialog.Accepted:
            return

        self._settings = dialog.value
        self._settings_store.save(self._settings)
        self.reload()

    def _update_productivity(self, week_start: datetime, events, day_statuses) -> None:
        summary = calculate_productive_time(
            week_start=week_start,
            events=events,
            settings=self._settings,
            day_statuses=day_statuses,
        )
        self._latest_summary = summary
        free_slots = calculate_free_slots(
            week_start=week_start,
            events=events,
            settings=self._settings,
            day_statuses=day_statuses,
        )
        self._week_view.set_free_slots(free_slots)

        value = f"{summary.free_minutes / 60:.1f}".replace(".", ",")
        self._productive_hours_label.setText(f"{value} h")

    def _show_previous_week(self) -> None:
        self._reference = self._reference - timedelta(days=7)
        self.reload()

    def _show_current_week(self) -> None:
        self._reference = datetime.now()
        self.reload()

    def _show_next_week(self) -> None:
        self._reference = self._reference + timedelta(days=7)
        self.reload()
