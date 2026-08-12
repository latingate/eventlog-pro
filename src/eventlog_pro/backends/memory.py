"""In-process backend — ``memory://``.

For tests and for `assert` in a REPL. Rows live in a list on the backend
instance and disappear with it; :func:`eventlog_pro.reset` throws them away.

    configure(dsn="memory://")
    log_event(app="t", category="t", event_code="OK")
    get_backend().events        # -> [Event(id=1, ...)]

``?max_events=`` caps the list (oldest dropped first) so a long-running process
using this by accident cannot exhaust memory. Default 10000.
"""

from __future__ import annotations

import threading
from typing import Any, ClassVar

from ..event import Event
from .base import Backend

__all__ = ["MemoryBackend"]

DEFAULT_MAX_EVENTS = 10_000


class MemoryBackend(Backend):
    """Keeps events in a list, assigning sequential ids from 1."""

    schemes: ClassVar[tuple[str, ...]] = ("memory",)
    dialect: ClassVar[str | None] = None

    def __init__(self, parsed: Any, settings: Any) -> None:
        super().__init__(parsed, settings)
        self.max_events = parsed.int_option("max_events", DEFAULT_MAX_EVENTS) or DEFAULT_MAX_EVENTS
        self.events: list[Event] = []
        self._lock = threading.RLock()
        self._next_id = 1

    def write(self, event: Event) -> Event:
        with self._lock:
            event.id = self._next_id
            self._next_id += 1
            self.events.append(event)
            if len(self.events) > self.max_events:
                del self.events[: len(self.events) - self.max_events]
        return event

    def clear(self) -> None:
        """Drop every stored event; ids keep counting up."""
        with self._lock:
            self.events.clear()

    def close(self) -> None:
        self.clear()
