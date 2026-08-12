"""Django ORM backend — ``django://<alias>``.

``django://`` uses the ``default`` alias; ``django://replica`` uses that one.
The model, its migrations and Django's own connection handling own the schema,
so this backend never emits DDL and ``auto_create_table`` is ignored.

Deliberate asymmetry: :meth:`write` returns the **model instance**, matching
what ``EventLog.objects.create(...)`` returned in the app this replaced, which
callers may rely on. Pure mode returns the :class:`~eventlog_pro.event.Event`
dataclass. Both expose ``.id``, ``.app``, ``.event_code``, ``.data`` and
``.created_at``.
"""

from __future__ import annotations

from typing import Any, ClassVar, cast

from ..event import Event
from ..exceptions import BackendError, ConfigurationError
from .base import Backend

__all__ = ["DjangoBackend"]


class DjangoBackend(Backend):
    """Writes events through ``EventLog.objects.using(alias).create()``."""

    schemes: ClassVar[tuple[str, ...]] = ("django",)
    dialect: ClassVar[str | None] = None
    extra: ClassVar[str] = "django"

    def __init__(self, parsed: Any, settings: Any) -> None:
        super().__init__(parsed, settings)
        try:
            import django  # noqa: F401
        except ImportError as exc:
            raise ConfigurationError(
                "django:// requires Django. Install: pip install 'eventlog-pro[django]'"
            ) from exc
        self.alias = parsed.database or "default"

    def create_schema(self) -> None:
        """No-op: ``python manage.py migrate eventlog_pro`` owns the table."""

    def write(self, event: Event) -> Event:
        # Imported inside the method: importing a model at module import time
        # would blow up before django.setup() has run.
        from ..contrib.django.models import EventLog

        kwargs = event.to_orm_kwargs()
        # `created_at` is auto_now_add, so the ORM stamps it itself; passing it
        # would be ignored, and dropping it keeps the intent obvious.
        kwargs.pop("created_at", None)
        try:
            instance = EventLog.objects.using(self.alias).create(**kwargs)
        except Exception as exc:
            raise BackendError(
                f"eventlog write via Django alias {self.alias!r} failed: {exc}"
            ) from exc
        return cast(Event, instance)
