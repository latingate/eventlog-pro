"""The filter surface shared by :func:`~eventlog_pro.api.event_query` and
:func:`~eventlog_pro.api.delete_events`.

One :class:`Criteria` object serves both, so a caller can preview with
``event_query()`` what ``delete_events()`` is about to remove — with the one
caveat that the two disagree about the default ``limit`` (see
:func:`build_criteria`).

Nothing here touches a database or a backend: it is pure argument
normalisation, which is why it can be unit-tested on its own.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Final

from .exceptions import ConfigurationError
from .schema import CHAR_COLUMNS, COLUMNS, MAX_CHARFIELD_LENGTH

__all__ = [
    "Criteria",
    "build_criteria",
    "normalize_order_by",
    "sort_events",
    "DEFAULT_QUERY_LIMIT",
    "FILTER_COLUMNS",
    "SORTABLE_COLUMNS",
]

#: What a bare ``event_query()`` returns. ``delete_events()`` has no default —
#: silently capping a retention run at 100 rows would look like success.
DEFAULT_QUERY_LIMIT: Final[int] = 100

#: Every column that can be filtered by equality. ``data`` is excluded: it is
#: filtered by substring instead, through its own argument.
FILTER_COLUMNS: Final[tuple[str, ...]] = ("id", *(c for c in COLUMNS if c != "data"))

#: Every column that can be sorted on. ``data`` is here too — ordering by it is
#: useless but harmless, and excluding it would be a second rule to remember.
SORTABLE_COLUMNS: Final[tuple[str, ...]] = ("id", *COLUMNS)

_DIRECTIONS: Final[tuple[str, ...]] = ("ASC", "DESC")

#: Newest first — the useful default for reading.
DEFAULT_QUERY_ORDER: Final[tuple[tuple[str, str], ...]] = (
    ("created_at", "DESC"),
    ("id", "DESC"),
)

#: Oldest first — deleting the *oldest* N is the retention use case.
DEFAULT_DELETE_ORDER: Final[tuple[tuple[str, str], ...]] = (
    ("created_at", "ASC"),
    ("id", "ASC"),
)


class _Unset:
    """Distinguishes "not passed" from ``limit=None`` (meaning unbounded)."""

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return "<unset>"


#: Public so :mod:`eventlog_pro.api` can spell the same "not passed" default.
UNSET: Final[Any] = _Unset()


@dataclass(frozen=True, slots=True)
class Criteria:
    """A normalised filter, ready for a backend to translate.

    ``created_from`` is always an inclusive lower bound. ``created_to`` carries
    its own operator because a ``datetime`` upper bound is inclusive while a
    ``date`` one means "through the end of that day" and is therefore exclusive
    of the next midnight.
    """

    equals: tuple[tuple[str, Any], ...] = ()
    contains: tuple[tuple[str, str], ...] = ()
    created_from: datetime | None = None
    created_to: datetime | None = None
    #: ``"<="`` or ``"<"``, describing ``created_to``.
    created_to_op: str = "<="
    order_by: tuple[tuple[str, str], ...] = field(default_factory=tuple)
    limit: int | None = None

    @property
    def has_filters(self) -> bool:
        """True if anything narrows the row set.

        ``limit`` and ``order_by`` deliberately do not count: they choose
        *which* rows, not *whether* a row matches, and ``delete_events()``
        refuses to run without a real filter.
        """
        return bool(
            self.equals
            or self.contains
            or self.created_from is not None
            or self.created_to is not None
        )

    def matches(self, event: Any) -> bool:
        """Evaluate this filter in Python, for the non-SQL backends.

        ``memory://`` and ``jsonl://`` have no query language, so they get the
        same semantics by running them here. Substring matching is
        case-sensitive, which agrees with SQLite and PostgreSQL but not with
        MySQL's default collation.
        """
        for column, expected in self.equals:
            if getattr(event, column, None) != expected:
                return False
        for column, needle in self.contains:
            haystack = event.json_data() if column == "data" else str(getattr(event, column, ""))
            if needle not in haystack:
                return False
        created_at = getattr(event, "created_at", None)
        if created_at is None:
            return not (self.created_from is not None or self.created_to is not None)
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)
        if self.created_from is not None and created_at < self.created_from:
            return False
        if self.created_to is not None:
            if self.created_to_op == "<=" and created_at > self.created_to:
                return False
            if self.created_to_op == "<" and created_at >= self.created_to:
                return False
        return True


def build_criteria(
    *,
    id: int | None = None,  # shadows the builtin, but it is the column's name
    created_at: datetime | date | None = None,
    from_created_at: datetime | date | None = None,
    to_created_at: datetime | date | None = None,
    created_by: str | None = None,
    app: str | None = None,
    category: str | None = None,
    sub_category: str | None = None,
    event_code: str | None = None,
    event_type: str | None = None,
    entity_app: str | None = None,
    entity_model: str | None = None,
    entity_id: str | None = None,
    remarks: str | None = None,
    data: str | None = None,
    order_by: Any = None,
    limit: Any = UNSET,
    for_delete: bool = False,
) -> Criteria:
    """Normalise filter keyword arguments into a :class:`Criteria`.

    Every column argument means exact equality, **except ``data``**, which is a
    substring match against the stored JSON text — see the README. ``None``
    means "not filtered"; ``""`` is a real filter that matches the empty
    column.

    The one thing *for_delete* changes is the pair of defaults: reads are
    capped at :data:`DEFAULT_QUERY_LIMIT` and sorted newest-first, deletes are
    uncapped and, when a limit *is* given, sorted oldest-first.
    """
    equals: list[tuple[str, Any]] = []
    contains: list[tuple[str, str]] = []

    if id is not None:
        if isinstance(id, bool) or not isinstance(id, int):
            raise TypeError(f"id must be an int, got {type(id).__name__}.")
        equals.append(("id", id))

    text_filters: tuple[tuple[str, str | None], ...] = (
        ("created_by", created_by),
        ("app", app),
        ("category", category),
        ("sub_category", sub_category),
        ("event_code", event_code),
        ("event_type", event_type),
        ("entity_app", entity_app),
        ("entity_model", entity_model),
        ("entity_id", entity_id),
        ("remarks", remarks),
    )
    for column, value in text_filters:
        if value is None:
            continue
        text = value if isinstance(value, str) else str(value)
        # Stored values are truncated to fit varchar(100), so an over-long
        # filter would match nothing at all; truncate it the same way instead.
        if column in CHAR_COLUMNS:
            text = text[:MAX_CHARFIELD_LENGTH]
        equals.append((column, text))

    if data is not None:
        if not isinstance(data, str):
            raise TypeError(
                "data= is a substring match against the stored JSON text, so it takes a "
                f"string, not {type(data).__name__}. To find a value, pass the value: "
                'data="INV-1234".'
            )
        contains.append(("data", data))

    created_from, created_to, created_to_op = _created_at_bounds(
        created_at, from_created_at, to_created_at
    )

    resolved_limit = _resolve_limit(limit, for_delete=for_delete)
    resolved_order = _resolve_order(order_by, limit=resolved_limit, for_delete=for_delete)

    return Criteria(
        equals=tuple(equals),
        contains=tuple(contains),
        created_from=created_from,
        created_to=created_to,
        created_to_op=created_to_op,
        order_by=resolved_order,
        limit=resolved_limit,
    )


def normalize_order_by(value: Any) -> tuple[tuple[str, str], ...]:
    """Normalise every accepted ``order_by`` spelling into ``(field, DIR)`` pairs.

    Accepts a bare field name (``"category"``), the ``"-field"`` shorthand for
    descending, a single ``(field, direction)`` pair, or a sequence mixing all
    of those — where sequence order is sort priority.
    """
    if value is None:
        return ()
    if isinstance(value, str):
        return (_one_term(value),)
    if isinstance(value, (set, frozenset)):
        if len(value) > 1:
            raise ConfigurationError(
                "order_by cannot be a set of more than one term: a set has no order, so the "
                "sort priority would be arbitrary. Pass a list or a tuple instead, e.g. "
                "order_by=[('category', 'ASC'), ('created_at', 'DESC')]."
            )
        value = list(value)
    if _is_pair(value):
        return (_one_term(value),)
    if not isinstance(value, Iterable):
        raise ConfigurationError(
            f"order_by must be a field name, a (field, direction) pair, or a sequence of "
            f"those; got {type(value).__name__}."
        )

    terms = tuple(_one_term(item) for item in value)
    seen: set[str] = set()
    for name, _direction in terms:
        if name in seen:
            raise ConfigurationError(f"order_by names {name!r} more than once.")
        seen.add(name)
    return terms


def _one_term(item: Any) -> tuple[str, str]:
    """One field name, or one ``(field, direction)`` pair, normalised."""
    if isinstance(item, str):
        name, descending = (item[1:], True) if item.startswith("-") else (item, False)
        return (_validate_field(name), "DESC" if descending else "ASC")
    if _is_pair(item):
        name, direction = item
        if name.startswith("-"):
            raise ConfigurationError(
                f"order_by term {item!r} gives the direction twice: drop the '-' from "
                f"{name!r} or drop {direction!r}."
            )
        return (_validate_field(name), direction.upper())
    raise ConfigurationError(
        f"Invalid order_by term {item!r}. Use 'field', '-field', or ('field', 'ASC'|'DESC')."
    )


def _is_pair(value: Any) -> bool:
    """True for a ``(field, direction)`` pair, as opposed to a list of fields.

    Both halves must be strings *and* the second must be a direction keyword,
    so ``("category", "app")`` reads as two fields rather than a bad direction.
    """
    return (
        isinstance(value, Sequence)
        and not isinstance(value, str)
        and len(value) == 2
        and all(isinstance(part, str) for part in value)
        and value[1].upper() in _DIRECTIONS
    )


def _validate_field(name: str) -> str:
    """Whitelist a sort field — this is the string that reaches SQL unbound."""
    if name not in SORTABLE_COLUMNS:
        raise ConfigurationError(
            f"Unknown order_by field {name!r}. Known: {', '.join(SORTABLE_COLUMNS)}."
        )
    return name


def _created_at_bounds(
    created_at: datetime | date | None,
    from_created_at: datetime | date | None,
    to_created_at: datetime | date | None,
) -> tuple[datetime | None, datetime | None, str]:
    """Turn the three timestamp arguments into one half-open-ish interval."""
    if created_at is not None and (from_created_at is not None or to_created_at is not None):
        raise TypeError(
            "created_at cannot be combined with from_created_at / to_created_at. Pass an "
            "exact created_at, or a range, not both."
        )

    if created_at is not None:
        if _is_plain_date(created_at):
            start = _start_of_day(created_at)
            return (start, start + timedelta(days=1), "<")
        moment = _as_utc(created_at)
        return (moment, moment, "<=")

    created_from = None if from_created_at is None else _lower_bound(from_created_at)
    created_to: datetime | None = None
    created_to_op = "<="
    if to_created_at is not None:
        if _is_plain_date(to_created_at):
            # "through the end of that day", expressed as "< the next midnight"
            # so the last microsecond of the day is not silently excluded.
            created_to = _start_of_day(to_created_at) + timedelta(days=1)
            created_to_op = "<"
        else:
            created_to = _as_utc(to_created_at)

    if created_from is not None and created_to is not None and created_from > created_to:
        raise ConfigurationError(
            f"from_created_at ({created_from.isoformat()}) is after to_created_at "
            f"({created_to.isoformat()}); nothing can match."
        )
    return (created_from, created_to, created_to_op)


def _is_plain_date(value: datetime | date) -> bool:
    """True for a ``date`` that is not also a ``datetime``."""
    return isinstance(value, date) and not isinstance(value, datetime)


def _start_of_day(value: date) -> datetime:
    return datetime.combine(value, time.min, tzinfo=timezone.utc)


def _lower_bound(value: datetime | date) -> datetime:
    return _start_of_day(value) if _is_plain_date(value) else _as_utc(value)


def _as_utc(value: datetime | date) -> datetime:
    """Naive datetimes are UTC — the same rule ``Event.__post_init__`` applies."""
    if not isinstance(value, datetime):  # pragma: no cover - guarded by callers
        return _start_of_day(value)
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _resolve_limit(limit: Any, *, for_delete: bool) -> int | None:
    if limit is UNSET:
        return None if for_delete else DEFAULT_QUERY_LIMIT
    if limit is None:
        return None
    if isinstance(limit, bool) or not isinstance(limit, int):
        raise TypeError(f"limit must be an int or None, got {type(limit).__name__}.")
    if limit < 1:
        raise ConfigurationError(f"limit must be at least 1, got {limit}.")
    return limit


def _resolve_order(
    order_by: Any, *, limit: int | None, for_delete: bool
) -> tuple[tuple[str, str], ...]:
    explicit = normalize_order_by(order_by)
    if explicit:
        return explicit
    if for_delete:
        # An unlimited delete has no "first N", so ordering it is pure cost.
        return DEFAULT_DELETE_ORDER if limit is not None else ()
    # A read is always limited unless told otherwise, so "which rows" is always
    # a real question and the default sort always applies.
    return DEFAULT_QUERY_ORDER


def sort_events(events: list[Any], order_by: tuple[tuple[str, str], ...]) -> list[Any]:
    """Apply *order_by* to a list of events, for the in-Python backends.

    Sorts once per term, least significant first — the standard stable-sort
    trick, which keeps mixed ASC/DESC directions correct without a comparator.
    """
    result = list(events)
    for name, direction in reversed(order_by):
        result.sort(key=lambda event: _sort_value(event, name), reverse=direction == "DESC")
    return result


def _sort_value(event: Any, name: str) -> Any:
    value = getattr(event, name, None)
    if name == "id":
        # `jsonl://` leaves id as None, and None is not orderable against int.
        return -1 if value is None else value
    if name == "data":
        return event.json_data()
    if isinstance(value, datetime) and value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value
