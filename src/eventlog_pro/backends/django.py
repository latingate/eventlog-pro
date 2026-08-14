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

from ..criteria import Criteria
from ..event import Event
from ..exceptions import BackendError, ConfigurationError
from ..schema import SELECT_COLUMNS, from_db_datetime
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

    def read(self, criteria: Criteria) -> list[Event]:
        """Reads return :class:`Event`, not model instances.

        The write path's asymmetry is not extended here: a caller iterating
        results should get the same type in both modes, so the ORM row is
        converted rather than handed over.
        """
        queryset = self._queryset(criteria)
        try:
            rows = list(queryset.values_list(*SELECT_COLUMNS)[: criteria.limit])
        except Exception as exc:
            raise BackendError(
                f"eventlog query via Django alias {self.alias!r} failed: {exc}"
            ) from exc
        return [self._to_event(row) for row in rows]

    def delete(self, criteria: Criteria) -> int:
        queryset = self._queryset(criteria)
        try:
            if criteria.limit is not None:
                # `.delete()` refuses to run on a sliced queryset, so the ids
                # are collected first — the same two-statement shape the SQL
                # backends use, for the same reason.
                ids = list(queryset.values_list("pk", flat=True)[: criteria.limit])
                if not ids:
                    return 0
                queryset = self._manager().filter(pk__in=ids)
            deleted, _per_model = queryset.delete()
        except Exception as exc:
            raise BackendError(
                f"eventlog delete via Django alias {self.alias!r} failed: {exc}"
            ) from exc
        return int(deleted)

    def _manager(self) -> Any:
        from ..contrib.django.models import EventLog

        return EventLog.objects.using(self.alias)

    def _queryset(self, criteria: Criteria) -> Any:
        from django.db.models import TextField
        from django.db.models.functions import Cast

        queryset = self._manager().all()

        if criteria.equals:
            queryset = queryset.filter(**dict(criteria.equals))

        for column, needle in criteria.contains:
            # `data__contains` on a JSONField means JSON *containment*, not
            # substring — and it raises NotSupportedError on SQLite. Casting to
            # text first is what makes `data=` mean the same thing here as it
            # does in pure mode.
            alias = f"_eventlog_{column}_text"
            queryset = queryset.annotate(**{alias: Cast(column, output_field=TextField())})
            queryset = queryset.filter(**{f"{alias}__contains": needle})

        if criteria.created_from is not None:
            queryset = queryset.filter(created_at__gte=criteria.created_from)
        if criteria.created_to is not None:
            lookup = "created_at__lte" if criteria.created_to_op == "<=" else "created_at__lt"
            queryset = queryset.filter(**{lookup: criteria.created_to})

        if criteria.order_by:
            queryset = queryset.order_by(
                *(
                    f"-{name}" if direction == "DESC" else name
                    for name, direction in criteria.order_by
                )
            )
        return queryset

    @staticmethod
    def _to_event(row: tuple[Any, ...]) -> Event:
        values = dict(zip(SELECT_COLUMNS, row, strict=True))
        created_at = values.pop("created_at")
        return Event(created_at=from_db_datetime(created_at, "django"), **values)
