from __future__ import annotations

from pathlib import Path

from planner.todo_details import TodoDetailsStore
from planner.todos import TodoArchiveStore, TodoItem, TodoStore


def test_todo_store_roundtrip(tmp_path: Path) -> None:
    file_path = tmp_path / "planner_todos.md"
    store = TodoStore(file_path)
    expected = [
        TodoItem(title="Konzept schreiben", effort_hours=2.5, category="Arbeit"),
        TodoItem(title="Review", effort_hours=1, category="Privat"),
    ]

    store.save(expected)
    loaded = store.load()

    assert loaded == expected
    content = file_path.read_text(encoding="utf-8")
    assert "# Todos" in content
    assert "| Titel | Zeitaufwand [h] | Kategorie |" in content


def test_todo_store_ignores_empty_rows(tmp_path: Path) -> None:
    file_path = tmp_path / "planner_todos.md"
    file_path.write_text(
        "# Todos\n\n| Titel | Zeitaufwand [h] | Kategorie |\n| --- | ---: | --- |\n|  | 0 |  |\n| Aufgabe | 3 | Fokus |\n",
        encoding="utf-8",
    )
    store = TodoStore(file_path)

    loaded = store.load()

    assert loaded == [TodoItem(title="Aufgabe", effort_hours=3, category="Fokus")]


def test_todo_store_reads_legacy_two_column_format(tmp_path: Path) -> None:
    file_path = tmp_path / "planner_todos.md"
    file_path.write_text(
        "# Todos\n\n| Titel | Zeitaufwand [h] |\n| --- | ---: |\n| Legacy | 1.5 |\n",
        encoding="utf-8",
    )
    store = TodoStore(file_path)

    loaded = store.load()

    assert loaded == [TodoItem(title="Legacy", effort_hours=1.5, category="")]


def test_todo_archive_store_writes_markdown(tmp_path: Path) -> None:
    archive_file = tmp_path / "planner_todos_archive.md"
    store = TodoArchiveStore(archive_file)

    store.archive(TodoItem(title="Erledigt", effort_hours=1.0, category="Admin", link="https://example.com"))

    content = archive_file.read_text(encoding="utf-8")
    assert "# Todo-Archiv" in content
    assert "| Geloescht am | Titel | Zeitaufwand [h] | Kategorie | Link |" in content
    assert "Erledigt" in content
    assert "Admin" in content


def test_todo_details_store_creates_markdown_and_metadata(tmp_path: Path) -> None:
    store = TodoDetailsStore(tmp_path / "planner_data" / "todos")
    todo = TodoItem(title="ANAGEN-2993: Test", effort_hours=3.0, category="jira", link="https://example.com")

    details = store.ensure(todo, initial_description="Summary text")

    assert details.todo_dir.exists()
    assert details.description_path.exists()
    assert details.attachments_dir.exists()
    assert store.load_description(todo) == "Summary text\n"
    assert (details.todo_dir / "meta.json").exists()


def test_todo_details_store_adds_unique_attachments(tmp_path: Path) -> None:
    store = TodoDetailsStore(tmp_path / "planner_data" / "todos")
    todo = TodoItem(title="Attachment Todo", effort_hours=1.0, category="ops")
    source = tmp_path / "note.txt"
    source.write_text("v1", encoding="utf-8")

    first = store.add_attachment(todo, source)
    second = store.add_attachment(todo, source)

    assert first.exists()
    assert second.exists()
    assert first.name == "note.txt"
    assert second.name == "note_2.txt"


def test_todo_details_store_fills_empty_existing_description(tmp_path: Path) -> None:
    store = TodoDetailsStore(tmp_path / "planner_data" / "todos")
    todo = TodoItem(title="ANAGEN-2993: Summary", effort_hours=1.0, category="jira")

    details = store.ensure(todo)
    details.description_path.write_text("\n\n", encoding="utf-8")

    store.ensure(todo, initial_description="Filled from jira")

    assert store.load_description(todo) == "Filled from jira\n"
