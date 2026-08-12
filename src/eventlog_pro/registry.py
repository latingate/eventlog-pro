"""Scheme → backend class, resolved lazily by dotted path.

Nothing here imports a backend module until its scheme is actually used, which
is what keeps ``import eventlog_pro`` free of ``psycopg``, ``pymysql`` and
``django``.
"""

from __future__ import annotations

import threading
from importlib import import_module
from typing import TYPE_CHECKING

from .exceptions import ConfigurationError, UnknownSchemeError

if TYPE_CHECKING:  # pragma: no cover
    from .backends.base import Backend

__all__ = ["register_backend", "get_backend_class", "known_schemes", "unregister_backend"]

_ENTRY_POINT_GROUP = "eventlog_pro.backends"

_lock = threading.RLock()

#: Built-in schemes, as dotted ``module:attribute`` paths.
_REGISTRY: dict[str, str | type[Backend]] = {
    "sqlite": "eventlog_pro.backends.sqlite:SQLiteBackend",
    "sqlite3": "eventlog_pro.backends.sqlite:SQLiteBackend",
    "postgres": "eventlog_pro.backends.postgres:PostgresBackend",
    "postgresql": "eventlog_pro.backends.postgres:PostgresBackend",
    "mysql": "eventlog_pro.backends.mysql:MySQLBackend",
    "mariadb": "eventlog_pro.backends.mysql:MySQLBackend",
    "jsonl": "eventlog_pro.backends.jsonl:JSONLBackend",
    "memory": "eventlog_pro.backends.memory:MemoryBackend",
    "null": "eventlog_pro.backends.null:NullBackend",
    "django": "eventlog_pro.backends.django:DjangoBackend",
}

_entry_points_loaded = False


def register_backend(scheme: str, backend: str | type[Backend]) -> None:
    """Register *backend* for DSN *scheme*.

    *backend* is either a :class:`~eventlog_pro.backends.base.Backend` subclass
    or a ``"package.module:ClassName"`` string, which is imported on first use.
    Registering an already-known scheme replaces it.
    """
    scheme = _normalize(scheme)
    if not isinstance(backend, str) and not isinstance(backend, type):
        raise ConfigurationError(
            f"register_backend({scheme!r}, ...) needs a Backend subclass or a "
            f"'module:Class' string, got {type(backend).__name__}."
        )
    with _lock:
        _REGISTRY[scheme] = backend


def unregister_backend(scheme: str) -> None:
    """Remove *scheme* from the registry. Unknown schemes are ignored."""
    with _lock:
        _REGISTRY.pop(_normalize(scheme), None)


def known_schemes() -> tuple[str, ...]:
    """Every registered scheme, sorted."""
    with _lock:
        return tuple(sorted(_REGISTRY))


def get_backend_class(scheme: str) -> type[Backend]:
    """Return the backend class for *scheme*, importing it if needed.

    Falls back to ``eventlog_pro.backends`` entry points on the first miss, so
    third-party backends can be installed without a ``register_backend()`` call.
    """
    scheme = _normalize(scheme)
    with _lock:
        target = _REGISTRY.get(scheme)

    if target is None:
        _load_entry_points()
        with _lock:
            target = _REGISTRY.get(scheme)
        if target is None:
            raise UnknownSchemeError(scheme, known_schemes())

    if isinstance(target, str):
        cls = _import(scheme, target)
        with _lock:
            _REGISTRY[scheme] = cls
        return cls
    return target


def _normalize(scheme: str) -> str:
    if not isinstance(scheme, str) or not scheme.strip():
        raise ConfigurationError("Backend scheme must be a non-empty string.")
    return scheme.strip().lower().partition("+")[0].rstrip(":/")


def _import(scheme: str, target: str) -> type[Backend]:
    module_path, _, attribute = target.partition(":")
    if not attribute:
        raise ConfigurationError(
            f"Backend path for {scheme!r} must be 'module:ClassName', got {target!r}."
        )
    try:
        module = import_module(module_path)
    except ImportError as exc:  # pragma: no cover - exercised via the driver check
        raise ConfigurationError(
            f"Backend for {scheme!r} could not be imported from {module_path!r}: {exc}"
        ) from exc
    try:
        cls = getattr(module, attribute)
    except AttributeError:
        raise ConfigurationError(
            f"Module {module_path!r} has no attribute {attribute!r} for scheme {scheme!r}."
        ) from None

    from .backends.base import Backend

    if not (isinstance(cls, type) and issubclass(cls, Backend)):
        raise ConfigurationError(
            f"{target!r} is not a Backend subclass (registered for {scheme!r})."
        )
    return cls


def _load_entry_points() -> None:
    """Merge ``eventlog_pro.backends`` entry points in, once per process."""
    global _entry_points_loaded
    with _lock:
        if _entry_points_loaded:
            return
        _entry_points_loaded = True

    from importlib.metadata import entry_points

    for entry_point in entry_points(group=_ENTRY_POINT_GROUP):
        scheme = _normalize(entry_point.name)
        with _lock:
            # An explicit register_backend() call always wins over discovery.
            _REGISTRY.setdefault(scheme, f"{entry_point.module}:{entry_point.attr}")
