from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from planner.calendar_api import create_calendar_provider
from planner.ui.main_window import MainWindow


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Planner")
    app.setStyle("Fusion")

    provider = create_calendar_provider()
    window = MainWindow(provider)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
