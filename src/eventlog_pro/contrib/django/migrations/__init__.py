"""Migrations for the ``eventlog_pro`` app label.

One fresh ``0001_initial`` replaces the source app's 0001-0004, whose end state
(add ``type`` → alter its help_text → rename to ``event_type``) is exactly
today's model, so squashing them is lossless.

Upgrading an install that already has the physical table, **after a backup**::

    # INSTALLED_APPS: 'eventlog.apps.EventlogConfig' -> 'eventlog_pro.contrib.django'
    python manage.py migrate eventlog zero --fake      # drop the old history, keep the table
    python manage.py migrate eventlog_pro --fake-initial
    python manage.py migrate eventlog_pro              # really applies 0002_add_indexes

The indexes live in ``0002`` precisely so that sequence works: 0001 is adopted
by ``--fake-initial``, and 0002 is the only thing that actually touches the
database. The table is never dropped in either direction.

One exception: a table created by the **core backends** already has the three
indexes, so ``0002`` would fail on "index already exists". Those installs fake
both migrations instead::

    python manage.py migrate eventlog_pro --fake

Both paths are covered by ``tests/test_schema_parity.py``.
"""
