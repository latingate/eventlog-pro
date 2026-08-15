"""eventlog-pro — a small structured event log with two interchangeable modes.

Importing this package pulls in nothing but the standard library: no Django, no
database driver. Backends are resolved lazily, by DSN scheme, on first write.

    import eventlog_pro

    eventlog_pro.configure(dsn="sqlite:///./eventlog-pro.db")
    eventlog_pro.log_event(app="api", category="webhook", event_code="RECEIVED")
"""

from __future__ import annotations

from .__about__ import __version__
from .api import build_event, delete_events, event_query, log_event, log_event_safe
from .backends.base import Backend
from .config import Settings, configure, get_backend, get_settings, reset
from .criteria import Criteria
from .dsn import ParsedDSN, parse_dsn
from .event import Event
from .exceptions import (
    BackendError,
    ConfigurationError,
    EventLogError,
    UnknownSchemeError,
)
from .registry import known_schemes, register_backend

__all__ = [
    "log_event",
    "log_event_safe",
    "event_query",
    "delete_events",
    "configure",
    "get_settings",
    "reset",
    "Event",
    "Backend",
    "register_backend",
    "EventLogError",
    "ConfigurationError",
    "BackendError",
    "UnknownSchemeError",
    "__version__",
    # Secondary, but part of the supported surface.
    "Settings",
    "Criteria",
    "ParsedDSN",
    "parse_dsn",
    "build_event",
    "get_backend",
    "known_schemes",
]
