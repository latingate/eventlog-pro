"""SQLite backend.

Rows are asserted by reading them back with a raw ``sqlite3`` connection —
testing the writer with the writer proves nothing.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timezone

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
