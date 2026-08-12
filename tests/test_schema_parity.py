"""The core promise: one table, readable by both modes.

Two independent checks:

1. Build the table twice — once with ``schema.ddl_for("sqlite", ...)`` and once
   with ``migrate`` — and compare the results column by column.
2. Write a row with the core SQLite backend and read it back through the Django
   ORM, asserting the timestamp survives (the ``created_at`` trap).
"""

from __future__ import annotations

import sqlite3
import warnings
from contextlib import contextmanager

import pytest
from django.conf import settings
from django.core.management import call_command
from django.db import connection, connections
from django.test import override_settings

import eventlog_pro
from eventlog_pro.schema import create_table_sql, ddl_for, index_name

TABLE = "eventlog_eventlog"

#: The tests that read the migrated schema use pytest-django's test database.
#: The ones that share a real file with the core backend deliberately do not —
#: they unblock the database themselves and clean up their own tmp_path file.
uses_test_database = pytest.mark.django_db


@contextmanager
def extra_database(alias: str, path):
    """Expose *path* as a real (non-test) database under *alias*.

    Django warns that overriding ``DATABASES`` is unsupported: no signal
    invalidates ``ConnectionHandler.settings``, and its first read copies the
    dict into ``_settings``. Both have to be dropped by hand, on the way in and
    on the way out.
    """
    databases = {
        **settings.DATABASES,
        alias: {"ENGINE": "django.db.backends.sqlite3", "NAME": str(path)},
    }
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        with override_settings(DATABASES=databases):
            _refresh_connections()
            try:
                yield
            finally:
                connections[alias].close()
                # Drop the wrapper too, or the next test reusing this alias
                # would talk to the previous test's file.
                del connections[alias]
    _refresh_connections()


def _refresh_connections() -> None:
    connections.__dict__.pop("settings", None)
    connections._settings = None


def core_built(path, *, indexes: bool = True) -> sqlite3.Connection:
    """A SQLite file whose table was created by the core DDL alone.

    ``indexes=False`` reproduces the table the source Django app left behind,
    which had none — that is the shape the documented upgrade path adopts.
    """
    statements = ddl_for("sqlite", TABLE) if indexes else (create_table_sql("sqlite", TABLE),)
    core = sqlite3.connect(path)
    for statement in statements:
        core.execute(statement)
    core.commit()
    return core


def table_info(cursor, table=TABLE):
    cursor.execute(f"PRAGMA table_info('{table}')")
    # (name, type, notnull, default, pk) — cid is positional and always matches.
    return [(row[1], row[2], row[3], row[4], row[5]) for row in cursor.fetchall()]


def index_info(cursor, table=TABLE):
    cursor.execute(f"PRAGMA index_list('{table}')")
    names = sorted(row[1] for row in cursor.fetchall() if not row[1].startswith("sqlite_"))
    result = {}
    for name in names:
        cursor.execute(f"PRAGMA index_info('{name}')")
        result[name] = [row[2] for row in cursor.fetchall()]
    return result


@uses_test_database
def test_columns_are_identical(tmp_path):
    core = core_built(tmp_path / "core.db")
    try:
        core_columns = table_info(core.cursor())
    finally:
        core.close()

    with connection.cursor() as cursor:
        django_columns = table_info(cursor.cursor)

    assert core_columns == django_columns


@uses_test_database
def test_indexes_are_identical(tmp_path):
    core = core_built(tmp_path / "core.db")
    try:
        core_indexes = index_info(core.cursor())
    finally:
        core.close()

    with connection.cursor() as cursor:
        django_indexes = index_info(cursor.cursor)

    assert core_indexes == django_indexes
    assert set(core_indexes) == {
        index_name(TABLE, "created"),
        index_name(TABLE, "app_cat"),
        index_name(TABLE, "entity"),
    }


@uses_test_database
def test_create_table_statement_matches_djangos(tmp_path):
    """Not just compatible — character for character the same DDL."""
    with connection.cursor() as cursor:
        cursor.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name=%s", [TABLE])
        django_sql = cursor.fetchone()[0]

    core_sql = create_table_sql("sqlite", TABLE)
    assert _normalise(core_sql) == _normalise(django_sql)


