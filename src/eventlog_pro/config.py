"""Settings, and the process-wide backend they resolve to.

Precedence: explicit :func:`configure` keywords → environment variables →
defaults. Nothing connects at import time; the first :func:`get_backend` call
materialises the settings, resolves the backend class from the DSN scheme, and
runs ``CREATE TABLE IF NOT EXISTS`` once.
"""

from __future__ import annotations

import logging
import os
import threading
from dataclasses import dataclass, fields, replace
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .dsn import ParsedDSN, parse_dsn, redact
from .exceptions import ConfigurationError
from .registry import get_backend_class
from .schema import DEFAULT_TABLE, validate_table_name

if TYPE_CHECKING:  # pragma: no cover
    from .backends.base import Backend

__all__ = ["Settings", "configure", "get_settings", "get_backend", "reset", "is_configured"]

logger = logging.getLogger("eventlog_pro")

DEFAULT_DSN = "sqlite:///./eventlog-pro.db"

#: The default filename before 0.2.0. Only used to warn a user upgrading into
#: the rename that their old file is still there — see ``_warn_default_dsn``.
LEGACY_DEFAULT_FILENAME = "events.db"

#: Setting name → environment variable.
ENV_VARS: dict[str, str] = {
    "dsn": "EVENTLOG_DSN",
    "table": "EVENTLOG_TABLE",
    "backend": "EVENTLOG_BACKEND",
    "auto_create_table": "EVENTLOG_AUTO_CREATE_TABLE",
    "default_app": "EVENTLOG_DEFAULT_APP",
    # Inverted: EVENTLOG_SILENT=1 means raise_on_error=False.
    "raise_on_error": "EVENTLOG_SILENT",
}


@dataclass(frozen=True, slots=True)
class Settings:
    """Immutable configuration snapshot."""

    dsn: str = DEFAULT_DSN
    table: str = DEFAULT_TABLE
    raise_on_error: bool = True
    auto_create_table: bool = True
    #: Force a backend regardless of the DSN scheme, e.g. ``"django"``.
    backend: str | None = None
    #: Fallback for ``log_event(app=...)`` when the caller passes none.
    default_app: str = ""
    #: Where ``dsn`` came from — ``"explicit"``, ``"env"`` or ``"default"``.
    #: Internal; used only to decide whether to warn about a stray SQLite file.
    dsn_source: str = "default"

    def __post_init__(self) -> None:
        validate_table_name(self.table)


_lock = threading.RLock()
_settings: Settings | None = None
_backend: Backend | None = None
_warned_default_dsn = False

_SETTING_NAMES = frozenset(f.name for f in fields(Settings)) - {"dsn_source"}


def configure(**kwargs: Any) -> Settings:
    """Set configuration explicitly. Returns the resulting :class:`Settings`.

    Any live backend is closed and discarded, so re-configuring mid-process (or
    between tests) is safe. Unknown keywords raise
    :class:`~eventlog_pro.exceptions.ConfigurationError` rather than being
    silently ignored.
    """
    unknown = sorted(set(kwargs) - _SETTING_NAMES)
    if unknown:
        raise ConfigurationError(
            f"Unknown setting(s): {', '.join(unknown)}. "
            f"Valid settings: {', '.join(sorted(_SETTING_NAMES))}."
        )

    base = _from_env()
    if "dsn" in kwargs and kwargs["dsn"] is not None:
        kwargs["dsn_source"] = "explicit"
    if "table" in kwargs and kwargs["table"] is not None:
        kwargs["table"] = validate_table_name(str(kwargs["table"]))

    settings = replace(base, **{k: v for k, v in kwargs.items() if v is not None})

    with _lock:
        _close_backend()
        global _settings
        _settings = settings
    return settings


def get_settings() -> Settings:
    """The current settings, materialising them from the environment if needed."""
    global _settings
    with _lock:
        if _settings is None:
            _settings = _from_env()
        return _settings


def is_configured() -> bool:
    """Whether settings have been materialised yet.

    ``AppConfig.ready()`` uses this to avoid overriding an explicit
    ``configure()`` call made earlier in ``settings.py``.
    """
    with _lock:
        return _settings is not None


def reset() -> None:
    """Close any live backend and forget all configuration.

    The teardown counterpart to :func:`configure`; call it from test fixtures.
    """
    global _settings, _warned_default_dsn
    with _lock:
        _close_backend()
        _settings = None
        _warned_default_dsn = False


