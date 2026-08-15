"""DSN parsing.

One URL configures a whole deployment, so parsing is deliberately permissive
about shape and strict about nothing except the scheme being present.

Path conventions follow the SQLAlchemy precedent, which is what people already
have in their heads::

    sqlite:///./eventlog-pro.db   relative path (three slashes)
    sqlite:////var/events.db      absolute path (four slashes)
    sqlite:///C:/tmp/e.db         Windows drive letters work with three
    sqlite://:memory:             in-memory database (":memory:" also works)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from urllib.parse import parse_qsl, unquote, urlsplit

from .exceptions import ConfigurationError

__all__ = ["ParsedDSN", "parse_dsn"]

_MEMORY = ":memory:"


@dataclass(frozen=True, slots=True)
class ParsedDSN:
    """The parts of a DSN a backend needs."""

    raw: str
    scheme: str
    driver: str = ""
    username: str = ""
    password: str = ""
    host: str = ""
    port: int | None = None
    database: str = ""
    options: dict[str, str] = field(default_factory=dict)

    def option(self, name: str, default: Any = None) -> Any:
        """Query-string option lookup, e.g. ``?table=audit_events``."""
        return self.options.get(name, default)

    def bool_option(self, name: str, default: bool = False) -> bool:
        """Query-string option read as a boolean (``1/true/yes/on``)."""
        raw = self.options.get(name)
        if raw is None:
            return default
        return raw.strip().lower() in {"1", "true", "yes", "on"}

    def int_option(self, name: str, default: int | None = None) -> int | None:
        """Query-string option read as an int; a bad value is a config error."""
        raw = self.options.get(name)
        if raw is None:
            return default
        try:
            return int(raw)
        except ValueError:
            raise ConfigurationError(
                f"Option {name!r} in DSN must be an integer, got {raw!r}."
            ) from None

    def __str__(self) -> str:  # pragma: no cover - repr convenience
        return redact(self.raw)


def redact(dsn: str) -> str:
    """Mask the password in *dsn* so it is safe to log or put in a message."""
    try:
        split = urlsplit(dsn)
    except ValueError:
        return dsn
    if not split.password:
        return dsn
    return dsn.replace(f":{split.password}@", ":***@", 1)


def parse_dsn(dsn: str) -> ParsedDSN:
    """Parse *dsn* into a :class:`ParsedDSN`.

    Raises :class:`~eventlog_pro.exceptions.ConfigurationError` if the string is
    empty or carries no scheme. The scheme is lower-cased, and a
    ``scheme+driver://`` suffix (``postgresql+psycopg://``) is split off into
    :attr:`ParsedDSN.driver`.
    """
    if not isinstance(dsn, str) or not dsn.strip():
        raise ConfigurationError("DSN must be a non-empty string.")
    dsn = dsn.strip()

    try:
        split = urlsplit(dsn)
    except ValueError as exc:
        raise ConfigurationError(f"Could not parse DSN {redact(dsn)!r}: {exc}") from exc

    if not split.scheme:
        raise ConfigurationError(
            f"DSN {redact(dsn)!r} has no scheme. Expected something like "
            f"'sqlite:///./eventlog-pro.db' or 'postgresql://user:pw@host/db'."
        )

    scheme, _, driver = split.scheme.lower().partition("+")

    database = _database(split.netloc, split.path, scheme)

    port: int | None = None
    if database != _MEMORY:
        # `sqlite://:memory:` puts the marker where a port would be, so the
        # port is only meaningful once memory has been ruled out.
        try:
            port = split.port
        except ValueError:
            raise ConfigurationError(f"DSN {redact(dsn)!r} has an invalid port.") from None

    options = dict(parse_qsl(split.query, keep_blank_values=True))

    return ParsedDSN(
        raw=dsn,
        scheme=scheme,
        driver=driver,
        username=unquote(split.username or ""),
        password=unquote(split.password or ""),
        host=split.hostname or "",
        port=port,
        database=database,
        options=options,
    )


def _database(netloc: str, path: str, scheme: str) -> str:
    """Extract the database part: a file path, a DB name, or a Django alias."""
    # `sqlite://:memory:` — the memory marker lands in the netloc.
    if netloc.strip("/") == _MEMORY or path.strip("/") == _MEMORY:
        return _MEMORY

    if "@" not in netloc and ":" not in netloc and scheme in {"django", "memory", "null"}:
        # `django://other_db` — the alias is the netloc, not a host.
        return netloc or path.lstrip("/")

    if not path:
        return ""

    # urlsplit keeps the leading separator; one slash is the scheme's own, so
    # `sqlite:///x.db` is relative and `sqlite:////x.db` is absolute.
    database = path[1:] if path.startswith("/") else path

    # `sqlite:///C:/tmp/events.db` must not become `C:/tmp/...` losing nothing,
    # but `sqlite:///c:\tmp` style input keeps its drive letter either way.
    return database


def path_of(parsed: ParsedDSN) -> str:
    """The filesystem path a file-backed DSN points at (``""`` for memory)."""
    return "" if parsed.database == _MEMORY else parsed.database
