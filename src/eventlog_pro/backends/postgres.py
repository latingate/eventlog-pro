"""PostgreSQL backend.

``postgresql://user:pw@host:5432/db``  ·  ``postgres://…``  ·
``postgresql+psycopg://…``

Needs the ``[postgres]`` extra (``psycopg`` 3). ``psycopg2`` is accepted as a
fallback for deployments that already have it, since both speak DB-API 2.0 and
libpq URLs.

Query options: ``?table=`` (consumed here), plus any libpq parameter —
``?connect_timeout=5``, ``?sslmode=require``, ``?application_name=…`` — which is
passed through to the driver untouched.
"""

from __future__ import annotations

import threading
from datetime import timezone
from typing import Any, ClassVar
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from ..event import Event
from ..exceptions import BackendError, ConfigurationError
from ..schema import insert_sql
from .base import Backend, SQLReadDeleteMixin, ThreadLocalConnectionMixin

__all__ = ["PostgresBackend"]

#: DSN options this package owns; everything else belongs to libpq.
_OWN_OPTIONS = frozenset({"table"})

_driver_lock = threading.Lock()
_driver: Any = None
_driver_name = ""


def _load_driver() -> tuple[Any, str]:
    """Import psycopg (3, then 2) on first use, or explain the missing extra."""
    global _driver, _driver_name
    with _driver_lock:
        if _driver is not None:
            return _driver, _driver_name
        for name in ("psycopg", "psycopg2"):
            try:
                _driver = __import__(name)
            except ImportError:
                continue
            _driver_name = name
            return _driver, _driver_name
    raise ConfigurationError(
        "postgresql:// requires psycopg. Install: pip install 'eventlog-pro[postgres]'"
    )


class PostgresBackend(SQLReadDeleteMixin, ThreadLocalConnectionMixin, Backend):
    """Writes events to PostgreSQL, one held-open connection per thread."""

    schemes: ClassVar[tuple[str, ...]] = ("postgres", "postgresql")
    dialect: ClassVar[str] = "postgresql"
    extra: ClassVar[str] = "postgres"

    def __init__(self, parsed: Any, settings: Any) -> None:
        super().__init__(parsed, settings)
        driver, self.driver_name = _load_driver()
        self.driver = driver
        # A stale connection must be retried; a syntax error must not.
        self.retryable_exceptions = (driver.OperationalError, driver.InterfaceError)
        self.conninfo = _conninfo(parsed.raw)

    def connect(self) -> Any:
        try:
            connection = self.driver.connect(self.conninfo)
        except Exception as exc:
            raise BackendError(f"Could not connect to PostgreSQL ({self.parsed}): {exc}") from exc
        # Autocommit: one event is one statement, and holding a transaction
        # open across a webhook's lifetime is how you pin a replication slot.
        try:
            connection.autocommit = True
        except AttributeError:  # pragma: no cover - psycopg2 <2.5
            connection.set_session(autocommit=True)
        return connection

    def create_schema(self) -> None:
        statements = self.ddl()

        def run(connection: Any) -> None:
            with connection.cursor() as cursor:
                for statement in statements:
                    cursor.execute(statement)

        self.run(run, what="schema creation")

    def write(self, event: Event) -> Event:
        self.ensure_schema()
        sql = insert_sql(self.dialect, self.table)
        values = event.values(self.dialect)

        def run(connection: Any) -> tuple[Any, ...] | None:
            with connection.cursor() as cursor:
                cursor.execute(sql, values)
                row: tuple[Any, ...] | None = cursor.fetchone()
                return row

        row = self.run(run, what="write")
        if row:
            event.id = row[0]
            if len(row) > 1 and row[1] is not None:
                stored = row[1]
                event.created_at = (
                    stored.astimezone(timezone.utc)
                    if stored.tzinfo is not None
                    else stored.replace(tzinfo=timezone.utc)
                )
        return event


def _conninfo(dsn: str) -> str:
    """Strip this package's own query options; libpq rejects what it can't parse.

    Also normalises ``postgres://`` and ``postgresql+psycopg://`` to plain
    ``postgresql://``.
    """
    split = urlsplit(dsn)
    scheme = split.scheme.lower().partition("+")[0]
    scheme = "postgresql" if scheme in ("postgres", "postgresql") else scheme

    kept = [
        (key, value)
        for key, value in parse_qsl(split.query, keep_blank_values=True)
        if key not in _OWN_OPTIONS
    ]
    return urlunsplit((scheme, split.netloc, split.path, urlencode(kept), split.fragment))
