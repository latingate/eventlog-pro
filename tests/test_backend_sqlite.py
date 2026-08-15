"""SQLite backend.

Rows are asserted by reading them back with a raw ``sqlite3`` connection —
testing the writer with the writer proves nothing.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from datetime import date, datetime, timezone

import pytest

import eventlog_pro
from eventlog_pro import BackendError, configure, log_event
from eventlog_pro.config import get_backend


def read_rows(path, table="eventlog_eventlog"):
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    try:
        return [dict(r) for r in connection.execute(f"SELECT * FROM {table}")]
    finally:
        connection.close()


def test_write_round_trips(sqlite_dsn):
    dsn, path = sqlite_dsn
    configure(dsn=dsn)
    event = log_event(
        app="auto.pel",
        category="webhook",
        event_code="RECEIVED",
        event_type="info",
        remarks="ok",
        data={"n": 1},
        created_by="system",
    )
    (row,) = read_rows(path)
    assert row["id"] == event.id == 1
    assert row["app"] == "auto.pel"
    assert row["event_code"] == "RECEIVED"
    assert row["created_by"] == "system"
    assert json.loads(row["data"]) == {"n": 1}


def test_created_at_is_stored_django_readable(sqlite_dsn):
    dsn, path = sqlite_dsn
    configure(dsn=dsn)
    event = log_event(app="a", category="c", event_code="E")
    (row,) = read_rows(path)
    assert "T" not in row["created_at"]
    assert "+" not in row["created_at"]
    stored = datetime.fromisoformat(row["created_at"]).replace(tzinfo=timezone.utc)
    assert abs((stored - event.created_at).total_seconds()) < 0.001


def test_table_and_indexes_are_created(sqlite_dsn):
    dsn, path = sqlite_dsn
    configure(dsn=dsn)
    log_event(app="a", category="c", event_code="E")
    connection = sqlite3.connect(path)
    indexes = sorted(r[1] for r in connection.execute("PRAGMA index_list('eventlog_eventlog')"))
    connection.close()
    assert indexes == [
        "eventlog_eventlog_app_cat",
        "eventlog_eventlog_created",
        "eventlog_eventlog_entity",
    ]


def test_parent_directories_are_created(tmp_path):
    path = tmp_path / "deep" / "deeper" / "events.db"
    configure(dsn=f"sqlite:///{path.as_posix()}")
    log_event(app="a", category="c", event_code="E")
    assert path.exists()


def test_custom_table_via_query_option(tmp_path):
    path = tmp_path / "events.db"
    configure(dsn=f"sqlite:///{path.as_posix()}?table=audit_events")
    log_event(app="a", category="c", event_code="E")
    assert read_rows(path, "audit_events")[0]["event_code"] == "E"


def test_auto_create_table_can_be_switched_off(sqlite_dsn):
    dsn, _ = sqlite_dsn
    configure(dsn=dsn, auto_create_table=False)
    with pytest.raises(BackendError, match="no such table"):
        log_event(app="a", category="c", event_code="E")


def test_existing_database_is_reused(sqlite_dsn):
    dsn, path = sqlite_dsn
    configure(dsn=dsn)
    log_event(app="a", category="c", event_code="ONE")
    eventlog_pro.reset()
    configure(dsn=dsn)
    log_event(app="a", category="c", event_code="TWO")
    assert [r["event_code"] for r in read_rows(path)] == ["ONE", "TWO"]


def test_in_memory_database_is_shared_across_threads():
    configure(dsn="sqlite://:memory:")
    log_event(app="a", category="c", event_code="MAIN")

    ids = []
    thread = threading.Thread(
        target=lambda: ids.append(log_event(app="a", category="c", event_code="THREAD").id)
    )
    thread.start()
    thread.join()

    assert ids == [2]
    rows = get_backend().connection.execute("SELECT event_code FROM eventlog_eventlog").fetchall()
    assert [r[0] for r in rows] == ["MAIN", "THREAD"]


def test_each_thread_gets_its_own_file_connection(sqlite_dsn):
    dsn, path = sqlite_dsn
    configure(dsn=dsn)
    backend = get_backend()
    log_event(app="a", category="c", event_code="MAIN")
    seen = []

    def worker():
        log_event(app="a", category="c", event_code="THREAD")
        seen.append(backend.connection)

    thread = threading.Thread(target=worker)
    thread.start()
    thread.join()

    assert seen[0] is not backend.connection
    assert len(read_rows(path)) == 2


def test_a_dead_connection_is_retried_once(sqlite_dsn):
    dsn, path = sqlite_dsn
    configure(dsn=dsn)
    backend = get_backend()
    log_event(app="a", category="c", event_code="BEFORE")
    backend.connection.close()  # simulate the connection dying underneath us
    log_event(app="a", category="c", event_code="AFTER")
    assert [r["event_code"] for r in read_rows(path)] == ["BEFORE", "AFTER"]


def test_close_is_idempotent(sqlite_dsn):
    dsn, _ = sqlite_dsn
    configure(dsn=dsn)
    backend = get_backend()
    log_event(app="a", category="c", event_code="E")
    backend.close()
    backend.close()


def test_unopenable_database_is_a_backend_error(tmp_path):
    configure(dsn=f"sqlite:///{(tmp_path / 'dir').as_posix()}")
    (tmp_path / "dir").mkdir()
    with pytest.raises(BackendError):
        log_event(app="a", category="c", event_code="E")


# --------------------------------------------------------------- reading back
#
# Rows go in through a raw sqlite3 connection and come out through the read
# API, so a bug shared by the writer and the reader cannot hide.


def insert_rows(path, rows, table="eventlog_eventlog"):
    """Write rows with the raw driver, in the storage format the package uses."""
    connection = sqlite3.connect(path)
    try:
        for row in rows:
            connection.execute(
                f"INSERT INTO {table} (created_at, created_by, app, category, sub_category, "
                "event_code, event_type, entity_app, entity_model, entity_id, remarks, data) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    row["created_at"],
                    row.get("created_by", ""),
                    row.get("app", "api"),
                    row.get("category", "webhook"),
                    row.get("sub_category", ""),
                    row.get("event_code", "E"),
                    row.get("event_type", ""),
                    row.get("entity_app", ""),
                    row.get("entity_model", ""),
                    row.get("entity_id", ""),
                    row.get("remarks", ""),
                    json.dumps(row.get("data", {})),
                ),
            )
        connection.commit()
    finally:
        connection.close()


@pytest.fixture
def seeded(sqlite_dsn):
    """Three days of events, written with the raw driver."""
    dsn, path = sqlite_dsn
    configure(dsn=dsn)
    eventlog_pro.get_backend().ensure_schema()
    insert_rows(
        path,
        [
            {"created_at": "2026-08-12 09:00:00.000000", "event_code": "OLD", "app": "api"},
            {"created_at": "2026-08-13 09:00:00.000000", "event_code": "MID", "app": "api"},
            {
                "created_at": "2026-08-14 23:59:59.999999",
                "event_code": "NEW",
                "app": "web",
                "data": {"invoice": "INV-1234"},
            },
        ],
    )
    return dsn, path


def test_query_returns_events_newest_first(seeded):
    events = eventlog_pro.event_query()
    assert [event.event_code for event in events] == ["NEW", "MID", "OLD"]
    assert events[0].created_at == datetime(2026, 8, 14, 23, 59, 59, 999999, tzinfo=timezone.utc)
    assert events[0].data == {"invoice": "INV-1234"}


def test_query_filters_on_any_column(seeded):
    assert [e.event_code for e in eventlog_pro.event_query(app="api")] == ["MID", "OLD"]
    assert [e.event_code for e in eventlog_pro.event_query(event_code="NEW")] == ["NEW"]
    assert eventlog_pro.event_query(app="nobody") == []


def test_a_date_created_at_matches_the_whole_day(seeded):
    events = eventlog_pro.event_query(created_at=date(2026, 8, 14))
    assert [event.event_code for event in events] == ["NEW"]


def test_a_date_upper_bound_includes_the_last_microsecond_of_that_day(seeded):
    # 23:59:59.999999 on the 14th is exactly the value a "< next midnight"
    # bound must still include and a naive "<= midnight" one would drop.
    events = eventlog_pro.event_query(to_created_at=date(2026, 8, 14))
    assert [event.event_code for event in events] == ["NEW", "MID", "OLD"]


def test_a_range_excludes_what_falls_outside_it(seeded):
    events = eventlog_pro.event_query(
        from_created_at=date(2026, 8, 13), to_created_at=date(2026, 8, 13)
    )
    assert [event.event_code for event in events] == ["MID"]


def test_order_by_supports_several_fields_and_directions(seeded):
    events = eventlog_pro.event_query(order_by=[("app", "ASC"), ("created_at", "DESC")])
    assert [(e.app, e.event_code) for e in events] == [
        ("api", "MID"),
        ("api", "OLD"),
        ("web", "NEW"),
    ]


def test_data_is_a_substring_match(seeded):
    assert [e.event_code for e in eventlog_pro.event_query(data="INV-1234")] == ["NEW"]
    assert [e.event_code for e in eventlog_pro.event_query(data="invoice")] == ["NEW"]
    assert eventlog_pro.event_query(data="INV-9999") == []


def test_data_wildcards_are_escaped_not_honoured(seeded):
    # A LIKE pattern in the caller's string must be data, not syntax.
    assert eventlog_pro.event_query(data="INV%") == []
    assert eventlog_pro.event_query(data="INV_1234") == []


def test_query_is_capped_at_a_hundred_rows_by_default(sqlite_dsn):
    dsn, path = sqlite_dsn
    configure(dsn=dsn)
    eventlog_pro.get_backend().ensure_schema()
    insert_rows(
        path,
        [
            {"created_at": f"2026-08-14 12:00:{n // 60:02d}.{n % 60:06d}", "event_code": str(n)}
            for n in range(150)
        ],
    )
    assert len(eventlog_pro.event_query()) == 100
    assert len(eventlog_pro.event_query(limit=None)) == 150
    assert len(eventlog_pro.event_query(limit=5)) == 5


def test_delete_removes_matching_rows_and_returns_the_count(seeded):
    _dsn, path = seeded
    assert eventlog_pro.delete_events(app="api") == 2
    assert [row["event_code"] for row in read_rows(path)] == ["NEW"]


def test_a_limited_delete_takes_the_oldest_first(seeded):
    _dsn, path = seeded
    assert eventlog_pro.delete_events(to_created_at=date(2026, 8, 14), limit=2) == 2
    assert [row["event_code"] for row in read_rows(path)] == ["NEW"]


def test_a_limited_delete_honours_an_explicit_order(seeded):
    _dsn, path = seeded
    assert eventlog_pro.delete_events(to_created_at=date(2026, 8, 14), limit=1, order_by="-id") == 1
    assert [row["event_code"] for row in read_rows(path)] == ["OLD", "MID"]


def test_deleting_nothing_is_zero_not_an_error(seeded):
    assert eventlog_pro.delete_events(app="nobody") == 0
    assert eventlog_pro.delete_events(app="nobody", limit=5) == 0


def test_query_previews_exactly_what_delete_removes(seeded):
    preview = eventlog_pro.event_query(app="api", limit=None)
    assert eventlog_pro.delete_events(app="api") == len(preview)
