"""Django system checks.

Configuration mistakes that would otherwise show up as a confusing runtime
error — or as events written to a table nobody is reading.
"""

from __future__ import annotations

from typing import Any

from django.core.checks import Error, register
from django.core.checks import Warning as CheckWarning

__all__ = ["check_eventlog_pro"]


@register()
def check_eventlog_pro(app_configs: Any = None, **kwargs: Any) -> list[Any]:
    """Validate ``EVENTLOG_PRO`` against the migration state and ``DATABASES``."""
    from django.conf import settings as django_settings

    from ...config import get_settings
    from .conf import get_config

    problems: list[Any] = []

    try:
        config = get_config()
    except Exception as exc:  # ImproperlyConfigured from an unknown key or bad type
        return [
            Error(
                str(exc),
                hint="Fix the EVENTLOG_PRO setting in your settings module.",
                id="eventlog_pro.E003",
            )
        ]

    alias = str(config["DATABASE_ALIAS"])
    if alias not in django_settings.DATABASES:
        problems.append(
            Error(
                f"EVENTLOG_PRO['DATABASE_ALIAS'] = {alias!r} is not in settings.DATABASES.",
                hint=f"Known aliases: {', '.join(sorted(django_settings.DATABASES))}.",
                id="eventlog_pro.E001",
            )
        )

    configured_table = str(config["TABLE"])
    model_table = _model_table()
    if model_table is not None and configured_table != model_table:
        problems.append(
            CheckWarning(
                f"EVENTLOG_PRO['TABLE'] = {configured_table!r} but the model and its "
                f"migrations were built against {model_table!r}.",
                hint=(
                    "Meta.db_table and the migration both read TABLE at import time, so "
                    "changing it later neither moves the table nor generates a rename. "
                    "Set TABLE before Django loads the app, or rename the table by hand."
                ),
                id="eventlog_pro.W001",
            )
        )

    core_table = get_settings().table
    if core_table != configured_table:
        problems.append(
            CheckWarning(
                f"eventlog_pro.configure(table={core_table!r}) disagrees with "
                f"EVENTLOG_PRO['TABLE'] = {configured_table!r}.",
                hint=(
                    "In Django mode the model's db_table wins, so events land in "
                    f"{configured_table!r} regardless. Drop one of the two settings."
                ),
                id="eventlog_pro.W002",
            )
        )

    return problems


def _model_table() -> str | None:
    """The ``db_table`` frozen into the model — and therefore the migration."""
    try:
        from .models import EventLog

        return str(EventLog._meta.db_table)
    except Exception:  # pragma: no cover - the app is loaded by the time checks run
        return None