def get_backend() -> Backend:
    """The live backend, created (and its schema ensured) on first use."""
    global _backend
    with _lock:
        if _backend is not None:
            return _backend

        settings = get_settings()
        parsed = _parsed_dsn(settings)
        # Sampled before anything opens the file and reported after: only that
        # order knows whether the warning should say "created" or "reusing".
        target = _default_dsn_target(settings, parsed)
        existed = target.exists() if target is not None else False

        backend_class = get_backend_class(settings.backend or parsed.scheme)
        backend = backend_class(parsed, settings)
        try:
            backend.ensure_schema()
        except Exception:
            backend.close()
            raise
        if target is not None:
            _warn_default_dsn(settings, target, existed=existed)
        _backend = backend
        return backend


def _close_backend() -> None:
    global _backend
    backend, _backend = _backend, None
    if backend is None:
        return
    try:
        backend.close()
    except Exception:  # pragma: no cover - closing must never mask the caller's work
        logger.warning("Error closing eventlog backend", exc_info=True)


def _parsed_dsn(settings: Settings) -> ParsedDSN:
    """Parse the configured DSN, honouring an explicit ``backend`` override.

    ``configure(backend="django")`` with no matching DSN is a complete
    configuration on its own, so a mismatched scheme is replaced rather than
    fought with.
    """
    parsed = parse_dsn(settings.dsn)
    forced = settings.backend
    if forced and forced.lower() != parsed.scheme:
        parsed = parse_dsn(f"{forced.lower()}://")
    return parsed


def _default_dsn_target(settings: Settings, parsed: ParsedDSN) -> Path | None:
    """The SQLite file the unconfigured fallback will use, or ``None``.

    ``None`` means there is nothing to warn about — the DSN was chosen by the
    caller, a backend override is in force, or the warning already fired — so a
    configured path never pays for the ``exists()`` check in
    :func:`get_backend`.
    """
    if _warned_default_dsn or settings.dsn_source != "default" or settings.backend:
        return None
    # The fallback filename comes from DEFAULT_DSN rather than a literal, so the
    # file named here is always the file the backend goes on to open.
    return Path(parsed.database or parse_dsn(DEFAULT_DSN).database or "").resolve()


def _warn_default_dsn(settings: Settings, target: Path, *, existed: bool) -> None:
    """Warn once about a SQLite file nobody asked for.

    Called only once the schema attempt has succeeded, so the warning never
    announces a file that failed to open. *existed* was sampled before anything
    touched the path; together with ``target.exists()`` now it says whether the
    file was created, was already there, or is still deferred to the first
    write — the last being what ``auto_create_table=False`` means.
    """
    global _warned_default_dsn
    _warned_default_dsn = True

    if existed:
        outcome = "is using the existing %s"
    elif target.exists():
        outcome = "created %s"
    else:
        outcome = "will create %s"

    logger.warning(
        "eventlog_pro is not configured; falling back to %s, which "
        + outcome
        + ". Set EVENTLOG_DSN or call eventlog_pro.configure(dsn=...) to choose "
        "a destination.",
        redact(settings.dsn),
        target,
    )

    # Upgrading into the 0.2.0 rename: the previous default is sitting in the
    # same directory and would otherwise be silently abandoned.
    legacy = target.with_name(LEGACY_DEFAULT_FILENAME)
    if legacy != target and legacy.exists():
        logger.warning(
            "eventlog_pro found %s, the default before 0.2.0. It is untouched, "
            "and new events go to %s instead. To keep using the old file, set "
            "EVENTLOG_DSN=sqlite:///./%s or call "
            "eventlog_pro.configure(dsn='sqlite:///./%s').",
            legacy,
            target.name,
            LEGACY_DEFAULT_FILENAME,
            LEGACY_DEFAULT_FILENAME,
        )


def _from_env() -> Settings:
    """Build settings from environment variables over the defaults."""
    values: dict[str, Any] = {}

    dsn = os.environ.get(ENV_VARS["dsn"], "").strip()
    if dsn:
        values["dsn"] = dsn
        values["dsn_source"] = "env"

    table = os.environ.get(ENV_VARS["table"], "").strip()
    if table:
        values["table"] = validate_table_name(table)

    backend = os.environ.get(ENV_VARS["backend"], "").strip()
    if backend:
        values["backend"] = backend.lower()

    auto_create = _env_bool(ENV_VARS["auto_create_table"])
    if auto_create is not None:
        values["auto_create_table"] = auto_create

    silent = _env_bool(ENV_VARS["raise_on_error"])
    if silent is not None:
        values["raise_on_error"] = not silent

    default_app = os.environ.get(ENV_VARS["default_app"], "").strip()
    if default_app:
        values["default_app"] = default_app

    return Settings(**values)


def _env_bool(name: str) -> bool | None:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return None
    value = raw.strip().lower()
    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"0", "false", "no", "off"}:
        return False
    raise ConfigurationError(
        f"Environment variable {name}={raw!r} is not a boolean "
        f"(use 1/0, true/false, yes/no, on/off)."
    )
