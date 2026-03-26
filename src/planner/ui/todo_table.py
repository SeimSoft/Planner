from __future__ import annotations

from PySide6.QtCore import QMimeData, Qt, Signal
from PySide6.QtCore import QUrl
from PySide6.QtGui import QColor
from PySide6.QtGui import QDesktopServices, QDrag
from PySide6.QtWidgets import QAbstractItemView, QComboBox, QHeaderView, QInputDialog, QMenu, QTableWidget, QTableWidgetItem

from planner.todos import TodoItem, todo_key


class TodoTableWidget(QTableWidget):
    todosChanged = Signal(list)
    dragActiveChanged = Signal(bool)
    todoSelected = Signal(str)
    _PLACEHOLDER_TITLE = "Neues Todo"
    _PLACEHOLDER_EFFORT = "1"
    _PLACEHOLDER_CATEGORY = "Kategorie"
    MIME_TYPE = "application/x-planner-todo-row"
    LINK_ROLE = Qt.UserRole + 1

    def __init__(self, parent=None) -> None:
        super().__init__(0, 3, parent)
        self._loading = False
        self._category_options = ["", "Fokus", "Arbeit", "Admin", "Privat"]
        self.setHorizontalHeaderLabels(["Titel", "Zeitaufwand [h]", "Kategorie"])
        self.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.verticalHeader().setVisible(False)
        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.setSelectionMode(QAbstractItemView.SingleSelection)
        self.setDragDropMode(QAbstractItemView.DragDrop)
        self.setDragDropOverwriteMode(False)
        self.setDefaultDropAction(Qt.MoveAction)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(True)
        self.setEditTriggers(
            QAbstractItemView.DoubleClicked
            | QAbstractItemView.EditKeyPressed
            | QAbstractItemView.AnyKeyPressed
            | QAbstractItemView.SelectedClicked
        )
        self.setAlternatingRowColors(True)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.setStyleSheet(
            "QTableWidget { background: white; border: 1px solid #dbe4ef; border-radius: 12px; }"
            "QHeaderView::section { background: #eef2f7; color: #334155; font-weight: 700; border: none; padding: 8px; }"
            "QTableWidget::item { padding: 6px; }"
        )
        self.cellChanged.connect(self._handle_cell_changed)
        self.customContextMenuRequested.connect(self._open_context_menu)
        self.itemSelectionChanged.connect(self._emit_selected_todo)
        self._append_placeholder_row()

    def set_todos(self, todos: list[TodoItem]) -> None:
        self._loading = True
        try:
            self.setRowCount(0)
            for todo in todos:
                self._append_data_row(todo.title, _format_effort(todo.effort_hours), todo.category, todo.link)
            self._append_placeholder_row()
        finally:
            self._loading = False

    def current_todos(self) -> list[TodoItem]:
        todos: list[TodoItem] = []
        for row_index in range(max(0, self.rowCount() - 1)):
            title_item = self.item(row_index, 0)
            effort_item = self.item(row_index, 1)
            title = title_item.text().strip() if title_item else ""
            link = _clean_link(title_item.data(self.LINK_ROLE) if title_item else None)
            effort = _parse_effort(effort_item.text() if effort_item else "")
            category = self._category_text(row_index)
            if not title and effort == 0:
                continue
            todos.append(TodoItem(title=title, effort_hours=effort, category=category, link=link))
        return todos

    def todo_for_row(self, row: int) -> TodoItem | None:
        if row < 0 or row >= self.rowCount() - 1:
            return None
        title_item = self.item(row, 0)
        effort_item = self.item(row, 1)
        if title_item is None or effort_item is None:
            return None
        return TodoItem(
            title=title_item.text().strip(),
            effort_hours=_parse_effort(effort_item.text()),
            category=self._category_text(row),
            link=_clean_link(title_item.data(self.LINK_ROLE)),
        )

    def delete_row(self, row: int) -> None:
        if row < 0 or row >= self.rowCount() - 1:
            return
        self.removeRow(row)
        self._emit_change()
        self._emit_selected_todo()

    def delete_todo_by_key(self, key: str) -> TodoItem | None:
        normalized = key.strip().lower()
        for row_index in range(max(0, self.rowCount() - 1)):
            todo = self.todo_for_row(row_index)
            if todo and todo_key(todo.title, todo.category) == normalized:
                self.removeRow(row_index)
                self._emit_change()
                self._emit_selected_todo()
                return todo
        return None

    def select_todo_by_key(self, key: str) -> None:
        normalized = key.strip().lower()
        if not normalized:
            self.clearSelection()
            return
        for row_index in range(max(0, self.rowCount() - 1)):
            todo = self.todo_for_row(row_index)
            if todo and todo_key(todo.title, todo.category) == normalized:
                self.selectRow(row_index)
                self.scrollToItem(self.item(row_index, 0))
                return

    def sync_selected_todo(self) -> None:
        self._emit_selected_todo()

    def startDrag(self, supportedActions) -> None:
        row = self.currentRow()
        if row < 0 or row >= self.rowCount() - 1:
            return

        mime_data = QMimeData()
        mime_data.setData(self.MIME_TYPE, str(row).encode("utf-8"))

        drag = QDrag(self)
        drag.setMimeData(mime_data)
        self.dragActiveChanged.emit(True)
        try:
            drag.exec(Qt.MoveAction)
        finally:
            self.dragActiveChanged.emit(False)

    def dropEvent(self, event) -> None:
        if not event.mimeData().hasFormat(self.MIME_TYPE):
            event.ignore()
            return

        source_row = _parse_row(event.mimeData().data(self.MIME_TYPE).data())
        if source_row is None or source_row < 0 or source_row >= self.rowCount() - 1:
            event.ignore()
            return
        if not self._allows_current_drop_position():
            event.ignore()
            return

        target_row = self._target_row_from_event(event)
        self._move_row(source_row, target_row)
        event.setDropAction(Qt.MoveAction)
        event.accept()

    def dragEnterEvent(self, event) -> None:
        if event.mimeData().hasFormat(self.MIME_TYPE):
            event.acceptProposedAction()
            return
        super().dragEnterEvent(event)

    def dragMoveEvent(self, event) -> None:
        if event.mimeData().hasFormat(self.MIME_TYPE):
            event.acceptProposedAction()
        else:
            super().dragMoveEvent(event)
        if not self._allows_current_drop_position():
            event.ignore()

    def _allows_current_drop_position(self) -> bool:
        return self.dropIndicatorPosition() != QAbstractItemView.OnViewport or self.rowCount() > 0

    def _handle_cell_changed(self, row: int, column: int) -> None:
        del column
        if self._loading:
            return

        if row == self.rowCount() - 1:
            title_item = self.item(row, 0)
            effort_item = self.item(row, 1)
            title = title_item.text().strip() if title_item else ""
            effort = effort_item.text().strip() if effort_item else ""
            category = self._category_text(row)

            # Untouched placeholder values should not promote the row to a real todo.
            if title_item is not None and title_item.data(Qt.UserRole):
                if title == self._PLACEHOLDER_TITLE:
                    title = ""
            if effort_item is not None and effort_item.data(Qt.UserRole):
                if effort == self._PLACEHOLDER_EFFORT:
                    effort = ""
            category_item = self.item(row, 2)
            if category_item is not None and category_item.data(Qt.UserRole):
                if category == self._PLACEHOLDER_CATEGORY:
                    category = ""

            if title or effort or category:
                self._loading = True
                try:
                    self._clear_placeholder_style(row)
                    self._append_placeholder_row()
                finally:
                    self._loading = False

        self._emit_change()

    def _normalize_after_user_change(self) -> None:
        if self._loading:
            return
        self._loading = True
        try:
            todos = self.current_todos()
            self.setRowCount(0)
            for todo in todos:
                self._append_data_row(todo.title, _format_effort(todo.effort_hours), todo.category, todo.link)
            self._append_placeholder_row()
        finally:
            self._loading = False
        self._emit_change()

    def _move_row(self, source_row: int, target_row: int) -> None:
        todos = self.current_todos()
        if source_row < 0 or source_row >= len(todos):
            return

        target_row = max(0, min(target_row, len(todos)))
        item = todos.pop(source_row)
        if target_row > source_row:
            target_row -= 1
        todos.insert(target_row, item)

        self._loading = True
        try:
            self.set_todos(todos)
        finally:
            self._loading = False
        self.selectRow(target_row)
        self._emit_change()

    def _target_row_from_event(self, event) -> int:
        position = self.dropIndicatorPosition()
        pos = event.position().toPoint()
        row = self.rowAt(pos.y())
        if row < 0:
            return max(0, self.rowCount() - 1)
        if position == QAbstractItemView.BelowItem:
            return min(row + 1, self.rowCount() - 1)
        if position == QAbstractItemView.AboveItem:
            return row
        if position == QAbstractItemView.OnItem:
            rect = self.visualRect(self.model().index(row, 0))
            if pos.y() >= rect.center().y():
                return min(row + 1, self.rowCount() - 1)
            return row
        return row

    def _emit_change(self) -> None:
        self.todosChanged.emit(self.current_todos())
        self._emit_selected_todo()

    def _append_data_row(self, title: str, effort: str, category: str, link: str | None) -> None:
        row_index = self.rowCount()
        self.insertRow(row_index)
        title_item = _make_item(title)
        title_item.setData(self.LINK_ROLE, _clean_link(link))
        self._apply_title_style(title_item)
        self.setItem(row_index, 0, title_item)
        self.setItem(row_index, 1, _make_item(effort))
        self._set_category_cell(row_index, category, placeholder=False)

    def _open_context_menu(self, position) -> None:
        row = self.rowAt(position.y())
        if row < 0 or row >= self.rowCount() - 1:
            return

        title_item = self.item(row, 0)
        if title_item is None:
            return

        link = _clean_link(title_item.data(self.LINK_ROLE))
        menu = QMenu(self)
        edit_action = menu.addAction("Edit Link")
        open_action = menu.addAction("Open Link")
        open_action.setEnabled(bool(link))

        selected = menu.exec(self.viewport().mapToGlobal(position))
        if selected is edit_action:
            self._edit_link_for_row(row)
        if selected is open_action and link:
            QDesktopServices.openUrl(QUrl(link))

    def _edit_link_for_row(self, row: int) -> None:
        title_item = self.item(row, 0)
        if title_item is None:
            return

        current_link = _clean_link(title_item.data(self.LINK_ROLE)) or ""
        value, accepted = QInputDialog.getText(self, "Edit Link", "URL", text=current_link)
        if not accepted:
            return

        link = _clean_link(value)
        title_item.setData(self.LINK_ROLE, link)
        self._apply_title_style(title_item)
        self._emit_change()

    def _append_placeholder_row(self) -> None:
        row_index = self.rowCount()
        self.insertRow(row_index)

        title_item = _make_item(self._PLACEHOLDER_TITLE)
        title_item.setForeground(QColor("#94a3b8"))
        title_item.setToolTip("Titel hier eingeben")
        title_item.setData(Qt.UserRole, True)
        title_item.setFlags((title_item.flags() | Qt.ItemIsDropEnabled) & ~Qt.ItemIsDragEnabled)

        effort_item = _make_item(self._PLACEHOLDER_EFFORT)
        effort_item.setForeground(QColor("#94a3b8"))
        effort_item.setToolTip("Zeitaufwand in Stunden")
        effort_item.setData(Qt.UserRole, True)
        effort_item.setFlags((effort_item.flags() | Qt.ItemIsDropEnabled) & ~Qt.ItemIsDragEnabled)

        self.setItem(row_index, 0, title_item)
        self.setItem(row_index, 1, effort_item)
        self._set_category_cell(row_index, "", placeholder=True)

    def _clear_placeholder_style(self, row: int) -> None:
        for column in range(self.columnCount()):
            item = self.item(row, column)
            if item is None:
                continue
            if item.data(Qt.UserRole):
                if column == 0 and item.text() == self._PLACEHOLDER_TITLE:
                    item.setText("")
            item.setForeground(QColor("#0f172a"))
            item.setToolTip("")
            item.setData(Qt.UserRole, None)
            item.setFlags(item.flags() | Qt.ItemIsDragEnabled)
            if column == 0:
                self._apply_title_style(item)
        combo = self._category_combo(row)
        if combo is not None:
            self._configure_category_combo_style(combo, placeholder=False)

    def _set_category_cell(self, row: int, category: str, placeholder: bool) -> None:
        item_text = self._PLACEHOLDER_CATEGORY if placeholder else category
        item = _make_item(item_text)
        if placeholder:
            item.setForeground(QColor("#94a3b8"))
            item.setData(Qt.UserRole, True)
            item.setFlags((item.flags() | Qt.ItemIsDropEnabled) & ~Qt.ItemIsDragEnabled)
        else:
            item.setForeground(QColor("#0f172a"))
            item.setData(Qt.UserRole, None)
        self.setItem(row, 2, item)

        combo = QComboBox(self)
        combo.setEditable(True)
        combo.setInsertPolicy(QComboBox.NoInsert)
        options = list(self._category_options)
        if category and category not in options:
            options.append(category)
        combo.addItems(options)
        if placeholder:
            combo.setCurrentText("")
            combo.lineEdit().setPlaceholderText(self._PLACEHOLDER_CATEGORY)
        else:
            combo.setCurrentText(category)
        self._configure_category_combo_style(combo, placeholder=placeholder)
        combo.currentTextChanged.connect(self._on_category_combo_changed)
        self.setCellWidget(row, 2, combo)

    def _category_combo(self, row: int) -> QComboBox | None:
        widget = self.cellWidget(row, 2)
        if isinstance(widget, QComboBox):
            return widget
        return None

    def _row_for_category_combo(self, combo: QComboBox) -> int:
        for row in range(self.rowCount()):
            if self.cellWidget(row, 2) is combo:
                return row
        return -1

    def _category_text(self, row: int) -> str:
        combo = self._category_combo(row)
        if combo is not None:
            return combo.currentText().strip()
        item = self.item(row, 2)
        return item.text().strip() if item else ""

    def _on_category_combo_changed(self, _text: str) -> None:
        combo = self.sender()
        if not isinstance(combo, QComboBox):
            return
        row = self._row_for_category_combo(combo)
        if row < 0:
            return

        category_text = combo.currentText().strip()
        item = self.item(row, 2)
        if item is None:
            return
        item.setText(category_text or self._PLACEHOLDER_CATEGORY)

        is_placeholder_row = row == self.rowCount() - 1 and bool(item.data(Qt.UserRole))
        if is_placeholder_row and category_text:
            self._handle_cell_changed(row, 2)
            return

        if not is_placeholder_row:
            self._configure_category_combo_style(combo, placeholder=False)
            self._emit_change()

    def _configure_category_combo_style(self, combo: QComboBox, placeholder: bool) -> None:
        if placeholder:
            combo.setStyleSheet(
                "QComboBox { color: #94a3b8; border: none; padding: 0 6px; background: transparent; }"
                "QComboBox::drop-down { border: none; width: 18px; }"
            )
            return
        combo.setStyleSheet(
            "QComboBox { color: #0f172a; border: none; padding: 0 6px; background: transparent; }"
            "QComboBox::drop-down { border: none; width: 18px; }"
        )

    def _apply_title_style(self, title_item: QTableWidgetItem) -> None:
        if title_item.data(Qt.UserRole):
            return
        if _clean_link(title_item.data(self.LINK_ROLE)):
            title_item.setForeground(QColor("#2563eb"))
            title_item.setToolTip("Link verfuegbar")
        else:
            title_item.setForeground(QColor("#0f172a"))

    def _emit_selected_todo(self) -> None:
        selected = self.selectedItems()
        if not selected:
            self.todoSelected.emit("")
            return
        row = selected[0].row()
        todo = self.todo_for_row(row)
        if todo is None:
            self.todoSelected.emit("")
            return
        self.todoSelected.emit(todo_key(todo.title, todo.category))


def _make_item(value: str) -> QTableWidgetItem:
    item = QTableWidgetItem(value)
    item.setFlags(item.flags() | Qt.ItemIsEditable | Qt.ItemIsDragEnabled | Qt.ItemIsDropEnabled)
    return item


def _parse_effort(raw: str) -> float:
    normalized = raw.strip().replace(",", ".")
    if not normalized:
        return 0.0
    try:
        return max(float(normalized), 0.0)
    except ValueError:
        return 0.0


def _format_effort(value: float) -> str:
    text = f"{max(value, 0.0):.2f}".rstrip("0").rstrip(".")
    return text or "0"


def _parse_row(raw: bytes) -> int | None:
    try:
        return int(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return None


def _clean_link(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if text.startswith("http://") or text.startswith("https://"):
        return text
    return None
