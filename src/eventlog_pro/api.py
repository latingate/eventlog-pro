"""The public write API: :func:`log_event` and :func:`log_event_safe`.

The same two functions serve both modes; which store they reach is settled by
configuration, never by autodetection.
"""

from __future__ import annotations

import logging
from typing import Any

from .config import get_backend, get_settings
from .entity import resolve_entity
from .event import Event
from .schema import MAX_CHARFIELD_LENGTH

__all__ = ["log_event", "log_event_safe", "build_event"]

logger = logging.getLogger("eventlog_pro")


def build_event(
    *,
    app: str | None = None,
    category: str,
    event_code: str,
    event_type: str = "",
    sub_category: str = "",
    entity: Any = None,
    remarks: str = "",
    data: Any = None,
    created_by: str | None = None,
    entity_app: str | None = None,
    entity_model: str | None = None,
    entity_id: str | None = None,
) -> Event:
    """Build an :class:`~eventlog_pro.event.Event` without writing it.

    Useful for tests and for callers that want to inspect or enrich the row
    before handing it to a backend.
    """
    resolved_app, resolved_model, resolved_id = resolve_entity(entity)

    # Explicit kwargs bypass resolution entirely — the escape hatch for
    # pure-Python callers who have no objects to point at.
    if entity_app is not None:
        resolved_app = str(entity_app)[:MAX_CHARFIELD_LENGTH]
    if entity_model is not None:
        resolved_model = str(entity_model)[:MAX_CHARFIELD_LENGTH]
    if entity_id is not None:
        resolved_id = str(entity_id)[:MAX_CHARFIELD_LENGTH]

    if app is None:
        app = get_settings().default_app

    return Event(
        app=app,
        category=category,
        sub_category=sub_category,
        event_type=event_type,
        event_code=event_code,
        entity_app=resolved_app,
        entity_model=resolved_model,
        entity_id=resolved_id,
        remarks=remarks,
        data=data,
        created_by=created_by or "",
    )


def log_event(
    *,
    app: str | None = None,
    category: str,
    event_code: str,
    event_type: str = "",
    sub_category: str = "",
    entity: Any = None,
    remarks: str = "",
    data: Any = None,
    created_by: str | None = None,
    entity_app: str | None = None,
    entity_model: str | None = None,
    entity_id: str | None = None,
) -> Event:
    """Record one event. **Raises** if the write fails.

    Parameters
    ----------
    app : str
        Source system or app name (``"api"``, ``"accounts"``, ``"auto.pel"``).
        Arbitrary caller-chosen text, max 100 characters, dots allowed, no
        validation. Falls back to the configured ``default_app``.
    category : str
        Main grouping (``"webhook"``, ``"auth"``, ``"email"``).
    event_code : str
        Stable machine-readable code (``"SIGNATURE_MISMATCH"``).
    event_type : str
        Free text severity-ish label — ``"error"``, ``"info"``, ``"warning"``.
    sub_category : str
        Optional secondary grouping.
    entity : Any
        The thing the event is about: a Django model instance, an object
        implementing ``__eventlog_entity__()``, a dict, a 3-tuple, or a bare
        identifier. See :func:`~eventlog_pro.entity.resolve_entity`.
    remarks : str
        Human-readable note. Unbounded (``text``).
    data : dict | list | None
        Extra JSON payload; ``None`` is stored as ``{}``. Serialised with
        ``default=str``, so datetimes and other odd values never raise.
    created_by : str | None
        Who caused it — a username, an email, a process name.
    entity_app, entity_model, entity_id : str | None
        Set the entity columns directly, bypassing ``entity=`` resolution.

    Returns
    -------
    Event
        The stored event, with ``id`` set by backends that have one. In Django
        mode this is the ``EventLog`` model instance instead — both expose
        ``.id``, ``.app``, ``.event_code``, ``.data`` and ``.created_at``.

    Raises
    ------
    ConfigurationError
        Bad DSN, unknown scheme, or a missing optional driver.
    BackendError
        The store rejected or could not take the write.

    Notes
    -----
    Every ``varchar(100)`` value is silently truncated to fit rather than
    rejected. With ``configure(raise_on_error=False)`` (or ``EVENTLOG_SILENT=1``)
    this function behaves exactly like :func:`log_event_safe` and returns
    ``None`` instead of raising.
    """
    event = build_event(
        app=app,
        category=category,
        event_code=event_code,
        event_type=event_type,
        sub_category=sub_category,
        entity=entity,
        remarks=remarks,
        data=data,
        created_by=created_by,
        entity_app=entity_app,
        entity_model=entity_model,
        entity_id=entity_id,
    )
    try:
        return get_backend().write(event)
    except Exception:
        # KeyboardInterrupt / SystemExit are BaseExceptions and pass straight
        # through, in both this function and log_event_safe.
        if get_settings().raise_on_error:
            raise
        logger.exception("eventlog_pro failed to write event %s", event)
        # The documented kill-switch behaviour; the annotation describes the
        # default configuration, where this line is unreachable.
        return None  # type: ignore[return-value]


def log_event_safe(**kwargs: Any) -> Event | None:
    """:func:`log_event` that never raises — the one to call from a webhook.

    Logs the failure to the ``eventlog_pro`` stdlib logger with a traceback and
    returns ``None``. Building the event is inside the guard too, so a caller
    who passes a bad keyword still gets ``None`` rather than a ``TypeError``.
    """
    try:
        event = build_event(**kwargs)
        return get_backend().write(event)
    except Exception:
        logger.exception("eventlog_pro failed to write event (kwargs=%r)", _redact(kwargs))
        return None


def _redact(kwargs: dict[str, Any]) -> dict[str, Any]:
    """Keep the failure log readable — identity, not payload."""
    return {
        key: kwargs.get(key)
        for key in ("app", "category", "event_code", "event_type")
        if key in kwargs
    }
