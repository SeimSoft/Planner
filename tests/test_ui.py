from __future__ import annotations

from datetime import datetime

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication

from planner.calendar_api.demo import DemoCalendarProvider
from planner.ui.main_window import MainWindow


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
