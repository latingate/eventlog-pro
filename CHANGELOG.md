# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

<!-- RELEASING: rename this heading to "## [<version>] - YYYY-MM-DD" and add a
     fresh empty "## [Unreleased]" above it. Nothing automates this; publish.yml
     never reads this file, so a forgotten rename ships release notes headed
     "Unreleased", permanently. Full checklist:
     .claude/plans/005-2026-08-14-releasing-a-new-version.md step 3.
     Check whether a TestPyPI rehearsal applies (step 5):
     git diff --stat "$(git describe --tags --abbrev=0)..HEAD" -- pyproject.toml README.md -->

## [0.2.3] - 2026-08-16

### Changed

- **The test suite refuses to run against a stale installed copy.** `src/` is
  not on `sys.path`, so a non-editable install left over from an earlier version
  shadows the working tree silently and the suite passes having exercised code
  nobody edited. `tests/conftest.py` now compares the installed version against
  `src/eventlog_pro/__about__.py` and aborts collection with the fix
  (`pip install -e ".[dev]"`) when they disagree. Contributors only; nothing
  ships in the wheel. Comparing versions rather than paths is what keeps CI's
  deliberate non-editable install working.
- **The package summary no longer lists JSONL beside the three databases.** It
  read "pure Python (SQLite/PostgreSQL/MySQL/JSONL)", which is the exact framing
  0.2.1 removed from the README — and it is the more prominent of the two, being
  the one-line description under the package name on PyPI, in search results and
  in `pip show`. `jsonl://` is unchanged and still supported; see
  [docs/features/jsonl-backend.md](https://github.com/latingate/eventlog-pro/blob/main/docs/features/jsonl-backend.md).
  Note this only reaches PyPI when a version uploads — unlike the README, a
  summary cannot be corrected in place.
- **The author email is no longer published as package metadata.** `authors` in
  `pyproject.toml` carried a personal address, which PyPI renders in the Meta
  panel on the project page. The entry now names the author with no address;
  `[project.urls]` already points at the repository's Issues page, which is the
  contact channel that gets read. Like the summary above, this only reaches PyPI
  when a version uploads, and it cannot be corrected retroactively — 0.2.2 and
  earlier keep the old metadata permanently.

## [0.2.2] - 2026-08-16

### Fixed

- **The unconfigured-fallback warning no longer claims to create a file that is
  already there.** It now says `created <path>`, `is using the existing <path>`,
  or `will create <path>` — the last when `auto_create_table=False` defers the
  file to the first write. Only the wording of one `logging` warning changes; no
  API, default or stored data is affected.
- **That warning is no longer emitted when the database cannot be opened.** It
  fired before the backend was even constructed, so a failed `ensure_schema()`
  still announced a file that never appeared. It now follows a successful schema
  step, and a failure raises `BackendError` — which names the path itself.
- **A failed schema attempt no longer consumes the one-per-process warning.**
  The latch was set before the attempt, so a later retry in the same process was
  silently un-warned.
- **Two README links now resolve on the PyPI project page.** `CHANGELOG.md` and
  `LICENSE` were relative, which 404s in the rendered long description; they are
  absolute GitHub URLs now, matching the existing convention.

### Documentation

- `docs/features/configuration.md` documents all three warning wordings and the
  fact that the warning follows the schema step.

## [0.2.1] - 2026-08-15

Documentation only. **No behaviour changed and no DSN was removed** — the sole
code edit is a module docstring. Upgrading from 0.2.0 requires nothing.

### Documentation

- **`jsonl://` is documented as an export format, not a general-purpose
  backend**, and `sqlite://` is named as the recommended choice whenever the
  requirement is "no database server" — it is stdlib, adds no dependency, needs
  no server, and supports the full read and delete API. The README previously
  listed JSONL beside the three databases and credited it with half of the
  zero-dependency install, which invited people to pick it and then meet
  `id is None`, full-scan reads and a raising `delete_events()` at runtime.
- **No behaviour changed and no DSN was removed.** `jsonl://` works exactly as
  it did in 0.2.0; existing deployments need to do nothing. The only code change
  is a module docstring.
- New `docs/features/jsonl-backend.md` — what the backend writes, when it is the
  right choice (shipping the file to a collector that will own it), when it is
  not, and retention by rotation.
- A `jsonl://` delete is now recorded as **rejected rather than deferred**. A
  read-filter-rewrite has a crash window that can truncate the log, its lock is
  per-process, and with `id` always `None` there is no way to name a row.
  Retention on an append-only file is rotation.

## [0.2.0] - 2026-08-15

### Added

- **A read API: `event_query(**filters) -> list[Event]`.** Backend-agnostic, and
  the thing 0.1.0 was missing outside Django. Every stored column can be
  filtered; `created_at`, `from_created_at` and `to_created_at` accept a
  `datetime` or a `date` (a `date` means the whole UTC day, and `to_created_at`
  as a `date` means *through the end of* that day); `order_by` takes a field
  name, `"-field"`, a `(field, direction)` pair, or a sequence of those, where
  position is sort priority.
- **A delete API: `delete_events(**filters) -> int`.** The same filters, sharing
  one implementation, so `event_query()` can preview what a delete removes.
  Retention is one call: `delete_events(to_created_at=cutoff)`.
- `Backend.read()` and `Backend.delete()` — non-abstract hooks, so custom
  backends registered against 0.1.x keep working and raise a clear
  `BackendError` only if read from. Implemented for `sqlite`, `postgresql`,
  `mysql`, `django`, `memory` and `null`; `jsonl://` supports reads only.
- `Event.from_row()`, plus `schema.from_db_datetime()` / `from_db_data()` — the
  inverse of the write path, which 0.1.0 had no need for. Timestamps always come
  back tz-aware UTC, and parsing tolerates rows written by Django rather than by
  this package.
- Feature documentation at `docs/features/read-api.md`,
  `docs/features/delete-api.md` and `docs/features/configuration.md`.

### Changed

- **The default SQLite file is now `./eventlog-pro.db`, was `./events.db`.**
  Only affects callers relying on the default: if you set `EVENTLOG_DSN` or call
  `configure(dsn=...)`, nothing changes. `events.db` was generic enough to
  collide with another tool's file in the same directory; the new name matches
  the package.

  **Your old file is not touched, moved or read.** Events logged after upgrading
  go to the new file, so an existing `events.db` stops growing. To keep using
  it, name it explicitly:

  ```python
  eventlog_pro.configure(dsn="sqlite:///./events.db")   # or EVENTLOG_DSN=sqlite:///./events.db
  ```

  When the unconfigured fallback fires and an `events.db` is sitting in the same
  directory, the package now logs a second warning naming it, so the change is
  not silent. Adopting the old file automatically was rejected: it would make
  the default depend on directory contents, so two machines running identical
  code would write to different files.

### Decisions worth knowing

Each of these is a choice, not an oversight.

- **`data=` is a substring match, not equality.** It is the only column argument
  that does not mean equality. Byte-exact JSON comparison is useless in
  practice; `data="INV-1234"` finding the event that mentions an invoice is not.
  Passing a `dict` raises `TypeError` rather than matching nothing.
  Case-sensitive on SQLite and PostgreSQL, case-insensitive on MySQL — that is
  the collation's decision, and normalising it would change two backends to fix
  one.
- **`event_query()` caps at 100 rows by default; `delete_events()` never caps.**
  The read cap protects an accidental unfiltered query. The same cap on a delete
  would make a retention run report success while leaving most rows behind. The
  cost is that previewing a delete needs `event_query(..., limit=None)`.
- **`delete_events()` with no filter raises.** `limit` and `order_by` do not
  count as filters. The `configure(allow_delete=True)` gate discussed in
  `TODO.md` was deliberately not built; requiring a filter is the guard.
- **A limited delete is two statements**, not one: `DELETE ... LIMIT` is
  MySQL-only, so ids are selected and then deleted. A row inserted between the
  two is not deleted — correct for retention batching, and not a way to delete
  an exact set atomically.
- **Neither read nor delete is silenced by `raise_on_error=False`.** That kill
  switch is for the write path: a dropped log line is survivable, a silently
  empty read is not.
- The Django admin's delete permission is unchanged, so `ADMIN_READONLY` still
  permits deletion there. The two are not yet consistent.

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

[Unreleased]: https://github.com/latingate/eventlog-pro/compare/v0.2.3...HEAD
[0.2.3]: https://github.com/latingate/eventlog-pro/compare/v0.2.2...v0.2.3
[0.2.2]: https://github.com/latingate/eventlog-pro/compare/v0.2.1...v0.2.2
[0.2.1]: https://github.com/latingate/eventlog-pro/compare/v0.2.0...v0.2.1
[0.2.0]: https://github.com/latingate/eventlog-pro/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/latingate/eventlog-pro/releases/tag/v0.1.0
