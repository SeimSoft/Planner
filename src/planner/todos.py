from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import re


DEFAULT_TODO_FILE = Path(__file__).resolve().parents[2] / "planner_todos.md"
DEFAULT_TODO_ARCHIVE_FILE = Path(__file__).resolve().parents[2] / "planner_todos_archive.md"
_LINK_PATTERN = re.compile(r"^\[(?P<title>.*)\]\((?P<link>https?://[^)]+)\)$")


@dataclass(slots=True, frozen=True)
class TodoItem:
    title: str
    effort_hours: float
    category: str = ""
    link: str | None = None


class TodoStore:
    def __init__(self, file_path: Path | None = None) -> None:
        self._file_path = file_path or DEFAULT_TODO_FILE

    @property
    def file_path(self) -> Path:
        return self._file_path

    def load(self) -> list[TodoItem]:
        if not self._file_path.exists():
            return []

        rows: list[TodoItem] = []
        for line in self._file_path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped.startswith("|"):
                continue
            cells = [cell.strip() for cell in stripped.strip("|").split("|")]
            if len(cells) not in {2, 3}:
                continue
            if cells[0].lower() == "titel" or set(cells[0]) == {"-"}:
                continue

            title, link = _parse_title_and_link(cells[0])
            effort = _parse_effort(cells[1])
            category = cells[2] if len(cells) == 3 else ""
            if not title and effort == 0:
                continue
            rows.append(TodoItem(title=title, effort_hours=effort, category=category, link=link))

        return rows

    def save(self, items: list[TodoItem]) -> None:
        lines = [
            "# Todos",
            "",
            "| Titel | Zeitaufwand [h] | Kategorie |",
            "| --- | ---: | --- |",
        ]
        for item in items:
            title = _format_title_cell(item.title, item.link)
            effort = _format_effort(item.effort_hours)
            category = item.category.replace("|", "\\|").strip()
            lines.append(f"| {title} | {effort} | {category} |")
        lines.append("")
        self._file_path.write_text("\n".join(lines), encoding="utf-8")


class TodoArchiveStore:
    def __init__(self, file_path: Path | None = None) -> None:
        self._file_path = file_path or DEFAULT_TODO_ARCHIVE_FILE

    def archive(self, item: TodoItem, deleted_at: datetime | None = None) -> None:
        timestamp = (deleted_at or datetime.now()).strftime("%Y-%m-%d %H:%M")
        title_cell = _format_title_cell(item.title, item.link)
        effort = _format_effort(item.effort_hours)
        link = item.link or ""
        category = item.category.replace("|", "\\|").strip()

        if not self._file_path.exists():
            lines = [
                "# Todo-Archiv",
                "",
                "| Geloescht am | Titel | Zeitaufwand [h] | Kategorie | Link |",
                "| --- | --- | ---: | --- | --- |",
            ]
        else:
            lines = self._file_path.read_text(encoding="utf-8").splitlines()
            if not lines:
                lines = [
                    "# Todo-Archiv",
                    "",
                    "| Geloescht am | Titel | Zeitaufwand [h] | Kategorie | Link |",
                    "| --- | --- | ---: | --- | --- |",
                ]

        lines.append(f"| {timestamp} | {title_cell} | {effort} | {category} | {link} |")
        if lines[-1] != "":
            lines.append("")
        self._file_path.write_text("\n".join(lines), encoding="utf-8")


def _parse_effort(raw: str) -> float:
    normalized = raw.strip().replace(",", ".")
    if not normalized:
        return 0.0
    try:
        value = float(normalized)
    except ValueError:
        return 0.0
    return max(value, 0.0)


def _format_effort(value: float) -> str:
    rounded = round(max(value, 0.0), 2)
    text = f"{rounded:.2f}".rstrip("0").rstrip(".")
    return text or "0"


def _parse_title_and_link(raw_title_cell: str) -> tuple[str, str | None]:
    match = _LINK_PATTERN.match(raw_title_cell.strip())
    if not match:
        return raw_title_cell.strip(), None
    return match.group("title").strip(), match.group("link").strip()


def _format_title_cell(title: str, link: str | None) -> str:
    safe_title = title.replace("|", "\\|").strip()
    if link:
        safe_link = link.strip()
        if safe_link:
            return f"[{safe_title}]({safe_link})"
    return safe_title


def todo_key(title: str, category: str = "") -> str:
    return f"{title.strip().lower()}::{category.strip().lower()}"
