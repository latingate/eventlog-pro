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

from ..criteria import Criteria, sort_events
from ..event import Event
from ..exceptions import BackendError
from ..schema import SELECT_COLUMNS, from_db_datetime
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

    def read(self, criteria: Criteria) -> list[Event]:
        """Scan the file, one JSON object per line.

        There is no index and no query language, so this is a full read of the
        file every time, filtered in Python with the same :class:`Criteria` the
        SQL backends translate. Unparsable lines are skipped rather than
        raised on — a half-written last line should not make the whole log
        unreadable.
        """
        events: list[Event] = []
        try:
            with self._lock, self.path.open("r", encoding=self.encoding) as handle:
                for line in handle:
                    event = self._parse(line)
                    if event is not None and criteria.matches(event):
                        events.append(event)
        except FileNotFoundError:
            return []
        except OSError as exc:
            raise BackendError(f"eventlog query of {self.path} failed: {exc}") from exc
        ordered = sort_events(events, criteria.order_by)
        return ordered if criteria.limit is None else ordered[: criteria.limit]

    def delete(self, criteria: Criteria) -> int:
        """Not supported.

        Deleting would mean rewriting the whole file, and an interrupted
        rewrite truncates a log that exists to be shipped somewhere else.
        Rotate the file, or send it to a store that can delete.
        """
        raise BackendError(
            "jsonl:// does not support deleting events: the file is append-only. "
            "Rotate it instead, or use a SQL backend."
        )

    def _parse(self, line: str) -> Event | None:
        line = line.strip()
        if not line:
            return None
        try:
            payload = json.loads(line)
        except ValueError:
            return None
        if not isinstance(payload, dict):
            return None
        created_at = payload.get("created_at")
        fields: dict[str, Any] = {
            name: payload.get(name) for name in SELECT_COLUMNS if name != "created_at"
        }
        if created_at is not None:
            fields["created_at"] = from_db_datetime(created_at, "jsonl")
        return Event(**fields)

    def _payload(self, event: Event) -> dict[str, Any]:
        """Field dict with ``created_at`` as an ISO-8601 UTC string."""
        payload = event.as_dict()
        created_at = payload.get("created_at")
        if isinstance(created_at, datetime):
            payload["created_at"] = created_at.isoformat()
        return payload
