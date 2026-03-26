from __future__ import annotations

import hashlib
from collections import defaultdict
from datetime import timedelta

from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPaintEvent, QPen
from PySide6.QtWidgets import QFrame, QLabel, QScrollArea, QVBoxLayout, QWidget

from planner.models import AllDayEventLayout, TimedEventLayout, WeekLayout
from planner.productivity import FreeSlot


DAY_NAMES = ("Mo", "Di", "Mi", "Do", "Fr", "Sa", "So")
TIME_GUTTER = 68
HOUR_HEIGHT = 72
ALL_DAY_ROW_HEIGHT = 28
DAY_PADDING = 6
EVENT_PALETTE = ("#dc6b52", "#e5a93d", "#4c9f70", "#3282b8", "#2260c7", "#7c6cc9", "#c95d7b")


class WeekView(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._layout: WeekLayout | None = None
        self._free_slots: tuple[FreeSlot, ...] = ()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._header = _HeaderWidget(self)
        self._all_day = _AllDayWidget(self)
        self._canvas = _TimedCanvas(self)

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setWidget(self._canvas)
        scroll.setStyleSheet("background: transparent;")

        layout.addWidget(self._header)
        layout.addWidget(self._all_day)
        layout.addWidget(scroll, 1)

    def set_week(self, week_layout: WeekLayout) -> None:
        self._layout = week_layout
        self._header.set_week(week_layout)
        self._all_day.set_week(week_layout)
        self._canvas.set_week(week_layout)

    def set_free_slots(self, free_slots: tuple[FreeSlot, ...]) -> None:
        self._free_slots = free_slots
        self._canvas.set_free_slots(free_slots)


class _HeaderWidget(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._layout: WeekLayout | None = None
        self.setMinimumHeight(74)

    def set_week(self, week_layout: WeekLayout) -> None:
        self._layout = week_layout
        self.update()

    def paintEvent(self, event: QPaintEvent) -> None:
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(), QColor("#fdfdfc"))

        if self._layout is None:
            return

        day_width = (self.width() - TIME_GUTTER) / 7
        painter.fillRect(QRect(0, 0, TIME_GUTTER, self.height()), QColor("#f5f7fb"))
        painter.setPen(QColor("#64748b"))
        painter.drawText(QRect(0, 18, TIME_GUTTER - 8, 20), Qt.AlignRight | Qt.AlignVCenter, "Ganztag")

        for day_index, day_name in enumerate(DAY_NAMES):
            x = int(TIME_GUTTER + day_index * day_width)
            rect = QRect(x, 0, int(day_width), self.height())
            date_value = self._layout.week_start + timedelta(days=day_index)
            status = _day_status(self._layout, day_index)

            painter.fillRect(rect.adjusted(0, 0, -1, -1), _day_background_color(day_index, status))
            painter.setPen(QPen(QColor("#e2e8f0"), 1))
            painter.drawLine(rect.topLeft(), rect.bottomLeft())

            painter.setPen(QColor("#0f172a"))
            painter.setFont(QFont("Avenir Next", 14, QFont.DemiBold))
            painter.drawText(rect.adjusted(16, 10, -10, -28), Qt.AlignLeft | Qt.AlignVCenter, day_name)

            painter.setPen(QColor("#64748b"))
            painter.setFont(QFont("Avenir Next", 11))
            painter.drawText(rect.adjusted(16, 34, -10, -8), Qt.AlignLeft | Qt.AlignVCenter, f"{date_value:%d.%m.}")

            if status and status.holiday_name:
                painter.setPen(QColor("#6b7280"))
                painter.setFont(QFont("Avenir Next", 9))
                painter.drawText(rect.adjusted(16, 52, -10, -2), Qt.AlignLeft | Qt.AlignVCenter, status.holiday_name)

        painter.setPen(QPen(QColor("#d8dee9"), 1))
        painter.drawLine(0, self.height() - 1, self.width(), self.height() - 1)


class _AllDayWidget(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._layout: WeekLayout | None = None
        self._chips: list[QLabel] = []
        self.setMinimumHeight(42)

    def set_week(self, week_layout: WeekLayout) -> None:
        self._layout = week_layout
        for chip in self._chips:
            chip.deleteLater()
        self._chips.clear()

        grouped: dict[int, list[AllDayEventLayout]] = defaultdict(list)
        for event_layout in week_layout.all_day_events:
            grouped[event_layout.day_index].append(event_layout)

        max_rows = 0
        for entries in grouped.values():
            max_rows = max(max_rows, len(entries))
            for event_layout in entries:
                chip = QLabel(event_layout.event.title, self)
                chip.setAlignment(Qt.AlignVCenter | Qt.AlignLeft)
                chip.setMargin(6)
                chip.setStyleSheet(
                    "background: {color}; color: white; border-radius: 8px; font-weight: 600;"
                    .format(color=_event_color(event_layout.event.calendar_name or event_layout.event.title))
                )
                chip.setToolTip(_tooltip_text(event_layout.event))
                chip.show()
                self._chips.append(chip)

        self.setFixedHeight(max(42, 12 + max_rows * (ALL_DAY_ROW_HEIGHT + 4)))
        self.update()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._place_chips()

    def paintEvent(self, event: QPaintEvent) -> None:
        del event
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#fffdfc"))
        painter.setPen(QPen(QColor("#e2e8f0"), 1))
        painter.drawLine(0, self.height() - 1, self.width(), self.height() - 1)
        if self._layout is None:
            return
        day_width = (self.width() - TIME_GUTTER) / 7
        painter.fillRect(QRect(0, 0, TIME_GUTTER, self.height()), QColor("#f5f7fb"))
        for day_index in range(7):
            x = int(TIME_GUTTER + day_index * day_width)
            status = _day_status(self._layout, day_index)
            painter.fillRect(
                QRect(x, 0, int(day_width), self.height()),
                _day_background_color(day_index, status, default_weekend="#fffdfc"),
            )
            if status and status.holiday_name:
                painter.setPen(QColor("#6b7280"))
                painter.setFont(QFont("Avenir Next", 9))
                painter.drawText(
                    QRect(x + 8, self.height() - 16, int(day_width) - 10, 14),
                    Qt.AlignLeft | Qt.AlignVCenter,
                    status.holiday_name,
                )
            painter.setPen(QPen(QColor("#e2e8f0"), 1))
            painter.drawLine(x, 0, x, self.height())

    def _place_chips(self) -> None:
        if self._layout is None:
            return
        day_width = (self.width() - TIME_GUTTER) / 7
        for chip, event_layout in zip(self._chips, self._layout.all_day_events):
            x = int(TIME_GUTTER + event_layout.day_index * day_width + DAY_PADDING)
            y = 8 + event_layout.row * (ALL_DAY_ROW_HEIGHT + 4)
            chip.setGeometry(x, y, int(day_width - DAY_PADDING * 2), ALL_DAY_ROW_HEIGHT)


class _TimedCanvas(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._layout: WeekLayout | None = None
        self._free_slots: tuple[FreeSlot, ...] = ()
        self._cards: list[_EventCard] = []
        self.setMinimumHeight(HOUR_HEIGHT * 24)
        self._empty_message: QLabel | None = None

    def set_week(self, week_layout: WeekLayout) -> None:
        self._layout = week_layout
        for card in self._cards:
            card.deleteLater()
        self._cards.clear()

        for event_layout in week_layout.timed_events:
            card = _EventCard(event_layout, self)
            card.show()
            self._cards.append(card)

        self._position_cards()
        self.update()

    def set_free_slots(self, free_slots: tuple[FreeSlot, ...]) -> None:
        self._free_slots = free_slots
        self.update()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._position_cards()

    def paintEvent(self, event: QPaintEvent) -> None:
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(), QColor("#fffdfc"))

        day_width = (self.width() - TIME_GUTTER) / 7
        painter.fillRect(QRect(0, 0, TIME_GUTTER, self.height()), QColor("#f5f7fb"))

        if self._layout is not None:
            for day_index in range(7):
                x = int(TIME_GUTTER + day_index * day_width)
                status = _day_status(self._layout, day_index)
                painter.fillRect(
                    QRect(x, 0, int(day_width), self.height()),
                    _day_background_color(day_index, status, default_weekend="#fffdfc"),
                )

        if self._free_slots:
            painter.setPen(Qt.NoPen)
            for slot in self._free_slots:
                x = TIME_GUTTER + slot.day_index * day_width + DAY_PADDING
                y = slot.start_minutes * (HOUR_HEIGHT / 60)
                width = max(day_width - DAY_PADDING * 2, 12)
                height = max((slot.end_minutes - slot.start_minutes) * (HOUR_HEIGHT / 60), 8)

                # Soft green overlay to highlight productive free windows.
                painter.setBrush(QColor(170, 233, 192, 120))
                painter.drawRoundedRect(QRect(int(x), int(y + 1), int(width), int(height - 2)), 10, 10)

        for hour in range(24):
            y = hour * HOUR_HEIGHT
            painter.setPen(QColor("#94a3b8"))
            painter.drawText(QRect(0, y - 10, TIME_GUTTER - 10, 20), Qt.AlignRight | Qt.AlignVCenter, f"{hour:02d}:00")
            painter.setPen(QPen(QColor("#e2e8f0"), 1))
            painter.drawLine(TIME_GUTTER, y, self.width(), y)

        for day_index in range(8):
            x = int(TIME_GUTTER + day_index * day_width)
            painter.setPen(QPen(QColor("#e2e8f0"), 1))
            painter.drawLine(x, 0, x, self.height())

    def _position_cards(self) -> None:
        if self._layout is None:
            return
        day_width = (self.width() - TIME_GUTTER) / 7
        pixels_per_minute = HOUR_HEIGHT / 60

        for card in self._cards:
            event_layout = card.layout_data
            column_width = (day_width - DAY_PADDING * 2) / max(event_layout.column_count, 1)
            x = TIME_GUTTER + event_layout.day_index * day_width + DAY_PADDING + event_layout.column * column_width
            y = event_layout.start_minutes * pixels_per_minute
            height = max((event_layout.end_minutes - event_layout.start_minutes) * pixels_per_minute, 24)
            width = max(column_width - 4, 48)
            card.setGeometry(int(x), int(y + 1), int(width), int(height - 2))


class _EventCard(QFrame):
    def __init__(self, layout_data: TimedEventLayout, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.layout_data = layout_data

        color = _event_color(layout_data.event.calendar_name or layout_data.event.title)
        self.setStyleSheet(
            "QFrame {"
            f"background: {color};"
            "border-radius: 12px;"
            "border: 1px solid rgba(15, 23, 42, 0.08);"
            "}"
            "QLabel { color: white; background: transparent; }"
        )

        title = QLabel(layout_data.event.title, self)
        title.setWordWrap(True)
        title.setStyleSheet("font-size: 13px; font-weight: 700;")

        time_label = QLabel(
            f"{layout_data.event.start:%H:%M} - {layout_data.event.end:%H:%M}",
            self,
        )
        time_label.setStyleSheet("font-size: 11px; color: rgba(255, 255, 255, 0.92);")

        container = QVBoxLayout(self)
        container.setContentsMargins(10, 8, 10, 8)
        container.setSpacing(2)
        container.addWidget(time_label)
        container.addWidget(title)
        container.addStretch(1)

        self.setToolTip(_tooltip_text(layout_data.event))


def _event_color(seed: str) -> str:
    digest = hashlib.sha1(seed.encode("utf-8", errors="ignore")).digest()[0]
    return EVENT_PALETTE[digest % len(EVENT_PALETTE)]


def _day_status(layout: WeekLayout, day_index: int):
    for item in layout.day_statuses:
        if item.day_index == day_index:
            return item
    return None


def _day_background_color(day_index: int, status, default_weekend: str = "#ffffff") -> QColor:
    if status and not status.is_workday:
        return QColor("#eceff3")
    if day_index >= 5:
        return QColor(default_weekend)
    return QColor("#ffffff")


def _tooltip_text(event) -> str:
    details = [f"{event.title}", f"{event.start:%d.%m.%Y %H:%M} - {event.end:%d.%m.%Y %H:%M}"]
    if event.calendar_name:
        details.append(f"Kalender: {event.calendar_name}")
    if event.location:
        details.append(f"Ort: {event.location}")
    return "\n".join(details)
