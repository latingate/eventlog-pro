"""The :class:`Event` record — the 12 stored columns plus ``id``."""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass, field, fields
from datetime import datetime, timezone
from typing import Any

from .schema import (
    CHAR_COLUMNS,
    COLUMNS,
    MAX_CHARFIELD_LENGTH,
    SELECT_COLUMNS,
    from_db_data,
    from_db_datetime,
    to_db_datetime,
)

__all__ = ["Event"]


def _utcnow() -> datetime:
    """Always tz-aware. Never ``utcnow()``."""
    return datetime.now(timezone.utc)


@dataclass(slots=True)
class Event:
    """One event row.

    Mirrors ``eventlog_pro.contrib.django.models.EventLog`` field for field, so
    the same row can be written by either mode.

    Normalisation happens in ``__post_init__`` and is deliberately forgiving:
    over-long ``varchar(100)`` values are silently truncated and ``data=None``
    becomes ``{}``. Callers log free text from webhook payloads; a ``DataError``
    at 101 characters would be a worse outcome than a shortened value.
    """

    id: int | None = None
    created_at: datetime = field(default_factory=_utcnow)
    created_by: str = ""
    app: str = ""
    category: str = ""
    sub_category: str = ""
    event_code: str = ""
    event_type: str = ""
    entity_app: str = ""
    entity_model: str = ""
    entity_id: str = ""
    remarks: str = ""
    data: Any = None

    def __post_init__(self) -> None:
        if self.created_at is None:
            self.created_at = _utcnow()
        elif self.created_at.tzinfo is None:
            self.created_at = self.created_at.replace(tzinfo=timezone.utc)

        for name in CHAR_COLUMNS:
            value = getattr(self, name)
            if value is None:
                setattr(self, name, "")
                continue
            if not isinstance(value, str):
                value = str(value)
            setattr(self, name, value[:MAX_CHARFIELD_LENGTH])

        if self.remarks is None:
            self.remarks = ""
        elif not isinstance(self.remarks, str):
            self.remarks = str(self.remarks)

        if self.data is None:
            self.data = {}

    @classmethod
    def from_row(cls, row: Sequence[Any], dialect: str) -> Event:
        """Build an :class:`Event` from one database row.

        The inverse of :meth:`values`, and it expects
        :data:`~eventlog_pro.schema.SELECT_COLUMNS` order — ``id`` first, then
        the stored columns. ``created_at`` and ``data`` are the two that need
        real work; the rest come back as the strings they went in as.
        """
        if len(row) != len(SELECT_COLUMNS):
            raise ValueError(
                f"Expected {len(SELECT_COLUMNS)} columns in {SELECT_COLUMNS!r}, got {len(row)}."
            )
        values = dict(zip(SELECT_COLUMNS, row, strict=True))
        return cls(
            id=values["id"],
            created_at=from_db_datetime(values["created_at"], dialect),
            data=from_db_data(values["data"]),
            **{
                name: values[name]
                for name in SELECT_COLUMNS
                if name not in ("id", "created_at", "data")
            },
        )

    def __str__(self) -> str:
        return (
            f"pk={self.id} | app={self.app} | category={self.category} "
            f"| event_code={self.event_code}"
        )

    def json_data(self) -> str:
        """``data`` as a JSON string.

        ``default=str`` is deliberate: callers pass request headers and
        datetimes leak in. A ``TypeError`` out of ``json`` here is exactly the
        "logging blew up the webhook" failure this package exists to prevent.
        """
        return json.dumps(self.data, ensure_ascii=False, default=str)

    def as_dict(self) -> dict[str, Any]:
        """All fields, ``id`` first — used by the JSONL backend and tests."""
        return {f.name: getattr(self, f.name) for f in fields(self)}

    def to_orm_kwargs(self) -> dict[str, Any]:
        """Keyword arguments for ``EventLog.objects.create()``.

        ``created_at`` is included even though the model declares
        ``auto_now_add``; the Django backend clears ``auto_now_add`` handling by
        assigning after instantiation, so callers keep the timestamp the core
        generated.
        """
        return {name: getattr(self, name) for name in COLUMNS}

    def values(self, dialect: str | None = None) -> tuple[Any, ...]:
        """Column values in :data:`~eventlog_pro.schema.COLUMNS` order.

        ``data`` is serialised to JSON text. When *dialect* is given,
        ``created_at`` is rendered for that dialect's storage format via
        :func:`~eventlog_pro.schema.to_db_datetime`; otherwise it is returned
        as the aware ``datetime`` it is.
        """
        row: list[Any] = []
        for name in COLUMNS:
            if name == "data":
                row.append(self.json_data())
            elif name == "created_at" and dialect is not None:
                row.append(to_db_datetime(self.created_at, dialect))
            else:
                row.append(getattr(self, name))
        return tuple(row)
