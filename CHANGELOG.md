# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.0] - 2026-08-12

First release. The package is an extraction of the in-repo `eventlog` Django app
from `pel-automation`, rebuilt to work with or without Django.

### Added

- `log_event()` and `log_event_safe()`, writing the same twelve-column row in
  both modes.
- Pure-Python backends selected by DSN: `sqlite://` (stdlib), `postgresql://`
  (`[postgres]`), `mysql://` / `mariadb://` (`[mysql]`), `jsonl://`, `memory://`
  and `null://`. `psycopg2` and `mysqlclient` are accepted as fallback drivers.
- The Django app at `eventlog_pro.contrib.django` (`[django]`) — model,
  migrations, admin, `EVENTLOG_PRO` settings, system checks and the `django://`
  backend.
- `configure()` / `get_settings()` / `reset()`, with environment-variable
  fallbacks (`EVENTLOG_DSN`, `EVENTLOG_TABLE`, `EVENTLOG_BACKEND`,
  `EVENTLOG_SILENT`, `EVENTLOG_AUTO_CREATE_TABLE`, `EVENTLOG_DEFAULT_APP`).
- `register_backend()` and `eventlog_pro.backends` entry-point discovery for
  custom backends.
- `resolve_entity()`, resolving `entity=` without importing Django, including
  the `__eventlog_entity__()` protocol.
- Three indexes the source app never had: `(created_at DESC)`,
  `(app, category, event_code)` and `(entity_app, entity_model, entity_id)`.
  They ship in `0002_add_indexes`, separately from `0001_initial`, so an
  existing install can adopt its table with `--fake-initial` and still get them.
- Type hints throughout, with a `py.typed` marker.

### Changed — deliberate deviations from the in-repo app

Each of these is a decision, not an accident.

- **The admin is read-only by default.** `ADMIN_READONLY` defaults to `True`,
  disabling add and change; delete is still permitted. An editable audit log is
  not an audit log. Set `EVENTLOG_PRO = {"ADMIN_READONLY": False}` for the old
  behaviour.
- **The app label is `eventlog_pro`, not `eventlog`.** A package that squatted
  the generic label would collide with any project that has its own `eventlog`
  app. The physical table name is unchanged (`eventlog_eventlog`) and is now
  configurable via `EVENTLOG_PRO["TABLE"]`.
- **`data` is serialised with `default=str`.** Callers pass request headers, and
  datetimes leak in; a `TypeError` out of `json` is exactly the "logging blew up
  the webhook" failure this package exists to prevent.
- **`varchar(100)` values are truncated, not rejected.** Real callers pass free
  text; a `DataError` at 101 characters in a webhook is worse than a shortened
  value.
- **`log_event_safe()` is new** — same signature, never raises, logs the
  traceback to the `eventlog_pro` logger and returns `None`. The one to call
  from webhooks and signal handlers. `log_event()` still raises by default, as
  it does today at every existing call site.
- **`created_at` is always timezone-aware UTC**, generated with
  `datetime.now(timezone.utc)`.
- **`__str__` is a real method.** The source had it commented out, with a
  `categoty` typo that is not preserved.
- Every package directory has a real `__init__.py`. The source app's
  `eventlog/utils/` had none and worked only as an implicit namespace package.

### Not carried over

- `eventlog/views.py` — a bare `render` stub.
- `eventlog/tests.py` — prints, no assertions, and a commented-out `input()`
  that would hang CI. Its intent became the real test suite.

### Known limitations

- `search_fields` includes the JSON `data` column, matching the source app. That
  is an unindexable full-table scan on PostgreSQL and can raise on MySQL 8; a
  GIN index does **not** help, because the query is a `LIKE`. Set
  `ADMIN_SEARCH_DATA = False` past roughly a million rows.
- `event_type` is free text, and `pretty_event_type` lower-cases to match while
  its fallback branch renders the original casing. The inconsistency is
  preserved verbatim here and is a 0.2 candidate.
- `app` is arbitrary caller-chosen text (existing callers pass `"auto.pel"`),
  capped at 100 characters and otherwise unvalidated.
- No connection pooling, no batching and no async. Point the DSN at pgbouncer,
  or use `django://` and let Django's `CONN_MAX_AGE` own the connection.
- The `jsonl://` backend leaves `id` as `None`: a file has no sequence.
- The table name is read once at import time by `Meta.db_table` and by the
  migration, so changing `TABLE` later does not generate a rename. The
  `eventlog_pro.W001` system check reports the drift.

### Deprecated

- `eventlog_pro.utils.eventlog_utilities` re-exports `log_event` and
  `log_event_safe` with a `DeprecationWarning`, so migrating
  `from eventlog.utils.eventlog_utilities import log_event` is a one-token edit.
  Scheduled for removal in 1.0.

[Unreleased]: https://github.com/latingate/eventlog-pro/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/latingate/eventlog-pro/releases/tag/v0.1.0
