"""Kill switch — ``null://``.

Accepts every event and stores none, without erroring. ``EVENTLOG_DSN=null://``
is how ops defuse event logging in production without a code change; it counts
what it dropped so the decision stays visible.
"""

from __future__ import annotations

import threading
from typing import ClassVar

from ..event import Event
from .base import Backend

__all__ = ["NullBackend"]


class NullBackend(Backend):
    """Discards everything. ``id`` stays ``None``."""

    schemes: ClassVar[tuple[str, ...]] = ("null",)
    dialect: ClassVar[str | None] = None

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)  # type: ignore[arg-type]
        self.dropped = 0
        self._lock = threading.RLock()

    def write(self, event: Event) -> Event:
        with self._lock:
            self.dropped += 1
        return event
