"""PostgreSQL integration tests.

Skipped unless ``EVENTLOG_TEST_POSTGRES_DSN`` points at a database the suite may
create tables in, so a plain ``pytest`` run stays offline::

    docker run -d --rm -e POSTGRES_PASSWORD=secret -e POSTGRES_DB=evp \
        -p 55432:5432 postgres:16-alpine
    EVENTLOG_TEST_POSTGRES_DSN=postgresql://postgres:secret@localhost:55432/evp pytest
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone

import pytest

from eventlog_pro import BackendError, configure, log_event
from eventlog_pro.config import get_backend

DSN = os.environ.get("EVENTLOG_TEST_POSTGRES_DSN", "")

pytestmark = [
    pytest.mark.skipif(not DSN, reason="EVENTLOG_TEST_POSTGRES_DSN is not set"),
    pytest.mark.integration,
]

psycopg = pytest.importorskip("psycopg") if DSN else None

TABLE = "eventlog_pytest"


@pytest.fixture
def connection():
    with psycopg.connect(DSN, autocommit=True) as conn:
        conn.execute(f"DROP TABLE IF EXISTS {TABLE}")
        yield conn
        conn.execute(f"DROP TABLE IF EXISTS {TABLE}")


@pytest.fixture
def configured(connection):
    configure(dsn=f"{DSN}?table={TABLE}")
    return connection


def test_write_round_trips(configured):
    event = log_event(
        app="auto.pel",
        category="webhook",
        event_code="RECEIVED",
        entity=("pel", "customer", 7),
        data={"n": 1, "nested": {"k": "v"}},
        created_by="system",
    )
    row = configured.execute(f"SELECT id, created_at, app, entity_id, data FROM {TABLE}").fetchone()
    assert row[0] == event.id
    assert row[2] == "auto.pel"
    assert row[3] == "7"
    assert row[4] == {"n": 1, "nested": {"k": "v"}}  # real jsonb, not a string
    assert row[1] == event.created_at


def test_returning_sets_id_and_timestamp(configured):
    event = log_event(app="a", category="c", event_code="E")
    assert isinstance(event.id, int)
    assert event.created_at.tzinfo is not None


def test_column_types_match_the_django_migration(configured):
    log_event(app="a", category="c", event_code="E")
    types = dict(
        configured.execute(
            "SELECT column_name, data_type FROM information_schema.columns WHERE table_name = %s",
            (TABLE,),
        ).fetchall()
    )
    assert types["id"] == "bigint"
    assert types["created_at"] == "timestamp with time zone"
    assert types["data"] == "jsonb"
    assert types["remarks"] == "text"
    assert types["app"] == "character varying"


def test_identity_column_not_bigserial(configured):
    log_event(app="a", category="c", event_code="E")
    is_identity = configured.execute(
        "SELECT is_identity FROM information_schema.columns "
        "WHERE table_name = %s AND column_name = 'id'",
        (TABLE,),
    ).fetchone()[0]
    assert is_identity == "YES"


def test_indexes_are_created(configured):
    log_event(app="a", category="c", event_code="E")
    names = sorted(
        r[0]
        for r in configured.execute(
            "SELECT indexname FROM pg_indexes WHERE tablename = %s", (TABLE,)
        ).fetchall()
    )
    assert len([n for n in names if not n.endswith("pkey")]) == 3


def test_ddl_is_idempotent(configured):
    log_event(app="a", category="c", event_code="ONE")
    import eventlog_pro

    eventlog_pro.reset()
    configure(dsn=f"{DSN}?table={TABLE}")
    log_event(app="a", category="c", event_code="TWO")
    assert configured.execute(f"SELECT count(*) FROM {TABLE}").fetchone()[0] == 2


def test_a_dead_connection_is_retried_once(configured):
    log_event(app="a", category="c", event_code="BEFORE")
    get_backend().connection.close()
    log_event(app="a", category="c", event_code="AFTER")
    assert configured.execute(f"SELECT count(*) FROM {TABLE}").fetchone()[0] == 2


def test_bad_sql_is_wrapped_in_backend_error(configured):
    log_event(app="a", category="c", event_code="E")
    backend = get_backend()
    with pytest.raises(BackendError):
        backend.run(lambda c: c.cursor().execute("SELECT no_such_column"), what="probe")


def test_json_payloads_survive_odd_values(configured):
    log_event(
        app="a",
        category="c",
        event_code="E",
        data={"when": datetime(2026, 8, 12, tzinfo=timezone.utc)},
    )
    stored = configured.execute(f"SELECT data FROM {TABLE}").fetchone()[0]
    assert stored["when"].startswith("2026-08-12")
    assert json.dumps(stored)  # round-trips


def test_missing_database_is_a_backend_error():
    configure(dsn="postgresql://nobody:nothing@127.0.0.1:1/none?connect_timeout=1")
    with pytest.raises(BackendError):
        log_event(app="a", category="c", event_code="E")
