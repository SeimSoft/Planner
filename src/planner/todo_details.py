from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re
import shutil

from planner.todos import TodoItem, todo_key


DEFAULT_TODO_DETAILS_DIR = Path(__file__).resolve().parents[2] / "planner_data" / "todos"


@dataclass(slots=True, frozen=True)
class TodoDetails:
    todo_dir: Path
    description_path: Path
    attachments_dir: Path


class TodoDetailsStore:
    def __init__(self, base_dir: Path | None = None) -> None:
        self._base_dir = base_dir or DEFAULT_TODO_DETAILS_DIR

    @property
    def base_dir(self) -> Path:
        return self._base_dir

    def ensure(self, todo: TodoItem, initial_description: str | None = None) -> TodoDetails:
        details = self._details_paths(todo)
        details.attachments_dir.mkdir(parents=True, exist_ok=True)
        self._write_metadata(todo, details.todo_dir)
        starter = (initial_description or "").strip()
        if not details.description_path.exists():
            details.description_path.write_text((starter + "\n") if starter else "", encoding="utf-8")
            return details

        if starter:
            current = details.description_path.read_text(encoding="utf-8")
            if not current.strip():
                details.description_path.write_text(starter + "\n", encoding="utf-8")
        return details

    def load_description(self, todo: TodoItem) -> str:
        details = self.ensure(todo)
        return details.description_path.read_text(encoding="utf-8")

    def save_description(self, todo: TodoItem, text: str) -> None:
        details = self.ensure(todo)
        details.description_path.write_text(text, encoding="utf-8")

    def list_attachments(self, todo: TodoItem) -> list[Path]:
        details = self.ensure(todo)
        files = [path for path in details.attachments_dir.iterdir() if path.is_file()]
        return sorted(files, key=lambda path: path.name.lower())

    def add_attachment(self, todo: TodoItem, source: Path) -> Path:
        if not source.exists() or not source.is_file():
            raise FileNotFoundError(str(source))

        details = self.ensure(todo)
        destination = self._unique_attachment_path(details.attachments_dir, source.name)
        shutil.copy2(source, destination)
        return destination

    def remove_attachment(self, todo: TodoItem, file_name: str) -> bool:
        details = self.ensure(todo)
        candidate = details.attachments_dir / file_name
        if not candidate.exists() or not candidate.is_file():
            return False
        candidate.unlink(missing_ok=False)
        return True

    def _details_paths(self, todo: TodoItem) -> TodoDetails:
        category_slug = _slugify(todo.category) or "uncategorized"
        title_slug = _slugify(todo.title) or "todo"
        key = todo_key(todo.title, todo.category)
        digest = hashlib.sha1(key.encode("utf-8", errors="ignore")).hexdigest()[:10]
        todo_dir = self._base_dir / category_slug / f"{title_slug}-{digest}"
        return TodoDetails(
            todo_dir=todo_dir,
            description_path=todo_dir / "description.md",
            attachments_dir=todo_dir / "attachments",
        )

    def _write_metadata(self, todo: TodoItem, todo_dir: Path) -> None:
        todo_dir.mkdir(parents=True, exist_ok=True)
        metadata_path = todo_dir / "meta.json"
        payload = {
            "title": todo.title,
            "category": todo.category,
            "effort_hours": float(todo.effort_hours),
            "link": todo.link,
            "todo_key": todo_key(todo.title, todo.category),
            "updated_at": datetime.now().isoformat(timespec="seconds"),
        }
        metadata_path.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")

    def _unique_attachment_path(self, directory: Path, file_name: str) -> Path:
        candidate = directory / file_name
        if not candidate.exists():
            return candidate

        stem = candidate.stem
        suffix = candidate.suffix
        index = 2
        while True:
            numbered = directory / f"{stem}_{index}{suffix}"
            if not numbered.exists():
                return numbered
            index += 1


def _slugify(value: str) -> str:
    normalized = re.sub(r"[^a-zA-Z0-9]+", "-", value.strip().lower())
    return normalized.strip("-")[:72]
