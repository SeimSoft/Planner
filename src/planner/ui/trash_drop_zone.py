from __future__ import annotations

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, Qt, Signal, QVariantAnimation
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QFrame, QGraphicsOpacityEffect, QHBoxLayout, QLabel, QWidget


class TrashDropZone(QFrame):
    todoDropped = Signal(int)

    def __init__(self, icon_widget: QWidget, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._default_color = QColor("#ef4444")
        self._active_color = QColor("#dc2626")
        self._success_color = QColor("#22c55e")

        self.setAcceptDrops(True)
        self.setFixedHeight(68)
        self.setStyleSheet(self._style_for_color(self._default_color))

        self._opacity = QGraphicsOpacityEffect(self)
        self._opacity.setOpacity(0.0)
        self.setGraphicsEffect(self._opacity)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(10)
        layout.addWidget(icon_widget)

        label = QLabel("Zum Loeschen hier ablegen", self)
        label.setStyleSheet("color: white; font-weight: 700; font-size: 12px;")
        layout.addWidget(label)
        layout.addStretch(1)

        self._fade = QPropertyAnimation(self._opacity, b"opacity", self)
        self._fade.setDuration(160)
        self._fade.setEasingCurve(QEasingCurve.OutCubic)
        self._fade.finished.connect(self._hide_if_transparent)

        self._flash = QVariantAnimation(self)
        self._flash.setDuration(280)
        self._flash.valueChanged.connect(self._apply_flash_value)
        self.hide()

    def set_drag_active(self, active: bool) -> None:
        self._fade.stop()
        if active:
            self.show()
            self.raise_()
            self._fade.setStartValue(self._opacity.opacity())
            self._fade.setEndValue(1.0)
            self._fade.start()
            return

        self._fade.setStartValue(self._opacity.opacity())
        self._fade.setEndValue(0.0)
        self._fade.start()
        self.setStyleSheet(self._style_for_color(self._default_color))

    def dragEnterEvent(self, event) -> None:
        row = _parse_row(event.mimeData().data("application/x-planner-todo-row").data())
        if row is None:
            event.ignore()
            return
        self.setStyleSheet(self._style_for_color(self._active_color))
        event.acceptProposedAction()

    def dragMoveEvent(self, event) -> None:
        row = _parse_row(event.mimeData().data("application/x-planner-todo-row").data())
        if row is None:
            event.ignore()
            return
        event.acceptProposedAction()

    def dragLeaveEvent(self, event) -> None:
        del event
        self.setStyleSheet(self._style_for_color(self._default_color))

    def dropEvent(self, event) -> None:
        row = _parse_row(event.mimeData().data("application/x-planner-todo-row").data())
        if row is None:
            event.ignore()
            return
        self.todoDropped.emit(row)
        self._play_success_animation()
        event.setDropAction(Qt.MoveAction)
        event.accept()

    def _play_success_animation(self) -> None:
        self._flash.stop()
        self._flash.setStartValue(self._success_color)
        self._flash.setEndValue(self._default_color)
        self._flash.start()

    def _apply_flash_value(self, value) -> None:
        if isinstance(value, QColor):
            self.setStyleSheet(self._style_for_color(value))

    def _hide_if_transparent(self) -> None:
        if self._opacity.opacity() <= 0.01:
            self.hide()

    def _style_for_color(self, color: QColor) -> str:
        return (
            "QFrame {"
            f"background: rgba({color.red()}, {color.green()}, {color.blue()}, 0.95);"
            "border-radius: 14px;"
            "border: 1px solid rgba(255, 255, 255, 0.22);"
            "}"
        )


def _parse_row(raw: bytes) -> int | None:
    try:
        return int(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return None