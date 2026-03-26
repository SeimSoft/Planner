from __future__ import annotations

from abc import ABC, abstractmethod
from typing import NamedTuple

from planner.todos import TodoItem


class ImportResult(NamedTuple):
    imported: list[TodoItem]
    skipped: int
    errors: list[str]


class TodoImportPlugin(ABC):
    """Base class for todo import plugins."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable name of this plugin."""
        raise NotImplementedError

    @abstractmethod
    def is_configured(self) -> bool:
        """Return True if the plugin has required credentials/config."""
        raise NotImplementedError

    @abstractmethod
    async def import_todos(self, existing_todos: list[TodoItem]) -> ImportResult:
        """Fetch todos from external source and return import result.
        
        Existing todos are passed to enable deduplication by title.
        Must not re-import items with matching title.
        """
        raise NotImplementedError


class PluginRegistry:
    """Registry for available import plugins."""

    def __init__(self) -> None:
        self._plugins: dict[str, TodoImportPlugin] = {}

    def register(self, plugin_id: str, plugin: TodoImportPlugin) -> None:
        """Register a plugin with a unique ID."""
        self._plugins[plugin_id] = plugin

    def get(self, plugin_id: str) -> TodoImportPlugin | None:
        """Get a plugin by ID."""
        return self._plugins.get(plugin_id)

    def list_configured(self) -> list[tuple[str, TodoImportPlugin]]:
        """Return all plugins that are currently configured and ready to use."""
        return [(pid, plugin) for pid, plugin in self._plugins.items() if plugin.is_configured()]

    def list_all(self) -> list[tuple[str, TodoImportPlugin]]:
        """Return all registered plugins."""
        return list(self._plugins.items())


_registry = PluginRegistry()


def get_registry() -> PluginRegistry:
    """Get the global plugin registry."""
    return _registry
