from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QMimeData, QTimer, Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QSizePolicy,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from planner.todo_details import TodoDetails
from planner.todos import TodoItem
from planner.ui.category_colors import category_color, contrast_text_color

try:
    import markdown
except ImportError:
    markdown = None


class TodoDetailsWidget(QWidget):
    descriptionChanged = Signal(str)
    attachmentsDropped = Signal(list)
    attachmentRemoveRequested = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._current_todo: TodoItem | None = None
        self._current_details: TodoDetails | None = None
        self._suppress_description_signal = False
        self._description_edit_mode = False
        self.setAcceptDrops(True)

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)

        self._title_label = QLabel("Kein Todo ausgewaehlt", self)
        self._title_label.setWordWrap(True)
        self._title_label.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)
        self._title_label.setStyleSheet(
            "font-size: 16px;"
            "font-weight: 700;"
            "color: #0f172a;"
            "border-radius: 8px;"
            "padding: 8px 10px;"
            "background: #e2e8f0;"
        )

        info_grid = QVBoxLayout()
        info_grid.setSpacing(3)

        self._category_label = QLabel("Kategorie: -", self)
        self._estimate_label = QLabel("Schaetzung: -", self)
        for label in (self._category_label, self._estimate_label):
            label.setStyleSheet("font-size: 12px; color: #475569;")
            info_grid.addWidget(label)

        self._description_view = QTextBrowser(self)
        self._description_view.setStyleSheet(
            "QTextBrowser {"
            "background: white;"
            "border: 1px solid #cbd5e1;"
            "border-radius: 8px;"
            "padding: 8px;"
            "font-size: 12px;"
            "color: #0f172a;"
            "}"
        )
        self._description_view.document().setDefaultStyleSheet(
            "body { font-family: sans-serif; margin: 0; padding: 0; } "
            "h1 { font-size: 18px; font-weight: bold; margin: 8px 0; } "
            "h2 { font-size: 16px; font-weight: bold; margin: 6px 0; } "
            "h3 { font-size: 14px; font-weight: bold; margin: 4px 0; } "
            "p { margin: 4px 0; } "
            "code { background: #f0f0f0; padding: 2px 4px; border-radius: 3px; } "
            "pre { background: #f8f8f8; padding: 8px; border-radius: 4px; margin: 4px 0; }"
        )
        self._description_view.mousePressEvent = self._enter_edit_mode
        self._description_view.setReadOnly(True)

        self._description_edit = QPlainTextEdit(self)
        self._description_edit.setPlaceholderText("Beschreibung hier eingeben...\n\n(Click 'View' oder ausserhalb um zu speichern)")
        self._description_edit.setStyleSheet(
            "QPlainTextEdit {"
            "background: white;"
            "border: 1px solid #3b82f6;"
            "border-radius: 8px;"
            "padding: 8px;"
            "font-family: Consolas;"
            "font-size: 12px;"
            "color: #0f172a;"
            "}"
        )
        self._description_edit.textChanged.connect(self._schedule_description_emit)
        self._description_edit.hide()

        self._attachment_list = _AttachmentListWidget(self)
        self._attachment_list.filesDropped.connect(self.attachmentsDropped)
        self._attachment_list.removeRequested.connect(self.attachmentRemoveRequested)
        self._attachment_list.setStyleSheet(
            "QListWidget {"
            "background: white;"
            "border: 1px solid #cbd5e1;"
            "border-radius: 8px;"
            "padding: 4px;"
            "}"
            "QListWidget::item { padding: 6px; }"
            "QListWidget::item:selected { background: #dbeafe; color: #0f172a; }"
        )
        self._attachment_list.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)
        self._attachment_list.setMinimumHeight(0)
        self._attachment_list.setMaximumHeight(96)
        self._attachment_list.hide()

        root.addWidget(self._title_label)
        root.addLayout(info_grid)
        root.addWidget(self._description_view, 1)
        root.addWidget(self._description_edit, 1)
        root.addWidget(self._attachment_list)
        root.setStretch(2, 1)
        root.setStretch(3, 1)
        root.setStretch(4, 0)

        self._description_timer = QTimer(self)
        self._description_timer.setInterval(350)
        self._description_timer.setSingleShot(True)
        self._description_timer.timeout.connect(self._emit_description_changed)

    def set_todo(self, todo: TodoItem, details: TodoDetails, description: str, attachments: list[Path]) -> None:
        self._current_todo = todo
        self._current_details = details

        self._title_label.setText(todo.title)
        header_color = category_color(todo.category)
        header_text = contrast_text_color(header_color)
        self._title_label.setStyleSheet(
            "font-size: 16px;"
            "font-weight: 700;"
            f"color: {header_text};"
            "border-radius: 8px;"
            "padding: 8px 10px;"
            f"background: {header_color.name()};"
        )
        self._category_label.setText(f"Kategorie: {todo.category or '-'}")
        self._estimate_label.setText(f"Schaetzung: {todo.effort_hours:.2f} h")

        self._suppress_description_signal = True
        self._description_edit.setPlainText(description)
        self._render_description_view(description)
        self._suppress_description_signal = False
        self._description_edit_mode = False
        self._description_view.show()
        self._description_edit.hide()

        self._update_attachment_list(attachments)

    def clear_view(self) -> None:
        self._current_todo = None
        self._current_details = None
        self._title_label.setText("Kein Todo ausgewaehlt")
        self._title_label.setStyleSheet(
            "font-size: 16px;"
            "font-weight: 700;"
            "color: #0f172a;"
            "border-radius: 8px;"
            "padding: 8px 10px;"
            "background: #e2e8f0;"
        )
        self._category_label.setText("Kategorie: -")
        self._estimate_label.setText("Schaetzung: -")

        self._suppress_description_signal = True
        self._description_edit.setPlainText("")
        self._description_view.setHtml("")
        self._suppress_description_signal = False
        self._description_edit_mode = False
        self._description_view.show()
        self._description_edit.hide()

        self._update_attachment_list([])

    def _render_description_view(self, text: str) -> None:
        if not text.strip():
            self._description_view.setHtml("<p style='color: #94a3b8; font-style: italic;'>Klick zum Editieren...</p>")
            return

        if markdown is not None:
            try:
                html = markdown.markdown(text, extensions=["extra", "codehilite", "nl2br"])
                self._description_view.setHtml(html)
                return
            except Exception:
                pass

        safe_text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        html = f"<pre style='white-space: pre-wrap; word-wrap: break-word;'>{safe_text}</pre>"
        self._description_view.setHtml(html)

    def _update_attachment_list(self, attachments: list[Path]) -> None:
        if attachments:
            self._attachment_list.set_items(attachments)
            visible_rows = max(1, min(len(attachments), 3))
            self._attachment_list.setMaximumHeight(visible_rows * 30 + 10)
            self._attachment_list.show()
        else:
            self._attachment_list.clear()
            self._attachment_list.hide()

    def _enter_edit_mode(self, event) -> None:
        if self._description_edit_mode or self._current_todo is None:
            return
        self._description_edit_mode = True
        self._description_view.hide()
        self._description_edit.show()
        self._description_edit.setFocus()

    def _exit_edit_mode(self) -> None:
        if not self._description_edit_mode:
            return
        self._description_edit_mode = False
        self._description_edit.hide()
        self._render_description_view(self._description_edit.toPlainText())
        self._description_view.show()

    def _schedule_description_emit(self) -> None:
        if self._suppress_description_signal:
            return
        self._description_timer.start()

    def _emit_description_changed(self) -> None:
        if self._current_todo is None or self._suppress_description_signal:
            return
        self.descriptionChanged.emit(self._description_edit.toPlainText())

    def dragEnterEvent(self, event) -> None:
        if _contains_file_urls(event.mimeData()):
            event.acceptProposedAction()
            return
        event.ignore()

    def dragMoveEvent(self, event) -> None:
        if _contains_file_urls(event.mimeData()):
            event.acceptProposedAction()
            return
        event.ignore()

    def dropEvent(self, event) -> None:
        if not _contains_file_urls(event.mimeData()):
            event.ignore()
            return

        files: list[str] = []
        for url in event.mimeData().urls():
            if not url.isLocalFile():
                continue
            local_path = Path(url.toLocalFile())
            if local_path.is_file():
                files.append(str(local_path))

        if files:
            self.attachmentsDropped.emit(files)
            event.acceptProposedAction()
            return
        event.ignore()

    def focusOutEvent(self, event) -> None:
        if self._description_edit_mode:
            self._exit_edit_mode()
        super().focusOutEvent(event)


