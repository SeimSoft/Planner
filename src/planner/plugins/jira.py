from __future__ import annotations

import logging
import re

from planner.plugins.base import ImportResult, TodoImportPlugin
from planner.todos import TodoItem

logger = logging.getLogger(__name__)


class JiraImportPlugin(TodoImportPlugin):
    """Import todos from Jira tickets matching a filter."""

    DEFAULT_ACTIVE_SPRINTS_JQL = "resolution = Unresolved AND assignee = currentUser() AND sprint in openSprints() order by updated DESC"

    def __init__(
        self,
        base_url: str = "",
        jql: str = "",
        username: str = "",
        password: str = "",
        story_point_hours: float = 8.0,
    ) -> None:
        self._base_url = base_url.strip()
        self._jql = jql.strip() or self.DEFAULT_ACTIVE_SPRINTS_JQL
        self._username = username.strip()
        self._password = password.strip()
        self._story_point_hours = max(0.1, float(story_point_hours))

    @property
    def name(self) -> str:
        return "Jira"

    def set_credentials(
        self,
        base_url: str,
        jql: str,
        username: str,
        password: str,
        story_point_hours: float = 8.0,
    ) -> None:
        """Update Jira credentials."""
        self._base_url = base_url.strip()
        self._jql = jql.strip() or self.DEFAULT_ACTIVE_SPRINTS_JQL
        self._username = username.strip()
        self._password = password.strip()
        self._story_point_hours = max(0.1, float(story_point_hours))

    def is_configured(self) -> bool:
        """Check if Jira credentials are set."""
        return bool(self._base_url and self._jql and self._username and self._password)

    async def import_todos(self, existing_todos: list[TodoItem]) -> ImportResult:
        """Fetch tickets from Jira filter and convert to todos."""
        if not self.is_configured():
            return ImportResult(imported=[], skipped=0, errors=["Jira ist nicht konfiguriert"])

        try:
            from jira import JIRA
        except ImportError:
            return ImportResult(
                imported=[],
                skipped=0,
                errors=["jira ist nicht installiert. Bitte fuehren Sie `uv sync` aus."],
            )

        existing_titles = {todo.title.lower().strip() for todo in existing_todos}
        imported: list[TodoItem] = []
        skipped = 0
        errors: list[str] = []

        try:
            jira_base_url = _normalize_base_url(self._base_url)
            if not jira_base_url:
                return ImportResult(
                    imported=[],
                    skipped=0,
                    errors=["Ungueltige Jira-Base-URL"],
                )

            jira = JIRA(
                jira_base_url,
                basic_auth=(self._username, self._password),
                options={"verify": False},
            )

            story_point_field_ids = _find_story_point_field_ids(jira)
            issues = jira.search_issues(self._jql, maxResults=False, fields="*all")
            for issue in issues:
                try:
                    effort_hours = _resolve_effort_hours(issue, story_point_field_ids, self._story_point_hours)
                    todo = _convert_issue_to_todo(issue, jira_base_url, effort_hours)
                    if todo.title.lower().strip() in existing_titles:
                        skipped += 1
                    else:
                        imported.append(todo)
                        existing_titles.add(todo.title.lower().strip())
                except Exception as e:
                    issue_key = getattr(issue, "key", "unbekannt")
                    errors.append(f"Issue {issue_key}: {str(e)}")

        except Exception as e:
            logger.exception("Jira import failed")
            errors.append(f"Jira-Import fehlgeschlagen: {str(e)}")

        return ImportResult(imported=imported, skipped=skipped, errors=errors)


def _normalize_base_url(url: str) -> str | None:
    url = url.strip().rstrip("/")
    if not url.startswith(("http://", "https://")):
        return None
    if "/" not in url.replace("https://", "", 1).replace("http://", "", 1):
        return url
    try:
        scheme, remainder = url.split("://", 1)
        host = remainder.split("/", 1)[0]
        return f"{scheme}://{host}"
    except ValueError:
        return None


def _find_story_point_field_ids(jira) -> tuple[str, ...]:
    ids: list[str] = []
    try:
        fields = jira.fields()
    except Exception:
        return ()

    for field in fields:
        field_id = str(field.get("id", ""))
        field_name = str(field.get("name", "")).lower()
        if not field_id:
            continue
        if "story point" in field_name:
            ids.append(field_id)
    return tuple(ids)


def _resolve_effort_hours(issue, story_point_field_ids: tuple[str, ...], story_point_hours: float) -> float:
    fields = issue.raw.get("fields", {}) if hasattr(issue, "raw") else {}

    for key in ("timeoriginalestimate", "aggregatetimeoriginalestimate"):
        estimate_seconds = fields.get(key)
        if isinstance(estimate_seconds, (int, float)) and estimate_seconds > 0:
            return max(0.25, float(estimate_seconds) / 3600.0)

    timetracking = fields.get("timetracking") or {}
    for key in ("originalEstimateSeconds", "remainingEstimateSeconds"):
        estimate_seconds = timetracking.get(key)
        if isinstance(estimate_seconds, (int, float)) and estimate_seconds > 0:
            return max(0.25, float(estimate_seconds) / 3600.0)

    text_estimate = str(timetracking.get("originalEstimate") or timetracking.get("remainingEstimate") or "").strip()
    parsed_hours = _parse_jira_duration_to_hours(text_estimate)
    if parsed_hours is not None:
        return max(0.25, parsed_hours)

    for field_id in story_point_field_ids:
        value = fields.get(field_id)
        if isinstance(value, (int, float)) and value > 0:
            return max(0.25, float(value) * story_point_hours)

    return 1.0


def _parse_jira_duration_to_hours(value: str) -> float | None:
    if not value:
        return None

    token_pattern = re.compile(r"(?P<num>\d+(?:\.\d+)?)\s*(?P<unit>[wdhm])", re.IGNORECASE)
    total = 0.0
    found = False
    for match in token_pattern.finditer(value):
        found = True
        number = float(match.group("num"))
        unit = match.group("unit").lower()
        if unit == "w":
            total += number * 40.0
        elif unit == "d":
            total += number * 8.0
        elif unit == "h":
            total += number
        elif unit == "m":
            total += number / 60.0
    if not found:
        return None
    return total


def _convert_issue_to_todo(issue, jira_base_url: str, effort_hours: float) -> TodoItem:
    """Convert a Jira issue object to a TodoItem."""
    summary = str(getattr(issue.fields, "summary", "") or "").strip()
    title = f"{issue.key}: {summary}" if summary else str(issue.key)
    link = f"{jira_base_url.rstrip('/')}/browse/{issue.key}"

    return TodoItem(
        title=title,
        effort_hours=max(0.25, effort_hours),
        category="jira",
        link=link,
    )
