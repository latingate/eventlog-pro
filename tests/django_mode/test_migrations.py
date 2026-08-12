"""The migrations must stay in step with the model."""

from __future__ import annotations

import pytest
from django.core.management import call_command
from django.db import connection
from django.db.migrations.autodetector import MigrationAutodetector
from django.db.migrations.loader import MigrationLoader
from django.db.migrations.questioner import NonInteractiveMigrationQuestioner
from django.db.migrations.state import ProjectState


def test_no_missing_migrations():
    """``makemigrations --check`` in test form."""
    loader = MigrationLoader(None, ignore_no_migrations=True)
    autodetector = MigrationAutodetector(
        loader.project_state(),
        ProjectState.from_apps(__import__("django").apps.apps),
        NonInteractiveMigrationQuestioner(specified_apps=set(), dry_run=True),
    )
    changes = autodetector.changes(graph=loader.graph, trim_to_apps={"eventlog_pro"})
    assert "eventlog_pro" not in changes, changes.get("eventlog_pro")


def test_the_app_ships_exactly_two_migrations():
    loader = MigrationLoader(None, ignore_no_migrations=True)
    names = sorted(name for app, name in loader.disk_migrations if app == "eventlog_pro")
    assert names == ["0001_initial", "0002_add_indexes"]


def test_indexes_live_in_0002_so_fake_initial_works():
    """0001 must create no index, or --fake-initial would skip them forever."""
    loader = MigrationLoader(None, ignore_no_migrations=True)
    initial = loader.disk_migrations[("eventlog_pro", "0001_initial")]
    assert initial.initial is True
    assert all(type(op).__name__ == "CreateModel" for op in initial.operations)
    assert initial.operations[0].options["db_table"] == "eventlog_eventlog"

    second = loader.disk_migrations[("eventlog_pro", "0002_add_indexes")]
    assert [type(op).__name__ for op in second.operations] == ["AddIndex"] * 3


@pytest.mark.django_db(transaction=True)
def test_migrations_are_reversible():
    # transaction=True: SQLite's schema editor refuses to run inside the
    # transaction pytest-django wraps ordinary db tests in.
    call_command("migrate", "eventlog_pro", "0001", verbosity=0)
    with connection.cursor() as cursor:
        cursor.execute("PRAGMA index_list('eventlog_eventlog')")
        assert not [row for row in cursor.fetchall() if not row[1].startswith("sqlite_")]
    call_command("migrate", "eventlog_pro", verbosity=0)
    with connection.cursor() as cursor:
        cursor.execute("PRAGMA index_list('eventlog_eventlog')")
        assert len([row for row in cursor.fetchall() if not row[1].startswith("sqlite_")]) == 3