class _AttachmentListWidget(QListWidget):
    filesDropped = Signal(list)
    removeRequested = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setSelectionMode(QListWidget.SingleSelection)
        self.itemDoubleClicked.connect(self._open_item)

    def set_items(self, files: list[Path]) -> None:
        self.clear()
        for file_path in files:
            item = QListWidgetItem(file_path.name, self)
            item.setData(Qt.UserRole, str(file_path))
            self.addItem(item)

    def contextMenuEvent(self, event) -> None:
        item = self.itemAt(event.pos())
        if item is None:
            return

        menu = QMenu(self)
        open_action = menu.addAction("Open")
        remove_action = menu.addAction("Remove")
        selected = menu.exec(event.globalPos())
        if selected is open_action:
            self._open_item(item)
        if selected is remove_action:
            name = item.text().strip()
            if name:
                self.removeRequested.emit(name)

    def _open_item(self, item: QListWidgetItem) -> None:
        raw_path = str(item.data(Qt.UserRole) or "").strip()
        if not raw_path:
            return
        path = Path(raw_path)
        if not path.exists():
            QMessageBox.warning(self, "Datei nicht gefunden", f"Datei existiert nicht mehr:\n{path}")
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))


def _contains_file_urls(mime: QMimeData) -> bool:
    if not mime.hasUrls():
        return False
    return any(url.isLocalFile() for url in mime.urls())
