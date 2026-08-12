"""The :class:`Backend` ABC and the connection handling every SQL backend shares.

An ABC rather than a Protocol, because subclasses inherit real behaviour:
thread-local connections, retry-once-on-stale-connection, and an
:meth:`~Backend.ensure_schema` driven by :func:`eventlog_pro.schema.ddl_for`.

**Connection model.** One connection per thread, opened lazily and held open.
``sqlite3.Connection`` is not thread-safe, and connect-per-write costs a
TCP+TLS+auth round trip per log line on a webhook path that emits five to ten
events per request. There is deliberately **no pooling**: point the DSN at
pgbouncer, or use ``django://`` and let Django's ``CONN_MAX_AGE`` own it.
"""

from __future__ import annotations

import abc
import contextlib
import threading
from collections.abc import Callable
from typing import TYPE_CHECKING, Any, ClassVar

from ..event import Event
from ..exceptions import BackendError
from ..schema import create_table_sql, index_statements, validate_table_name

if TYPE_CHECKING:  # pragma: no cover
    from ..config import Settings
    from ..dsn import ParsedDSN

__all__ = ["Backend", "ThreadLocalConnectionMixin"]


class Backend(abc.ABC):
    """Writes :class:`~eventlog_pro.event.Event` rows somewhere."""

    #: DSN schemes this backend answers to (informational; the registry maps).
    schemes: ClassVar[tuple[str, ...]] = ()
    #: SQL dialect for :mod:`eventlog_pro.schema`, or ``None`` if not SQL.
    dialect: ClassVar[str | None] = None
    #: Name of the extra to install, used in the "driver missing" message.
    extra: ClassVar[str] = ""

    def __init__(self, parsed: ParsedDSN, settings: Settings) -> None:
        self.parsed = parsed
        self.settings = settings
        # `?table=` in the DSN beats Settings.table, so one env var can
        # configure a whole deployment.
        self.table = validate_table_name(str(parsed.option("table") or settings.table))
        self._schema_ready = False

    @abc.abstractmethod
    def write(self, event: Event) -> Event:
        """Persist *event*, set its ``id`` where the store has one, return it."""

    def ensure_schema(self) -> None:
        """Create the table and indexes once per process, if enabled."""
        if self._schema_ready or not self.settings.auto_create_table:
            return
        self.create_schema()
        self._schema_ready = True

    def create_schema(self) -> None:  # noqa: B027 - optional hook, not abstract
        """Actually run the DDL. Overridden by non-SQL backends to do nothing."""

    def ddl(self) -> tuple[str, ...]:
        """The DDL statements for this backend's dialect and table."""
        if self.dialect is None:  # pragma: no cover - guarded by callers
            return ()
        return (
            create_table_sql(self.dialect, self.table),
            *index_statements(self.dialect, self.table),
        )

    def close(self) -> None:  # noqa: B027 - optional hook, not abstract
        """Release any resources. Must be safe to call more than once."""

    def __repr__(self) -> str:
        return f"<{type(self).__name__} table={self.table!r} dsn={self.parsed}>"


class ThreadLocalConnectionMixin:
    """One lazily-created connection per thread, plus retry-once semantics."""

    #: Driver exceptions that mean "the connection died", not "the query is
    #: bad". Set per instance by backends whose driver is imported lazily.
    retryable_exceptions: tuple[type[BaseException], ...] = ()

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._local = threading.local()
        self._connections: list[Any] = []
        self._connections_lock = threading.RLock()

    def connect(self) -> Any:
        """Open a new driver connection. Implemented by each backend."""
        raise NotImplementedError

    @property
    def connection(self) -> Any:
        """This thread's connection, opening one if it has none."""
        connection = getattr(self._local, "connection", None)
        if connection is None:
            connection = self.connect()
            self._local.connection = connection
            with self._connections_lock:
                # `is`-comparison: a backend may hand the same shared
                # connection to every thread (in-memory SQLite does).
                if not any(existing is connection for existing in self._connections):
                    self._connections.append(connection)
        return connection

    def discard_connection(self) -> None:
        """Drop this thread's connection so the next use reconnects."""
        connection = getattr(self._local, "connection", None)
        self._local.connection = None
        if connection is None:
            return
        with self._connections_lock:
            self._connections = [
                existing for existing in self._connections if existing is not connection
            ]
        with contextlib.suppress(Exception):
            connection.close()

    def run(self, operation: Callable[[Any], Any], *, what: str = "operation") -> Any:
        """Run *operation* against this thread's connection.

        A dead connection (``OperationalError``/``InterfaceError``) is detected
        here and retried exactly once after reconnecting. Anything else — and
        any second failure — is wrapped in
        :class:`~eventlog_pro.exceptions.BackendError` with the driver
        exception preserved as ``__cause__``.
        """
        try:
            return operation(self.connection)
        except self.retryable_exceptions as exc:
            first = exc
            self.discard_connection()
            try:
                return operation(self.connection)
            except Exception as retry_exc:
                raise BackendError(
                    f"eventlog {what} failed after reconnecting (first error: {first})"
                ) from retry_exc
        except BackendError:
            raise
        except Exception as exc:
            raise BackendError(f"eventlog {what} failed: {exc}") from exc

    def close(self) -> None:
        """Close every connection this backend opened, in any thread."""
        with self._connections_lock:
            connections, self._connections = self._connections, []
        self._local = threading.local()
        for connection in connections:
            with contextlib.suppress(Exception):
                connection.close()
