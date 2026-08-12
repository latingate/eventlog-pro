"""Exception hierarchy.

Everything the package raises deliberately derives from :class:`EventLogError`,
so a caller can guard a whole ``log_event()`` call with a single ``except``.
``BaseException`` (``KeyboardInterrupt`` / ``SystemExit``) is never swallowed.
"""

from __future__ import annotations

__all__ = [
    "EventLogError",
    "ConfigurationError",
    "BackendError",
    "UnknownSchemeError",
]


class EventLogError(Exception):
    """Base class for every error raised by ``eventlog_pro``."""


class ConfigurationError(EventLogError):
    """Bad or missing configuration.

    Raised for an unparsable DSN, an invalid table name, an unknown
    ``configure()`` keyword, or a backend whose optional driver is not
    installed. The message always names the extra to install.
    """


class BackendError(EventLogError):
    """A backend failed to write, connect, or create its schema.

    The originating driver exception is preserved as ``__cause__``.
    """


class UnknownSchemeError(ConfigurationError):
    """No backend is registered for the DSN scheme."""

    def __init__(self, scheme: str, known: tuple[str, ...] = ()) -> None:
        self.scheme = scheme
        self.known = known
        detail = f" Known schemes: {', '.join(sorted(known))}." if known else ""
        super().__init__(f"No backend registered for scheme {scheme!r}.{detail}")
