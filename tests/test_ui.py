from __future__ import annotations

from datetime import datetime

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication, QComboBox

from planner.calendar_api.demo import DemoCalendarProvider
from planner.models import CalendarEvent
from planner.todos import TodoItem
from planner.ui.main_window import MainWindow
from planner.ui.todo_table import TodoTableWidget


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def test_event_cards_visible_after_week_navigation(qapp) -> None:
    """EventCards müssen nach Vor/Zurück-Navigation sichtbar sein.

    Neu erstellte Qt-Child-Widgets sind nach dem ersten window.show() unsichtbar
    (WA_WState_Hidden). set_week() muss daher .show() auf jedes neue Widget rufen,
    damit die Karten nach einer Navigation nicht leer bleiben.
    """
    win = MainWindow(DemoCalendarProvider())
    # Fixierter Montag für deterministischen Test
    win._reference = datetime(2026, 3, 23, 0, 0)
    win.reload()
    win.resize(1200, 800)
    win.show()
    qapp.processEvents()

    canvas = win._week_view._canvas
    all_day = win._week_view._all_day

    initial_cards = len(canvas._cards)
    assert initial_cards > 0, "Ausgangszustand: keine Event-Cards gefunden"
    assert all(c.isVisible() for c in canvas._cards), (
        "Ausgangszustand: Cards nach erstem show() unsichtbar"
    )

    # Vorwärts
    win._show_next_week()
    qapp.processEvents()
    assert len(canvas._cards) > 0, "Nach Vorwärts-Navigation: keine Event-Cards"
    assert all(c.isVisible() for c in canvas._cards), (
        "Nach Vorwärts-Navigation: Event-Cards nicht sichtbar"
    )

    # Zurück zur Ausgangswoche
    win._show_previous_week()
    qapp.processEvents()
    assert len(canvas._cards) == initial_cards, (
        f"Nach Zurück-Navigation: {len(canvas._cards)} Cards statt {initial_cards}"
    )
    assert all(c.isVisible() for c in canvas._cards), (
        "Nach Zurück-Navigation: Event-Cards nicht sichtbar – Kalender erscheint leer"
    )

    # All-Day-Chips der Ausgangswoche prüfen
    assert all(chip.isVisible() for chip in all_day._chips), (
        "Nach Zurück-Navigation: All-Day-Chips nicht sichtbar"
    )

    win.close()


def test_productivity_dock_is_populated(qapp) -> None:
    win = MainWindow(DemoCalendarProvider())
    win._reference = datetime(2026, 3, 23, 0, 0)
    win.reload()
    win.show()
    qapp.processEvents()

    text = win._productive_hours_label.text().strip()
    assert text.endswith("h")
    assert text != "0,0 h"

    win.close()


def test_all_day_chip_is_positioned_in_correct_day_column(qapp) -> None:
    class SingleEventProvider(DemoCalendarProvider):
        def get_events(self, start, end):
            return [
                CalendarEvent(
                    identifier="all-day",
                    title="Hausmuell Container in Bruckmuehl",
                    start=datetime(2026, 4, 23, 0, 0),
                    end=datetime(2026, 4, 23, 23, 59),
                    is_all_day=False,
                )
            ]

    win = MainWindow(SingleEventProvider())
    win._reference = datetime(2026, 4, 20, 0, 0)
    win.reload()
    win.resize(1200, 800)
    win.show()
    qapp.processEvents()

    all_day = win._week_view._all_day
    assert len(all_day._chips) == 1

    chip = all_day._chips[0]
    day_width = (all_day.width() - 68) / 7
    expected_x = int(68 + 3 * day_width + 6)

    assert abs(chip.x() - expected_x) <= 2, (
        f"Ganztags-Chip an falscher Position: x={chip.x()} statt etwa {expected_x}"
    )

    win.close()


def test_schedule_button_creates_todo_cards(qapp) -> None:
    win = MainWindow(DemoCalendarProvider())
    win._reference = datetime(2026, 3, 23, 0, 0)
    win.reload()
    win._todo_table.set_todos([TodoItem(title="Deep Work", effort_hours=1.5)])
    win.show()
    qapp.processEvents()

    win._schedule_todos()
    qapp.processEvents()

    assert len(win._week_view._canvas._todo_cards) >= 1

    win.close()


def test_todo_and_calendar_highlight_sync(qapp) -> None:
    win = MainWindow(DemoCalendarProvider())
    win._reference = datetime(2026, 3, 23, 0, 0)
    win.reload()
    win._todo_table.set_todos(
        [
            TodoItem(title="Alpha", effort_hours=1.0, category="Fokus"),
            TodoItem(title="Beta", effort_hours=1.0, category="Admin"),
        ]
    )
    win.show()
    qapp.processEvents()

    win._schedule_todos()
    qapp.processEvents()
    cards = win._week_view._canvas._todo_cards
    assert cards

    win._todo_table.selectRow(0)
    win._todo_table.sync_selected_todo()
    qapp.processEvents()
    assert any(card._highlighted for card in cards)

    cards[0].clicked.emit(cards[0].block.todo_key)
    qapp.processEvents()
    selected = win._todo_table.selectedItems()
    assert selected

    win.close()


def test_todo_table_category_cell_uses_combobox(qapp) -> None:
    table = TodoTableWidget()
    table.set_todos([TodoItem(title="Alpha", effort_hours=2.0, category="Fokus")])
    table.show()
    qapp.processEvents()

    combo = table.cellWidget(0, 2)
    assert isinstance(combo, QComboBox)
    assert combo.currentText() == "Fokus"

    combo.setCurrentText("Admin")
    qapp.processEvents()
    todos = table.current_todos()
    assert todos[0].category == "Admin"

    table.close()


def test_todo_table_new_todo_defaults_to_one_hour(qapp) -> None:
    table = TodoTableWidget()
    table.show()
    qapp.processEvents()

    placeholder_row = table.rowCount() - 1
    table.item(placeholder_row, 0).setText("Neues Thema")
    qapp.processEvents()

    todos = table.current_todos()
    assert len(todos) == 1
    assert todos[0].title == "Neues Thema"
    assert todos[0].effort_hours == 1.0

    table.close()
