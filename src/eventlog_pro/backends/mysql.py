"""MySQL / MariaDB backend.

``mysql://user:pw@host:3306/db``  ·  ``mariadb://…``

Needs the ``[mysql]`` extra (``PyMySQL``); ``mysqlclient`` (``MySQLdb``) is
accepted as a fallback. Connections are opened with ``autocommit=True`` and
``charset=utf8mb4``.

Query options: ``?table=``, ``?charset=`` (default ``utf8mb4``),
``?connect_timeout=`` (seconds, default 10), ``?ssl_disabled=1``,
``?unix_socket=``.
"""

from __future__ import annotations

import threading
from typing import Any, ClassVar

from ..event import Event
from ..exceptions import BackendError, ConfigurationError
from ..schema import insert_sql
from .base import Backend, ThreadLocalConnectionMixin

__all__ = ["MySQLBackend"]

#: MySQL error number for "Duplicate key name" — CREATE INDEX has no
#: IF NOT EXISTS on MySQL, so re-running the DDL must be a no-op instead.
ER_DUP_KEYNAME = 1061

_driver_lock = threading.Lock()
_driver: Any = None
_driver_name = ""


def _load_driver() -> tuple[Any, str]:
    """Import PyMySQL (then MySQLdb) on first use, or explain the missing extra."""
    global _driver, _driver_name
    with _driver_lock:
        if _driver is not None:
            return _driver, _driver_name
        for name in ("pymysql", "MySQLdb"):
            try:
                _driver = __import__(name)
            except ImportError:
                continue
            _driver_name = name
            return _driver, _driver_name
    raise ConfigurationError(
        "mysql:// requires PyMySQL. Install: pip install 'eventlog-pro[mysql]'"
    )


class MySQLBackend(ThreadLocalConnectionMixin, Backend):
    """Writes events to MySQL or MariaDB, one held-open connection per thread."""

    schemes: ClassVar[tuple[str, ...]] = ("mysql", "mariadb")
    dialect: ClassVar[str] = "mysql"
    extra: ClassVar[str] = "mysql"

    def __init__(self, parsed: Any, settings: Any) -> None:
        super().__init__(parsed, settings)
        driver, self.driver_name = _load_driver()
        self.driver = driver
        self.retryable_exceptions = (driver.OperationalError, driver.InterfaceError)

        if not parsed.database:
            raise ConfigurationError(
                "mysql:// needs a database name, e.g. 'mysql://user:pw@host/mydb'."
            )
        self.connect_kwargs = self._build_connect_kwargs(parsed)

    def _build_connect_kwargs(self, parsed: Any) -> dict[str, Any]:
        kwargs: dict[str, Any] = {
            "host": parsed.host or "localhost",
            "port": parsed.port or 3306,
            "user": parsed.username,
            "password": parsed.password,
            "database": parsed.database,
            "charset": str(parsed.option("charset", "utf8mb4")),
            "autocommit": True,
            "connect_timeout": parsed.int_option("connect_timeout", 10),
        }
        if parsed.option("unix_socket"):
            kwargs["unix_socket"] = parsed.option("unix_socket")
        if parsed.bool_option("ssl_disabled"):
            # PyMySQL spells this `ssl=None`; mysqlclient ignores it.
            kwargs["ssl_disabled"] = True
        return kwargs

    def connect(self) -> Any:
        kwargs = dict(self.connect_kwargs)
        if self.driver_name == "MySQLdb":
            # mysqlclient names the database `db` and has no ssl_disabled.
            kwargs["db"] = kwargs.pop("database")
            kwargs.pop("ssl_disabled", None)
        try:
            return self.driver.connect(**kwargs)
        except Exception as exc:
            raise BackendError(f"Could not connect to MySQL ({self.parsed}): {exc}") from exc

    def create_schema(self) -> None:
        statements = self.ddl()

        def run(connection: Any) -> None:
            with connection.cursor() as cursor:
                for statement in statements:
                    try:
                        cursor.execute(statement)
                    except Exception as exc:
                        if _is_duplicate_index(exc):
                            continue
                        raise

        self.run(run, what="schema creation")

    def write(self, event: Event) -> Event:
        self.ensure_schema()
        sql = insert_sql(self.dialect, self.table)
        values = event.values(self.dialect)

        def run(connection: Any) -> int | None:
            with connection.cursor() as cursor:
                cursor.execute(sql, values)
                last_id: int | None = cursor.lastrowid
                return last_id

        event.id = self.run(run, what="write")
        return event


def _is_duplicate_index(exc: Exception) -> bool:
    """True for "Duplicate key name", the re-run-the-DDL case."""
    args: tuple[Any, ...] = getattr(exc, "args", ())
    return bool(args) and args[0] == ER_DUP_KEYNAME
