# Planner

PySide6-Anwendung mit Wochenansicht (Montag bis Sonntag), die Kalendereintraege aus dem Systemkalender liest und in einer zeitlich einsortierten Ansicht darstellt.

## Funktionen

- Wochenansicht Montag bis Sonntag
- Termine mit Titel sowie Start- und Endzeit
- Farbige Darstellung pro Kalender
- Unterstuetzung fuer ganztagige und wiederkehrende Termine
- Plattformabstraktion fuer macOS und Windows
- Tests fuer die Business-Logik

## Start

```bash
uv sync --extra dev
uv run planner
```

## Tests

```bash
uv run pytest
```

## Plattformhinweise

- macOS: verwendet EventKit. Beim ersten Start fragt das System nach Kalenderzugriff.
- Windows: verwendet Outlook ueber COM via pywin32. Outlook muss installiert und ein Profil konfiguriert sein.