def _normalise(sql: str) -> str:
    """Collapse the cosmetic differences: our DDL is pretty-printed, Django's is not."""
    import re

    sql = sql.replace("IF NOT EXISTS ", "")
    sql = " ".join(sql.split())
    return re.sub(r"\s*([(),])\s*", r"\1", sql)


def test_django_can_adopt_an_existing_table(tmp_path, django_db_blocker):
    """The documented upgrade: ``--fake-initial`` adopts the table as it was.

    The source app's table had no indexes, so 0001 is faked and 0002 really
    runs — which is the whole reason the indexes ship separately.
    """
    path = tmp_path / "adopted.sqlite3"
    core_built(path, indexes=False).close()

    with django_db_blocker.unblock(), extra_database("adopted", path):
        call_command("migrate", "eventlog_pro", database="adopted", fake_initial=True, verbosity=0)
        with connections["adopted"].cursor() as applied:
            applied.execute("SELECT name FROM django_migrations WHERE app = 'eventlog_pro'")
            assert sorted(row[0] for row in applied.fetchall()) == [
                "0001_initial",
                "0002_add_indexes",
            ]
            applied.execute(f"PRAGMA index_list('{TABLE}')")
            created = [row[1] for row in applied.fetchall() if not row[1].startswith("sqlite_")]
            assert len(created) == 3


def test_a_core_created_table_is_adopted_with_a_full_fake(tmp_path, django_db_blocker):
    """A table the *core backend* made already has the indexes.

    ``--fake-initial`` only fakes 0001, so 0002 would try to create an index
    that exists. Such installs fake both — no DDL runs, nothing is lost.
    """
    path = tmp_path / "adopted.sqlite3"
    core_built(path).close()  # table *and* indexes, as the core backend leaves it

    with django_db_blocker.unblock(), extra_database("adopted", path):
        call_command("migrate", "eventlog_pro", database="adopted", fake=True, verbosity=0)
        with connections["adopted"].cursor() as applied:
            applied.execute("SELECT name FROM django_migrations WHERE app = 'eventlog_pro'")
            assert len(applied.fetchall()) == 2


def test_a_core_written_row_reads_back_through_the_orm(tmp_path, django_db_blocker):
    """The created_at trap: an ISO 'T' or a '+00:00' would break this."""
    from eventlog_pro.contrib.django.models import EventLog

    path = tmp_path / "shared.sqlite3"
    with django_db_blocker.unblock(), extra_database("shared", path):
        call_command("migrate", "eventlog_pro", database="shared", verbosity=0)

        eventlog_pro.configure(dsn=f"sqlite:///{path.as_posix()}", auto_create_table=False)
        written = eventlog_pro.log_event(
            app="core",
            category="webhook",
            event_code="FROM_CORE",
            remarks="written without Django",
            data={"n": 1, "unicode": "שלום"},
            created_by="system",
        )
        eventlog_pro.reset()

        row = EventLog.objects.using("shared").get(event_code="FROM_CORE")
        assert row.id == written.id
        assert row.app == "core"
        assert row.created_by == "system"
        assert row.data == {"n": 1, "unicode": "שלום"}
        assert row.created_at.tzinfo is not None
        assert abs((row.created_at - written.created_at).total_seconds()) < 0.001


def test_an_orm_written_row_reads_back_through_the_core(tmp_path, django_db_blocker):
    """And the same table in the other direction."""
    from eventlog_pro.contrib.django.models import EventLog

    path = tmp_path / "shared.sqlite3"
    with django_db_blocker.unblock(), extra_database("shared", path):
        call_command("migrate", "eventlog_pro", database="shared", verbosity=0)
        instance = EventLog.objects.using("shared").create(
            app="orm", category="c", event_code="FROM_ORM", data={"n": 2}
        )

    raw = sqlite3.connect(path)
    raw.row_factory = sqlite3.Row
    try:
        row = dict(raw.execute(f"SELECT * FROM {TABLE}").fetchone())
    finally:
        raw.close()

    assert row["id"] == instance.id
    assert row["app"] == "orm"
    assert "T" not in row["created_at"] and "+" not in row["created_at"]
