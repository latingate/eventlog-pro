"""The ``EVENTLOG_PRO`` settings dict, merged over defaults.

    EVENTLOG_PRO = {
        "TABLE": "eventlog_eventlog",
        "DATABASE_ALIAS": "default",
        "ADMIN_ENABLED": True,
        "ADMIN_READONLY": True,
        "ADMIN_SEARCH_DATA": True,
        "ADMIN_LIST_PER_PAGE": 50,
        "RAISE_ON_ERROR": True,
        "DEFAULT_APP": "",
    }

Unknown keys raise ``ImproperlyConfigured``: a typo'd setting that silently
does nothing is a support ticket waiting to happen.
"""

from __future__ import annotations

from typing import Any

from django.core.exceptions import ImproperlyConfigured

from ...schema import DEFAULT_TABLE

__all__ = ["DEFAULTS", "get_config", "table_name", "database_alias"]

SETTING_NAME = "EVENTLOG_PRO"

#: Rendering for ``pretty_event_type``, keyed by the lower-cased event type.
#: Types that are known but unstyled render as plain upper-case text; anything
#: unknown renders in its original casing (a quirk preserved from the source
#: app — see the CHANGELOG).
DEFAULT_EVENT_TYPE_STYLES: dict[str, str] = {
    "error": "color: red; font-weight: bold;",
    "success": "color: green; font-weight: bold;",
    "warning": "",
    "info": "",
    "notification": "",
    "debug": "",
}

DEFAULTS: dict[str, Any] = {
    "TABLE": DEFAULT_TABLE,
    "DATABASE_ALIAS": "default",
    "ADMIN_ENABLED": True,
    "ADMIN_READONLY": True,
    "ADMIN_SEARCH_DATA": True,
    "ADMIN_LIST_PER_PAGE": 50,
    "RAISE_ON_ERROR": True,
    "DEFAULT_APP": "",
    "EVENT_TYPE_STYLES": DEFAULT_EVENT_TYPE_STYLES,
}


def get_config() -> dict[str, Any]:
    """The merged configuration.

    Read fresh every call, so ``override_settings`` works in tests — except for
    ``TABLE``, which the model's ``Meta.db_table`` reads once at import time.
    """
    from django.conf import settings

    overrides = getattr(settings, SETTING_NAME, None) or {}
    if not isinstance(overrides, dict):
        raise ImproperlyConfigured(
            f"{SETTING_NAME} must be a dict, got {type(overrides).__name__}."
        )

    unknown = sorted(set(overrides) - set(DEFAULTS))
    if unknown:
        raise ImproperlyConfigured(
            f"Unknown {SETTING_NAME} key(s): {', '.join(unknown)}. "
            f"Valid keys: {', '.join(sorted(DEFAULTS))}."
        )

    config = dict(DEFAULTS)
    config.update(overrides)
    return config


def table_name() -> str:
    """The physical table name, validated."""
    from ...schema import validate_table_name

    return validate_table_name(str(get_config()["TABLE"]))


def database_alias() -> str:
    """The ``DATABASES`` alias the model and backend read and write."""
    return str(get_config()["DATABASE_ALIAS"])
