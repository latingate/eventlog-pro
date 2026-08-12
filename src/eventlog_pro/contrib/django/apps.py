"""The ``AppConfig``.

``label`` is mandatory: without it Django derives the label from the last
component of ``name`` and every install would be called ``django``.
"""

from __future__ import annotations

import logging

from django.apps import AppConfig

logger = logging.getLogger("eventlog_pro")

__all__ = ["EventLogProConfig"]


class EventLogProConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "eventlog_pro.contrib.django"
    label = "eventlog_pro"
    verbose_name = "Event Log"

    def ready(self) -> None:
        # Registers the system checks.
        from ...config import configure, is_configured
        from . import checks  # noqa: F401
        from .conf import get_config

        # Putting the app in INSTALLED_APPS is a declaration that events go
        # through the ORM — but an explicit configure() call still wins, so a
        # project can point the package somewhere else on purpose.
        if is_configured():
            return

        config = get_config()
        alias = str(config["DATABASE_ALIAS"])
        configure(
            backend="django",
            dsn=f"django://{alias}",
            table=str(config["TABLE"]),
            auto_create_table=False,
            raise_on_error=bool(config["RAISE_ON_ERROR"]),
            default_app=str(config["DEFAULT_APP"]),
        )
        logger.debug("eventlog_pro configured for Django alias %r", alias)
