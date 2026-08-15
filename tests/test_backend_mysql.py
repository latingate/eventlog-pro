"""MySQL / MariaDB integration tests.

Skipped unless ``EVENTLOG_TEST_MYSQL_DSN`` is set::

    docker run -d --rm -e MYSQL_ROOT_PASSWORD=secret -e MYSQL_DATABASE=evp \
        -p 33306:3306 mysql:8
    EVENTLOG_TEST_MYSQL_DSN=mysql://root:secret@localhost:33306/evp pytest
"""

from __future__ import annotations

import os
from datetime import date, datetime, timezone

import pytest

import eventlog_pro
from eventlog_pro import BackendError, ConfigurationError, configure, log_event
from eventlog_pro.config import get_backend

DSN = os.environ.get("EVENTLOG_TEST_MYSQL_DSN", "")

pytestmark = [
    pytest.mark.skipif(not DSN, reason="EVENTLOG_TEST_MYSQL_DSN is not set"),
    pytest.mark.integration,
]

pymysql = pytest.importorskip("pymysql") if DSN else None

TABLE = "eventlog_pytest"


@pytest.fixture
def connection():
    from eventlog_pro.dsn import parse_dsn

    parsed = parse_dsn(DSN)
    conn = pymysql.connect(
        host=parsed.host or "localhost",
        port=parsed.port or 3306,
        user=parsed.username,
        password=parsed.password,
        database=parsed.database,
        autocommit=True,
    )
    with conn.cursor() as cursor:
        cursor.execute(f"DROP TABLE IF EXISTS {TABLE}")
    yield conn
    with conn.cursor() as cursor:
        cursor.execute(f"DROP TABLE IF EXISTS {TABLE}")
    conn.close()


@pytest.fixture
def configured(connection):
    configure(dsn=f"{DSN}?table={TABLE}")
    return connection


def query(connection, sql, args=None):
    with connection.cursor() as cursor:
        cursor.execute(sql, args)
        return cursor.fetchall()


def test_write_round_trips(configured):
    event = log_event(
        app="auto.pel",
        category="webhook",
        event_code="RECEIVED",
        entity=("pel", "customer", 7),
        data={"n": 1},
        remarks="unicode: שלום ✓",
        created_by="system",
    )
    (row,) = query(configured, f"SELECT id, app, entity_id, remarks FROM {TABLE}")
    assert row[0] == event.id
    assert row[1] == "auto.pel"
    assert row[2] == "7"
    assert row[3] == "unicode: שלום ✓"


def test_lastrowid_sets_the_id(configured):
    first = log_event(app="a", category="c", event_code="E")
    second = log_event(app="a", category="c", event_code="E")
    assert second.id == first.id + 1


def test_column_types_match_the_django_migration(configured):
    log_event(app="a", category="c", event_code="E")
    types = dict(
        query(
            configured,
            "SELECT column_name, column_type FROM information_schema.columns "
            "WHERE table_name = %s AND table_schema = DATABASE()",
            (TABLE,),
        )
    )
    assert types["id"] == "bigint"
    assert types["created_at"] == "datetime(6)"
    assert types["data"] == "json"
    assert types["remarks"] == "longtext"
    assert types["app"] == "varchar(100)"


def test_table_is_utf8mb4(configured):
    log_event(app="a", category="c", event_code="E")
    (row,) = query(
        configured,
        "SELECT table_collation FROM information_schema.tables "
        "WHERE table_name = %s AND table_schema = DATABASE()",
        (TABLE,),
    )
    assert row[0].startswith("utf8mb4")


def test_microseconds_survive_the_round_trip(configured):
    event = log_event(app="a", category="c", event_code="E")
    (row,) = query(configured, f"SELECT created_at FROM {TABLE}")
    stored = row[0].replace(tzinfo=timezone.utc)
    assert stored.microsecond == event.created_at.microsecond
    assert abs((stored - event.created_at).total_seconds()) < 0.001


