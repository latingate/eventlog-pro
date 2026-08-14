"""The Event dataclass: normalisation, serialisation, column order."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from eventlog_pro import Event
from eventlog_pro.schema import CHAR_COLUMNS, COLUMNS


def test_defaults_are_empty_not_none():
    event = Event()
    for name in CHAR_COLUMNS:
        assert getattr(event, name) == ""
    assert event.remarks == ""
    assert event.data == {}
    assert event.id is None


def test_created_at_is_tz_aware_utc_by_default():
    event = Event()
    assert event.created_at.tzinfo is not None
    assert event.created_at.utcoffset() == timedelta(0)
    assert abs(event.created_at - datetime.now(timezone.utc)) < timedelta(seconds=5)


def test_naive_created_at_is_assumed_utc():
    event = Event(created_at=datetime(2026, 8, 12, 10, 0, 0))
    assert event.created_at == datetime(2026, 8, 12, 10, 0, 0, tzinfo=timezone.utc)


@pytest.mark.parametrize("name", CHAR_COLUMNS)
def test_char_columns_truncate_silently(name):
    event = Event(**{name: "x" * 250})
    assert getattr(event, name) == "x" * 100


def test_non_string_char_values_are_stringified():
    assert Event(entity_id=4711).entity_id == "4711"


def test_data_none_becomes_empty_dict():
    assert Event(data=None).data == {}


def test_json_data_coerces_unserialisable_values():
    event = Event(data={"when": datetime(2026, 8, 12, tzinfo=timezone.utc), "s": {1, 2}})
    payload = json.loads(event.json_data())
    assert payload["when"].startswith("2026-08-12")
    assert isinstance(payload["s"], str)


def test_json_data_keeps_unicode_unescaped():
    assert "שלום" in Event(data={"greeting": "שלום"}).json_data()


def test_values_follow_column_order():
    event = Event(app="a", category="c", event_code="E")
    values = event.values()
    assert len(values) == len(COLUMNS)
    assert values[COLUMNS.index("app")] == "a"
    assert values[COLUMNS.index("event_code")] == "E"
    assert values[COLUMNS.index("data")] == "{}"


def test_values_render_created_at_per_dialect():
    event = Event(created_at=datetime(2026, 8, 12, 10, 0, tzinfo=timezone.utc))
    index = COLUMNS.index("created_at")
    assert event.values("sqlite")[index] == "2026-08-12 10:00:00"
    assert event.values("mysql")[index] == datetime(2026, 8, 12, 10, 0)
    assert event.values("postgresql")[index] == event.created_at
    assert event.values()[index] == event.created_at


def test_to_orm_kwargs_covers_every_column():
    assert set(Event().to_orm_kwargs()) == set(COLUMNS)


def test_as_dict_includes_id():
    assert Event(id=7).as_dict()["id"] == 7


def test_str_reports_identity():
    event = Event(id=3, app="pel", category="webhook", event_code="OK")
    assert str(event) == "pk=3 | app=pel | category=webhook | event_code=OK"


def test_from_row_inverts_values():
    """`from_row` must undo exactly what `values` did, for the same dialect."""
    original = Event(
        id=7,
        created_at=datetime(2026, 8, 12, 10, 0, 0, 123456, tzinfo=timezone.utc),
        app="api",
        category="webhook",
        event_code="RECEIVED",
        remarks="ok",
        data={"n": 1},
    )
    row = (original.id, *original.values("sqlite"))
    restored = Event.from_row(row, "sqlite")
    assert restored == original


def test_from_row_rejects_a_row_of_the_wrong_width():
    with pytest.raises(ValueError, match="columns"):
        Event.from_row((1, 2, 3), "sqlite")
