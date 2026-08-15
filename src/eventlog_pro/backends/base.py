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
from ..schema import (
    create_table_sql,
    delete_by_ids_sql,
    delete_sql,
    index_statements,
    select_ids_sql,
    select_sql,
    validate_table_name,
)

if TYPE_CHECKING:  # pragma: no cover
    from ..config import Settings
    from ..criteria import Criteria
    from ..dsn import ParsedDSN

__all__ = ["Backend", "ThreadLocalConnectionMixin", "SQLReadDeleteMixin"]


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

    # `read` and `delete` are hooks rather than abstract methods on purpose: a
    # custom backend registered against 0.1.x keeps importing and writing, and
    # only fails — clearly — if someone tries to read from it.

    def read(self, criteria: Criteria) -> list[Event]:
        """Every stored event matching *criteria*, in ``criteria.order_by`` order."""
        raise BackendError(f"{type(self).__name__} does not support reading events.")

    def delete(self, criteria: Criteria) -> int:
        """Remove every event matching *criteria*; return how many went."""
        raise BackendError(f"{type(self).__name__} does not support deleting events.")

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


class SQLReadDeleteMixin:
    """:meth:`~Backend.read` and :meth:`~Backend.delete` for the SQL backends.

    The three of them differ only in how a statement is executed, so they
    supply :meth:`_query` and :meth:`_modify` and inherit the rest — including
    the two-statement limited delete, which must not be reimplemented three
    times.
    """

    dialect: ClassVar[str | None] = None

    if TYPE_CHECKING:  # pragma: no cover - supplied by Backend / the mixin
        table: str

        def ensure_schema(self) -> None: ...

        def run(self, operation: Callable[[Any], Any], *, what: str = ...) -> Any: ...

    def _query(self, connection: Any, sql: str, params: tuple[Any, ...]) -> list[Any]:
        """Run *sql* and return every row.

        The DB-API idiom, which psycopg and PyMySQL both follow. SQLite
        overrides it: ``sqlite3.Cursor`` is not a context manager, and an
        in-memory database has to serialise on its shared-connection lock.
        """
        with connection.cursor() as cursor:
            cursor.execute(sql, params)
            rows: list[Any] = list(cursor.fetchall())
            return rows

    def _modify(self, connection: Any, sql: str, params: tuple[Any, ...]) -> int:
        """Run *sql* and return the number of rows it affected."""
        with connection.cursor() as cursor:
            cursor.execute(sql, params)
            return int(cursor.rowcount)

    def read(self, criteria: Criteria) -> list[Event]:
        self.ensure_schema()
        dialect = str(self.dialect)
        sql, params = select_sql(dialect, self.table, criteria)

        def run(connection: Any) -> list[Any]:
            return self._query(connection, sql, params)

        rows = self.run(run, what="query")
        return [Event.from_row(row, dialect) for row in rows]

    def delete(self, criteria: Criteria) -> int:
        self.ensure_schema()
        dialect = str(self.dialect)

        if criteria.limit is None:
            sql, params = delete_sql(dialect, self.table, criteria)

            def run_all(connection: Any) -> int:
                return self._modify(connection, sql, params)

            return int(self.run(run_all, what="delete"))

        # `DELETE ... LIMIT` is MySQL-only, so a limited delete selects the ids
        # first and deletes those. Both statements run on one connection inside
        # one `run()`, but they are still two statements: a row inserted
        # between them is not deleted. That is the right behaviour for
        # retention batching, and it is documented.
        ids_sql, ids_params = select_ids_sql(dialect, self.table, criteria)

        def run_limited(connection: Any) -> int:
            ids = tuple(row[0] for row in self._query(connection, ids_sql, ids_params))
            if not ids:
                return 0
            sql, params = delete_by_ids_sql(dialect, self.table, ids)
            return self._modify(connection, sql, params)

        return int(self.run(run_limited, what="delete"))
