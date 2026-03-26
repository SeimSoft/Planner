from __future__ import annotations

import asyncio
from dataclasses import replace
import logging
from datetime import datetime, timedelta
from pathlib import Path

import qtawesome as qta
from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import (
    QDialog,
    QDockWidget,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from planner.business import layout_week_events, week_bounds
from planner.calendar_api.base import CalendarProvider, CalendarProviderError
from planner.holidays import build_day_statuses
from planner.plugins import JiraImportPlugin, get_registry
from planner.productivity import FreeSlot, ProductivitySummary, calculate_free_slots, calculate_productive_time
from planner.scheduling import (
    PersistedScheduledTodo,
    ScheduleStore,
    ScheduledTodoBlock,
    schedule_todos,
    to_persisted,
    trim_free_slots_from_now,
)
from planner.settings import SettingsStore
from planner.todo_details import TodoDetailsStore
from planner.todos import TodoArchiveStore, TodoItem, TodoStore, todo_key

from .settings_dialog import SettingsDialog
from .todo_details_widget import TodoDetailsWidget
from .todo_table import TodoTableWidget
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
        self._latest_free_slots: tuple[FreeSlot, ...] = ()
        self._todo_store = TodoStore()
        self._todo_archive_store = TodoArchiveStore()
        self._todo_details_store = TodoDetailsStore()
        self._schedule_store = ScheduleStore()
        self._persisted_schedule: list[PersistedScheduledTodo] = self._schedule_store.load()
        self._selected_todo_key = ""

        self.setWindowTitle("Planner")
        icon_path = Path(__file__).resolve().parent / "icon.png"
        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))
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
        self._week_view.todoArchiveRequested.connect(self._archive_todo_by_key)
        self._week_view.todoEditLinkRequested.connect(self._edit_todo_link_by_key)
        self._week_view.todoOpenLinkRequested.connect(self._open_todo_link_by_key)
        self._week_view.set_show_weekends(self._settings.show_weekends)
        layout.addLayout(controls)
        layout.addWidget(self._week_view, 1)
        self._create_productivity_dock()

        root.setStyleSheet("background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #fffdf8, stop:1 #eef6ff);")
        self.setStyleSheet(
            "QToolTip {"
            "background-color: #f8fafc;"
            "color: #0f172a;"
            "border: 1px solid #cbd5e1;"
            "padding: 6px;"
            "}"
        )
        self._create_menu()
        self.reload()

    def _create_menu(self) -> None:
        settings_menu = self.menuBar().addMenu("Einstellungen")
        open_settings = QAction("Kalender-Einstellungen", self)
        open_settings.triggered.connect(self._open_settings_dialog)
        settings_menu.addAction(open_settings)

        view_menu = self.menuBar().addMenu("Ansicht")
        self._show_weekends_action = QAction("Wochenende anzeigen", self)
        self._show_weekends_action.setCheckable(True)
        self._show_weekends_action.setChecked(self._settings.show_weekends)
        self._show_weekends_action.toggled.connect(self._toggle_weekends_visibility)
        view_menu.addAction(self._show_weekends_action)

        import_menu = self.menuBar().addMenu("Todos importieren")
        jira_action = QAction("Von Jira", self)
        jira_action.triggered.connect(self._import_todos_from_jira)
        import_menu.addAction(jira_action)

    def _toggle_weekends_visibility(self, visible: bool) -> None:
        self._week_view.set_show_weekends(visible)
        if self._settings.show_weekends != visible:
            self._settings = replace(self._settings, show_weekends=visible)
            self._settings_store.save(self._settings)

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

        todo_header = QHBoxLayout()
        todo_header.setContentsMargins(0, 8, 0, 0)

        todo_title = QLabel("Todos", container)
        todo_title.setStyleSheet("font-size: 13px; color: #6b7280; font-weight: 700;")

        self._schedule_button = QToolButton(container)
        self._schedule_button.setIcon(qta.icon("fa5s.calendar-plus", color="#475569"))
        self._schedule_button.setToolTip("Todos in freie Slots einplanen")
        self._schedule_button.setAutoRaise(True)
        self._schedule_button.clicked.connect(self._schedule_todos)

        todo_header.addWidget(todo_title)
        todo_header.addStretch(1)
        todo_header.addWidget(self._schedule_button)

        self._todo_table = TodoTableWidget(container)
        self._todo_table.setMinimumWidth(280)
        self._todo_table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._todo_table.todosChanged.connect(self._save_todos)
        self._todo_table.todoSelected.connect(self._on_todo_selected)
        self._todo_table.todoArchiveRequested.connect(self._archive_todo_by_key)
        self._todo_table.set_todos(self._todo_store.load())
        self._week_view.todoSelected.connect(self._todo_table.select_todo_by_key)

        content.addWidget(title)
        content.addWidget(self._productive_hours_label)
        content.addLayout(todo_header)
        content.addWidget(self._todo_table, 1)

        container.setStyleSheet("background: #f8fafc;")
        dock.setWidget(container)
        self.addDockWidget(Qt.RightDockWidgetArea, dock)

        self._create_todo_details_dock()

    def _create_todo_details_dock(self) -> None:
        self._todo_details_dock = QDockWidget("Todo Details", self)
        self._todo_details_dock.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)
        self._todo_details_dock.setFeatures(QDockWidget.DockWidgetMovable | QDockWidget.DockWidgetFloatable)

        self._todo_details_widget = TodoDetailsWidget(self._todo_details_dock)
        self._todo_details_widget.descriptionChanged.connect(self._save_selected_todo_description)
        self._todo_details_widget.attachmentsDropped.connect(self._add_attachments_to_selected_todo)
        self._todo_details_widget.attachmentRemoveRequested.connect(self._remove_attachment_from_selected_todo)
        self._todo_details_dock.setWidget(self._todo_details_widget)

        self.addDockWidget(Qt.LeftDockWidgetArea, self._todo_details_dock)
        self._todo_details_dock.hide()

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
            self._apply_persisted_schedule_for_week(week_start)
        except CalendarProviderError as exc:
            logger.error(f"Calendar access error: {exc}", exc_info=True)
            QMessageBox.critical(self, "Kalenderzugriff", f"Fehler beim Laden der Kalendereinträge:\n\n{exc}")
            self._week_view.set_week(layout_week_events([], week_start, day_statuses=day_statuses))
            self._update_productivity(week_start, [], day_statuses)
            self._apply_persisted_schedule_for_week(week_start)
        except Exception as exc:
            logger.error(f"Unexpected error loading events: {exc}", exc_info=True)
            QMessageBox.critical(self, "Fehler", f"Unerwarteter Fehler:\n\n{exc}")
            self._week_view.set_week(layout_week_events([], week_start, day_statuses=day_statuses))
            self._update_productivity(week_start, [], day_statuses)
            self._apply_persisted_schedule_for_week(week_start)

    def _open_settings_dialog(self) -> None:
        dialog = SettingsDialog(self._settings, self)
        if dialog.exec() != QDialog.Accepted:
            return

        self._settings = dialog.value
        self._settings_store.save(self._settings)
        self.reload()

    def _import_todos_from_jira(self) -> None:
        """Handle import from Jira."""
        if not self._settings.jira_base_url or not self._settings.jira_jql:
            QMessageBox.warning(
                self,
                "Jira nicht konfiguriert",
                "Bitte konfigurieren Sie zuerst die Jira-Einstellungen:\n"
                "Einstellungen → Kalender-Einstellungen",
            )
            return

        # Create plugin with current settings
        plugin = JiraImportPlugin(
            base_url=self._settings.jira_base_url,
            jql=self._settings.jira_jql,
            username=self._settings.jira_username,
            password=self._settings.jira_password,
            story_point_hours=self._settings.jira_story_point_hours,
        )

        if not plugin.is_configured():
            QMessageBox.warning(
                self,
                "Jira nicht vollstaendig konfiguriert",
                "Base URL, JQL, Benutzername und Passwort sind erforderlich.",
            )
            return

        # Run async import
        try:
            result = asyncio.run(plugin.import_todos(self._todo_store.load()))
        except Exception as e:
            logger.exception("Jira import error")
            QMessageBox.critical(self, "Fehler beim Import", f"Import fehlgeschlagen:\n\n{str(e)}")
            return

        # Show results
        if result.errors:
            error_msg = "\n".join(result.errors)
            QMessageBox.warning(self, "Fehler beim Import", f"Einige Items konnten nicht importiert werden:\n\n{error_msg}")

        if result.imported:
            # Add imported todos to existing todos
            existing_todos = self._todo_store.load()
            updated_todos = existing_todos + result.imported
            self._todo_store.save(updated_todos)
            self._todo_table.set_todos(updated_todos)
            self._seed_details_for_jira_todos(updated_todos)

            message = f"Erfolgreich {len(result.imported)} Todos von Jira importiert."
            if result.skipped > 0:
                message += f"\n{result.skipped} Todos wurden übersprungen (bereits vorhanden)."
            QMessageBox.information(self, "Import erfolgreich", message)
        else:
            self._seed_details_for_jira_todos(self._todo_store.load())
            QMessageBox.information(self, "Import abgeschlossen", f"Keine neuen Todos importiert. {result.skipped} übersprungen.")

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
        free_slots = trim_free_slots_from_now(week_start, free_slots)
        self._latest_free_slots = free_slots
        self._week_view.set_free_slots(free_slots)

        remaining_free_minutes = sum(max(0, slot.end_minutes - slot.start_minutes) for slot in free_slots)
        current_free_hours = remaining_free_minutes / 60.0
        max_week_hours = summary.total_work_minutes / 60.0
        current_text = f"{current_free_hours:.1f}".replace(".", ",")
        max_text = f"{max_week_hours:.1f}".rstrip("0").rstrip(".").replace(".", ",")
        self._productive_hours_label.setText(f"{current_text} h/{max_text}h")

    def _save_todos(self, todos) -> None:
        todo_items = list(todos)
        self._todo_store.save(todo_items)
        if self._sync_persisted_schedule_links(todo_items):
            self._schedule_store.save(self._persisted_schedule)
            self._apply_persisted_schedule_for_week(self._reference)
        self._refresh_details_for_current_selection()

    def _on_todo_selected(self, selected_key: str) -> None:
        self._selected_todo_key = selected_key.strip().lower()
        self._week_view.set_highlighted_todo(self._selected_todo_key)
        self._refresh_details_for_current_selection()

    def _refresh_details_for_current_selection(self) -> None:
        if not self._selected_todo_key:
            self._todo_details_widget.clear_view()
            self._todo_details_dock.hide()
            return

        selected_todo = self._todo_for_key(self._selected_todo_key)
        if selected_todo is None:
            self._todo_details_widget.clear_view()
            self._todo_details_dock.hide()
            return

        details = self._todo_details_store.ensure(selected_todo)
        description = self._todo_details_store.load_description(selected_todo)
        attachments = self._todo_details_store.list_attachments(selected_todo)
        self._todo_details_widget.set_todo(selected_todo, details, description, attachments)
        self._todo_details_dock.show()

    def _save_selected_todo_description(self, description: str) -> None:
        selected_todo = self._todo_for_key(self._selected_todo_key)
        if selected_todo is None:
            return
        self._todo_details_store.save_description(selected_todo, description)

    def _add_attachments_to_selected_todo(self, paths: list[str]) -> None:
        selected_todo = self._todo_for_key(self._selected_todo_key)
        if selected_todo is None:
            return

        failures: list[str] = []
        for raw_path in paths:
            source = Path(raw_path)
            try:
                self._todo_details_store.add_attachment(selected_todo, source)
            except Exception as exc:
                failures.append(f"{source.name}: {exc}")

        self._refresh_details_for_current_selection()
        if failures:
            QMessageBox.warning(
                self,
                "Attachment konnte nicht hinzugefuegt werden",
                "\n".join(failures),
            )

    def _remove_attachment_from_selected_todo(self, file_name: str) -> None:
        selected_todo = self._todo_for_key(self._selected_todo_key)
        if selected_todo is None:
            return
        self._todo_details_store.remove_attachment(selected_todo, file_name)
        self._refresh_details_for_current_selection()

    def _todo_for_key(self, selected_key: str) -> TodoItem | None:
        normalized = selected_key.strip().lower()
        if not normalized:
            return None
        for todo in self._todo_table.current_todos():
            if todo_key(todo.title, todo.category) == normalized:
                return todo
        return None

    def _seed_details_for_jira_todos(self, todos: list[TodoItem]) -> None:
        for todo in todos:
            if todo.category.strip().lower() != "jira":
                continue
            summary = _jira_summary_from_title(todo.title)
            self._todo_details_store.ensure(todo, initial_description=summary)

    def _archive_todo_by_key(self, todo_key: str) -> None:
        todo = self._todo_table.delete_todo_by_key(todo_key)
        if todo is None:
            return
        self._todo_archive_store.archive(todo)
        self._persisted_schedule = [item for item in self._persisted_schedule if item.todo_key != todo_key]
        self._schedule_store.save(self._persisted_schedule)
        self._save_todos(self._todo_table.current_todos())
        self._apply_persisted_schedule_for_week(self._reference)
        if self._selected_todo_key == todo_key.strip().lower():
            self._selected_todo_key = ""
            self._refresh_details_for_current_selection()

    def _edit_todo_link_by_key(self, todo_key: str) -> None:
        self._todo_table.edit_link_for_todo_key(todo_key)

    def _open_todo_link_by_key(self, todo_key: str) -> None:
        self._todo_table.open_link_for_todo_key(todo_key)

    def _schedule_todos(self) -> None:
        remaining = list(self._todo_table.current_todos())
        if not remaining:
            self._week_view.set_scheduled_todos(())
            return

        first_week_start, _ = week_bounds(self._reference)
        now_week_start, _ = week_bounds(datetime.now())
        if first_week_start < now_week_start:
            first_week_start = now_week_start
        persisted: list[PersistedScheduledTodo] = []
        max_weeks = 26

        for week_offset in range(max_weeks):
            if not remaining:
                break

            week_start = first_week_start + timedelta(days=7 * week_offset)
            day_statuses = build_day_statuses(week_start, self._settings)
            try:
                _, events = self._provider.get_current_week_events(week_start)
            except Exception as exc:
                logger.warning(f"Could not load events for scheduling week {week_start:%Y-%m-%d}: {exc}")
                continue

            free_slots = calculate_free_slots(week_start, events, self._settings, day_statuses)
            free_slots = trim_free_slots_from_now(week_start, free_slots)
            result = schedule_todos(remaining, free_slots)
            persisted.extend(to_persisted(week_start.date(), result.scheduled_blocks))
            remaining = list(result.unscheduled_todos)

        self._persisted_schedule = persisted
        self._schedule_store.save(self._persisted_schedule)
        self._apply_persisted_schedule_for_week(self._reference)

        selected_items = self._todo_table.selectedItems()
        if selected_items:
            self._todo_table.sync_selected_todo()

        if remaining:
            remaining = ", ".join(
                f"{todo.title} ({todo.effort_hours:.1f} h)" for todo in remaining
            )
            QMessageBox.information(
                self,
                "Nicht komplett eingeplant",
                f"Folgende Restaufwaende passen nicht mehr in diese Woche:\n\n{remaining}",
            )

    def _apply_persisted_schedule_for_week(self, week_start: datetime) -> None:
        week_key = week_start.date().isoformat()
        blocks: list[ScheduledTodoBlock] = []
        for item in self._persisted_schedule:
            if item.week_start != week_key:
                continue
            duration_hours = max(0.25, (item.end_minutes - item.start_minutes) / 60)
            blocks.append(
                ScheduledTodoBlock(
                    title=item.title,
                    category=item.category,
                    link=item.link,
                    todo_key=item.todo_key,
                    day_index=item.day_index,
                    start_minutes=item.start_minutes,
                    end_minutes=item.end_minutes,
                    source_effort_hours=duration_hours,
                )
            )
        self._week_view.set_scheduled_todos(tuple(blocks))

    def _sync_persisted_schedule_links(self, todos) -> bool:
        link_by_key = {
            todo_key(todo.title, todo.category): todo.link
            for todo in todos
        }

        changed = False
        updated_items: list[PersistedScheduledTodo] = []
        for item in self._persisted_schedule:
            new_link = link_by_key.get(item.todo_key, item.link)
            if new_link != item.link:
                changed = True
                updated_items.append(
                    PersistedScheduledTodo(
                        week_start=item.week_start,
                        title=item.title,
                        category=item.category,
                        todo_key=item.todo_key,
                        day_index=item.day_index,
                        start_minutes=item.start_minutes,
                        end_minutes=item.end_minutes,
                        link=new_link,
                    )
                )
                continue
            updated_items.append(item)

        if changed:
            self._persisted_schedule = updated_items
        return changed

    def _show_previous_week(self) -> None:
        self._reference = self._reference - timedelta(days=7)
        self.reload()

    def _show_current_week(self) -> None:
        self._reference = datetime.now()
        self.reload()

    def _show_next_week(self) -> None:
        self._reference = self._reference + timedelta(days=7)
        self.reload()


def _jira_summary_from_title(title: str) -> str:
    if ":" not in title:
        return title.strip()
    _, summary = title.split(":", 1)
    return summary.strip()
