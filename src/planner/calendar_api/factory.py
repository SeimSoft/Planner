from __future__ import annotations

import logging
import platform

from .base import CalendarProvider, CalendarProviderError

logger = logging.getLogger(__name__)


def create_calendar_provider() -> CalendarProvider:
    system = platform.system()

    if system == "Darwin":
        from .macos import MacOSCalendarProvider
        try:
            return MacOSCalendarProvider()
        except CalendarProviderError as e:
            logger.warning(f"macOS calendar provider failed: {e}. Falling back to demo provider.")
            from .demo import DemoCalendarProvider
            return DemoCalendarProvider()

    if system == "Windows":
        from .windows import WindowsOutlookCalendarProvider
        try:
            return WindowsOutlookCalendarProvider()
        except CalendarProviderError as e:
            logger.warning(f"Windows calendar provider failed: {e}. Falling back to demo provider.")
            from .demo import DemoCalendarProvider
            return DemoCalendarProvider()

    logging.warning(f"Unsupported OS: {system}. Using demo provider.")
    from .demo import DemoCalendarProvider
    return DemoCalendarProvider()
