"""JSONL backend — one JSON object per line, append-only.

``jsonl:///./events.jsonl``  ·  ``jsonl:////var/log/events.jsonl``

``id`` stays ``None``: a file has no sequence, and inventing a counter would
produce ids that collide across processes and restarts. Ship the file to a
collector and let that assign identity.
"""

from __future__ import annotations

import json
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, ClassVar

from ..event import Event
from ..exceptions import BackendError
from .base import Backend

__all__ = ["JSONLBackend"]


class JSONLBackend(Backend):
    """Appends one ``json.dumps`` line per event, under a lock."""

    schemes: ClassVar[tuple[str, ...]] = ("jsonl",)
    dialect: ClassVar[str | None] = None

    def __init__(self, parsed: Any, settings: Any) -> None:
        super().__init__(parsed, settings)
        if not parsed.database:
            raise BackendError("jsonl:// needs a file path, e.g. 'jsonl:///./events.jsonl'.")
        self.path = Path(parsed.database)
        self.encoding = str(parsed.option("encoding", "utf-8"))
        self._lock = threading.RLock()

    def create_schema(self) -> None:
        """A file has no schema; just make sure its directory exists."""
        parent = self.path.parent
        if str(parent) not in ("", "."):
            try:
                parent.mkdir(parents=True, exist_ok=True)
            except OSError as exc:
                raise BackendError(f"Could not create {parent} for jsonl://: {exc}") from exc

    def write(self, event: Event) -> Event:
        self.ensure_schema()
        line = json.dumps(
            self._payload(event), ensure_ascii=False, default=str, separators=(",", ":")
        )
        try:
            with self._lock, self.path.open("a", encoding=self.encoding, newline="\n") as handle:
                handle.write(line + "\n")
                handle.flush()
        except OSError as exc:
            raise BackendError(f"eventlog write to {self.path} failed: {exc}") from exc
        return event

    def _payload(self, event: Event) -> dict[str, Any]:
        """Field dict with ``created_at`` as an ISO-8601 UTC string."""
        payload = event.as_dict()
        created_at = payload.get("created_at")
        if isinstance(created_at, datetime):
            payload["created_at"] = created_at.isoformat()
        return payload