def test_rerunning_the_ddl_survives_duplicate_indexes(configured):
    # MySQL has no CREATE INDEX IF NOT EXISTS; errno 1061 must be swallowed.
    log_event(app="a", category="c", event_code="ONE")
    eventlog_pro.reset()
    configure(dsn=f"{DSN}?table={TABLE}")
    log_event(app="a", category="c", event_code="TWO")
    assert query(configured, f"SELECT count(*) FROM {TABLE}")[0][0] == 2


def test_a_dead_connection_is_retried_once(configured):
    log_event(app="a", category="c", event_code="BEFORE")
    get_backend().connection.close()
    log_event(app="a", category="c", event_code="AFTER")
    assert query(configured, f"SELECT count(*) FROM {TABLE}")[0][0] == 2


def test_a_database_name_is_required():
    configure(dsn="mysql://root@localhost")
    with pytest.raises(ConfigurationError, match="needs a database name"):
        log_event(app="a", category="c", event_code="E")


def test_unreachable_server_is_a_backend_error():
    configure(dsn="mysql://nobody@127.0.0.1:1/none?connect_timeout=1")
    with pytest.raises(BackendError):
        log_event(app="a", category="c", event_code="E")


# --------------------------------------------------------------- reading back


@pytest.fixture
def seeded(configured):
    """Rows inserted with the raw driver, in MySQL's naive-UTC storage format."""
    get_backend().ensure_schema()
    rows = [
        ("2026-08-12 09:00:00.000000", "api", "OLD", "{}"),
        ("2026-08-13 09:00:00.000000", "api", "MID", "{}"),
        ("2026-08-14 23:59:59.999999", "web", "NEW", '{"invoice": "INV-1234"}'),
    ]
    with configured.cursor() as cursor:
        for created_at, app, code, data in rows:
            cursor.execute(
                f"INSERT INTO {TABLE} (created_at, created_by, app, category, sub_category, "
                "event_code, event_type, entity_app, entity_model, entity_id, remarks, data) "
                "VALUES (%s, '', %s, 'webhook', '', %s, '', '', '', '', '', %s)",
                (created_at, app, code, data),
            )
    return configured


def test_query_reads_naive_utc_back_as_aware(seeded):
    events = eventlog_pro.event_query()
    assert [event.event_code for event in events] == ["NEW", "MID", "OLD"]
    assert events[0].created_at == datetime(2026, 8, 14, 23, 59, 59, 999999, tzinfo=timezone.utc)
    assert events[0].created_at.tzinfo is not None
    assert events[0].data == {"invoice": "INV-1234"}


def test_query_filters_and_ranges(seeded):
    assert [e.event_code for e in eventlog_pro.event_query(app="api")] == ["MID", "OLD"]
    assert [e.event_code for e in eventlog_pro.event_query(to_created_at=date(2026, 8, 13))] == [
        "MID",
        "OLD",
    ]
    assert len(eventlog_pro.event_query(to_created_at=date(2026, 8, 14))) == 3
    assert len(eventlog_pro.event_query(created_at=date(2026, 8, 13))) == 1


def test_the_data_filter_casts_json_to_char(seeded):
    assert [e.event_code for e in eventlog_pro.event_query(data="INV-1234")] == ["NEW"]
    assert eventlog_pro.event_query(data="INV-9999") == []


def test_the_data_filter_still_escapes_wildcards_without_an_escape_clause(seeded):
    # MySQL gets no `ESCAPE` clause — it would be a syntax error — so this is
    # what proves its default backslash escape is doing the job.
    assert eventlog_pro.event_query(data="INV%") == []
    assert eventlog_pro.event_query(data="INV_1234") == []


def test_delete_and_limited_delete(seeded):
    assert eventlog_pro.delete_events(to_created_at=date(2026, 8, 14), limit=1) == 1
    assert [e.event_code for e in eventlog_pro.event_query()] == ["NEW", "MID"]
    assert eventlog_pro.delete_events(app="api") == 1
    assert [e.event_code for e in eventlog_pro.event_query()] == ["NEW"]
