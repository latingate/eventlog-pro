"""SQLite backend — stdlib only, the default destination.

``sqlite:///./events.db``  ·  ``sqlite:////var/log/events.db``  ·
``sqlite://:memory:``

Query options: ``?table=``, ``?timeout=`` (seconds, default 5),
``?journal_mode=`` (default ``WAL`` for file databases).
"""

from __future__ import annotations

import contextlib
import sqlite3
import threading
from pathlib import Path
from typing import Any, ClassVar

from ..event import Event
from ..exceptions import BackendError
from ..schema import insert_sql
from .base import Backend, ThreadLocalConnectionMixin

__all__ = ["SQLiteBackend"]

MEMORY = ":memory:"


class SQLiteBackend(ThreadLocalConnectionMixin, Backend):
    """Writes events to a SQLite file, or to a shared in-memory database."""

    schemes: ClassVar[tuple[str, ...]] = ("sqlite", "sqlite3")
    dialect: ClassVar[str] = "sqlite"
    retryable_exceptions: tuple[type[BaseException], ...] = (
        sqlite3.OperationalError,
        sqlite3.InterfaceError,
        sqlite3.ProgrammingError,
    )

    def __init__(self, parsed: Any, settings: Any) -> None:
        super().__init__(parsed, settings)
        self.is_memory = parsed.database in ("", MEMORY)
        self.path = "" if self.is_memory else str(Path(parsed.database))
        self.timeout = float(parsed.option("timeout", 5) or 5)
        self.journal_mode = str(parsed.option("journal_mode", "WAL"))
        # An in-memory database lives in exactly one connection, so every
        # thread must share it — and therefore serialise on a lock.
        self._shared: sqlite3.Connection | None = None
        self._shared_lock = threading.RLock()

    def connect(self) -> sqlite3.Connection:
        if self.is_memory:
            with self._shared_lock:
                if self._shared is None:
                    self._shared = self._connect(MEMORY, check_same_thread=False)
                return self._shared

        parent = Path(self.path).parent
        if str(parent) not in ("", "."):
            parent.mkdir(parents=True, exist_ok=True)
        connection = self._connect(self.path)
        if self.journal_mode:
            # A read-only directory or a network filesystem can refuse WAL; the
            # default journal still works, so this is not fatal.
            with contextlib.suppress(sqlite3.Error):
                connection.execute(f"PRAGMA journal_mode={self.journal_mode}")
        return connection

    def _connect(self, database: str, *, check_same_thread: bool = True) -> sqlite3.Connection:
        try:
            return sqlite3.connect(
                database,
                timeout=self.timeout,
                check_same_thread=check_same_thread,
            )
        except sqlite3.Error as exc:
            raise BackendError(f"Could not open SQLite database {database!r}: {exc}") from exc

    def create_schema(self) -> None:
        def run(connection: sqlite3.Connection) -> None:
            with self._maybe_shared():
                for statement in self.ddl():
                    connection.execute(statement)
                connection.commit()

        self.run(run, what="schema creation")

    def write(self, event: Event) -> Event:
        self.ensure_schema()
        sql = insert_sql(self.dialect, self.table)
        values = event.values(self.dialect)

        def run(connection: sqlite3.Connection) -> int | None:
            with self._maybe_shared():
                cursor = connection.execute(sql, values)
                connection.commit()
                return cursor.lastrowid

        event.id = self.run(run, what="write")
        return event

    def _maybe_shared(self) -> Any:
        """Serialise access when every thread shares one in-memory connection."""
        return self._shared_lock if self.is_memory else _NO_LOCK

    def discard_connection(self) -> None:
        # Reconnecting to `:memory:` would silently discard every stored row,
        # so a shared in-memory connection is never thrown away.
        if self.is_memory:
            return
        super().discard_connection()

    def close(self) -> None:
        with self._shared_lock:
            self._shared = None
        super().close()


class _NullLock:
    """A do-nothing context manager, so the write path has no branch in it."""

    def __enter__(self) -> None:
        return None

    def __exit__(self, *exc_info: object) -> None:
        return None


_NO_LOCK = _NullLock()
