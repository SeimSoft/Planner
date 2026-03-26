from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtGui import QColor, QIcon, QPalette
from PySide6.QtWidgets import QApplication

from planner.calendar_api import create_calendar_provider
from planner.ui.main_window import MainWindow


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Planner")
    icon_path = Path(__file__).resolve().parent / "ui" / "icon.png"
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))
    app.setStyle("Fusion")
    palette = app.palette()
    palette.setColor(QPalette.ToolTipBase, QColor("#f8fafc"))
    palette.setColor(QPalette.ToolTipText, QColor("#0f172a"))
    app.setPalette(palette)
    app.setStyleSheet(
        "QToolTip {"
        "background-color: #f8fafc;"
        "color: #0f172a;"
        "border: 1px solid #94a3b8;"
        "padding: 6px;"
        "}"
        "QMenu {"
        "background: #f8fafc;"
        "color: #0f172a;"
        "border: 1px solid #cbd5e1;"
        "}"
        "QMenu::item {"
        "padding: 6px 16px;"
        "}"
        "QMenu::item:selected {"
        "background: #e2e8f0;"
        "color: #0f172a;"
        "}"
    )

    provider = create_calendar_provider()
    window = MainWindow(provider)
    if not app.windowIcon().isNull():
        window.setWindowIcon(app.windowIcon())
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
