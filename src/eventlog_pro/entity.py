"""Turn whatever the caller passed as ``entity=`` into three strings.

Eight branches, tried in order, ending in a fallback that always produces
something. **This function never raises**: a broken ``__eventlog_entity__`` or
an exploding ``__getattr__`` degrades to ``("", "", "")`` rather than taking
down the call site that was only trying to log.
"""

from __future__ import annotations

import logging
from typing import Any

from .schema import MAX_CHARFIELD_LENGTH

__all__ = ["resolve_entity"]

logger = logging.getLogger("eventlog_pro")

EMPTY = ("", "", "")

_DICT_KEYS = (
    ("entity_app", "entity_model", "entity_id"),
    ("app", "model", "id"),
)

_ID_ATTRIBUTES = ("pk", "id", "uuid", "slug")


def resolve_entity(entity: Any) -> tuple[str, str, str]:
    """Resolve *entity* to ``(entity_app, entity_model, entity_id)``."""
    try:
        return _resolve(entity)
    except Exception:
        logger.debug("eventlog could not resolve entity %r", type(entity), exc_info=True)
        return EMPTY


def _resolve(entity: Any) -> tuple[str, str, str]:
    # 1. Nothing to resolve.
    if entity is None:
        return EMPTY

    # 2. The documented extension point.
    hook = getattr(entity, "__eventlog_entity__", None)
    if callable(hook):
        resolved = _from_hook(hook())
        if resolved is not None:
            return resolved

    # 3. Duck-typed Django model instance — same three lines as the source
    #    app's eventlog_utilities.py:100-103, with no Django import.
    meta = getattr(entity, "_meta", None)
    if meta is not None and hasattr(meta, "app_label") and hasattr(meta, "model_name"):
        pk = getattr(entity, "pk", None)
        return _clean(meta.app_label, meta.model_name, "" if pk is None else pk)

    # 4. Mapping with either key set.
    if isinstance(entity, dict):
        for app_key, model_key, id_key in _DICT_KEYS:
            if app_key in entity or model_key in entity or id_key in entity:
                return _clean(
                    entity.get(app_key, ""),
                    entity.get(model_key, ""),
                    entity.get(id_key, ""),
                )
        return EMPTY

    # 5. Positional triple.
    if isinstance(entity, (tuple, list)):
        if len(entity) == 3:
            return _clean(*entity)
        return EMPTY

    # 6. Scalars — `entity="INV-1234"` just works.
    if isinstance(entity, (str, bytes, int, float, bool)):
        value = entity.decode("utf-8", "replace") if isinstance(entity, bytes) else entity
        return _clean("", "", value)

    # 7. Generic object: top-level module as the app, class name as the model.
    app = type(entity).__module__.split(".")[0]
    model = type(entity).__name__.lower()
    identifier: Any = ""
    for name in _ID_ATTRIBUTES:
        candidate = getattr(entity, name, None)
        if candidate is not None:
            identifier = candidate
            break
    return _clean(app, model, identifier)


def _from_hook(result: Any) -> tuple[str, str, str] | None:
    """Interpret ``__eventlog_entity__()``: a 3-tuple or a mapping."""
    if isinstance(result, dict):
        for app_key, model_key, id_key in _DICT_KEYS:
            if app_key in result or model_key in result or id_key in result:
                return _clean(
                    result.get(app_key, ""),
                    result.get(model_key, ""),
                    result.get(id_key, ""),
                )
        return EMPTY
    if isinstance(result, (tuple, list)) and len(result) == 3:
        return _clean(*result)
    return None


def _clean(app: Any, model: Any, identifier: Any) -> tuple[str, str, str]:
    """Stringify and truncate to the column width."""
    return (
        _text(app),
        _text(model),
        _text(identifier),
    )


def _text(value: Any) -> str:
    if value is None:
        return ""
    text = value if isinstance(value, str) else str(value)
    return text[:MAX_CHARFIELD_LENGTH]
