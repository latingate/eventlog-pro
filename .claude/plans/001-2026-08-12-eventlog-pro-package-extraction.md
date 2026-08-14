# Extract `eventlog` into the `eventlog-pro` PyPI package

Status: done
Owner: Gal Sarig
Last updated: 2026-08-14

Executed in full. Remaining work, both listed under "Optional follow-up" below,
is tracked in two plans — split on 2026-08-14 because the second is work in a
different repository:

- publishing 0.1.0 → [002-2026-08-12-remaining-work-and-decisions.md](002-2026-08-12-remaining-work-and-decisions.md)
- the `pel-automation` cutover → [003-2026-08-14-pel-automation-cutover.md](003-2026-08-14-pel-automation-cutover.md)

Plus a pre-release check added on 2026-08-14, which runs before 002:
[004-2026-08-14-consumer-smoke-test-from-git.md](004-2026-08-14-consumer-smoke-test-from-git.md).

## Open Questions

_None._

## Context

`eventlog/` in pel-automation is a self-contained Django app: one model (`EventLog`, 12 columns), one
helper (`log_event()`), and one admin page. It has **zero coupling** to the rest of the project —
`migrations/0001_initial.py` has `dependencies = []`, there are no FKs, no `AUTH_USER_MODEL`
reference, no URLs, templates, signals or middleware, and it imports nothing outside `django.*`.
Only two files consume it (`pel/views.py:50` and the dated copy `pel/views_20260809.py:50`).

That makes it a good candidate to become a reusable, independently versioned package. The goal is a
standalone distribution — `eventlog-pro` on PyPI, import name `eventlog_pro` — that works in **two
modes** from a single install:

1. **Pure Python** (default install, zero dependencies) — writes to SQLite / PostgreSQL / MySQL /
   JSONL via a DSN, using stdlib `sqlite3` or an optional DB-API driver.
2. **Django** (`pip install eventlog-pro[django]`) — the app, model, migrations and admin, routed
   through the Django ORM.

Both modes expose the **same `log_event()` signature** and write the **same table shape**, so one
database can be read by either.

Decisions already made: one package with extras (not two packages, not runtime autodetect);
URL/DSN-driven pluggable backends; a new standalone repository, `eventlog-pro/`, checked out as a
sibling of `pel-automation/`, with **no changes to pel-automation** as part of this work beyond the
two documentation files below.

Paths below are repository-relative: unprefixed paths are inside this repo (`eventlog-pro/`), and
paths prefixed `pel-automation/` are inside the sibling repo.

## Deliverables

1. A new, self-contained repo — `eventlog-pro/`, this repository.
2. `pel-automation/.docs/eventlog_readme.md` — package reference.
3. `pel-automation/.docs/eventlog_setup.md` — install & setup guide.

Nothing under `pel-automation/eventlog/`, `pel/`, `pel_automation/` or `_checks/` is touched.

---

## Part 1 — Repo layout

```
eventlog-pro/
├── pyproject.toml                  # hatchling; all build + tool config
├── README.md  CHANGELOG.md  LICENSE (MIT)  .gitignore
├── .github/workflows/{ci.yml,publish.yml}
├── src/eventlog_pro/
│   ├── __init__.py                 # public API re-exports
│   ├── __about__.py                # __version__ = "0.1.0"  (single source of truth)
│   ├── py.typed                    # PEP 561 marker
│   ├── event.py                    # @dataclass Event — the 12 columns + id
│   ├── schema.py                   # COLUMNS tuple + ddl_for(dialect, table)
│   ├── config.py                   # Settings, configure(), get_settings(), reset(), env fallback
│   ├── dsn.py                      # parse_dsn() via urllib.parse
│   ├── registry.py                 # scheme -> backend class, lazy by dotted path
│   ├── entity.py                   # resolve_entity()
│   ├── api.py                      # log_event() / log_event_safe()
│   ├── exceptions.py               # EventLogError, ConfigurationError, BackendError, UnknownSchemeError
│   ├── utils/eventlog_utilities.py # deprecated shim re-exporting log_event
│   ├── backends/
│   │   ├── base.py                 # Backend ABC + ThreadLocalConnectionMixin
│   │   ├── sqlite.py  postgres.py  mysql.py  jsonl.py  memory.py  null.py  django.py
│   └── contrib/django/
│       ├── apps.py  models.py  admin.py  conf.py  checks.py
│       └── migrations/{0001_initial.py, 0002_add_indexes.py}
└── tests/                          # pytest + pytest-django, outside src/
```

**Every directory gets a real `__init__.py`** — including `utils/`. The source app's
`eventlog/utils/` has none and survives only on PEP 420 implicit namespace packages; that breaks
`find_packages()`, mypy resolution and frozen bundling. A CI check asserts no implicit namespace
dirs under `src/`.

Not carried over: `eventlog/views.py` (a bare `render` stub) and `eventlog/tests.py` (prints, no
assertions, a commented-out `input()` that would hang CI).

## Part 2 — `pyproject.toml`

**Build backend: hatchling.** It includes the whole package directory in the wheel by default, so
`contrib/django/migrations/*.py` ships with no `MANIFEST.in`/`package_data` glue — the number-one
packaging failure for Django apps. `[tool.hatch.version] path = "src/eventlog_pro/__about__.py"`
gives one version source with no import side effects.

```toml
[project]
name = "eventlog-pro"
requires-python = ">=3.10"          # 3.9 is EOL; Django 4.2 LTS floor is 3.10
dependencies = []                   # base install is pure stdlib — non-negotiable
license = "MIT"

[project.optional-dependencies]
django   = ["Django>=4.2"]
postgres = ["psycopg[binary]>=3.1"]
mysql    = ["PyMySQL>=1.1"]
all      = ["eventlog-pro[django,postgres,mysql]"]
dev      = ["eventlog-pro[all]", "pytest>=8", "pytest-django>=4.8", "pytest-cov",
            "ruff", "mypy", "build", "twine"]

[tool.hatch.build.targets.wheel]
packages = ["src/eventlog_pro"]
```

Plus `Framework :: Django :: 4.2/5.0/5.1/5.2` and `Typing :: Typed` classifiers, project URLs, and
`[tool.pytest.ini_options]` / `[tool.ruff]` / `[tool.mypy]` sections.

## Part 3 — Core (pure-Python)

### `Event` and the schema

`@dataclass(slots=True) Event` mirrors the 12 columns of
`pel-automation/eventlog/models.py` exactly, plus `id: int | None`. Column order is defined **once**
in `schema.py` as `COLUMNS = (created_at, created_by, app, category, sub_category, event_code,
event_type, entity_app, entity_model, entity_id, remarks, data)` — matching the Django model's
declaration order — and every backend builds its INSERT from that tuple. One list, no drift.

- `data` → `json.dumps(data, ensure_ascii=False, default=str)`. `default=str` is deliberate: callers
  pass request headers and datetimes leak in; a `TypeError` from `json` is exactly the "logging blew
  up the webhook" failure this is meant to prevent. `data=None` → `{}` (current behaviour).
- `created_at` = `datetime.now(timezone.utc)`, always tz-aware. Never `utcnow()`.
- All `varchar(100)` fields truncated to 100 chars in `__post_init__`, silently. Real callers pass
  free text (`event_code="first secret key"`); a `DataError` at 101 chars in a webhook is worse.

### Configuration

```python
@dataclass(frozen=True, slots=True)
class Settings:
    dsn: str = "sqlite:///./events.db"
    table: str = "eventlog_eventlog"
    raise_on_error: bool = True
    auto_create_table: bool = True
    backend: str | None = None
    ...
```

Precedence: explicit `configure()` kwargs → env vars (`EVENTLOG_DSN`, `EVENTLOG_TABLE`,
`EVENTLOG_SILENT`, `EVENTLOG_AUTO_CREATE_TABLE`, `EVENTLOG_BACKEND`) → defaults. Nothing connects at
import; the first `log_event()` materialises settings, resolves the backend, and runs
`CREATE TABLE IF NOT EXISTS` once per process. `configure()` after a backend is live closes and
discards it, so re-configuration is safe (essential for tests). `reset()` for teardown.

If no DSN is configured anywhere, emit a one-time `warning` naming the `events.db` file about to be
created — silently dropping a stray SQLite file in someone's CWD is how a package gets uninstalled.

### Backends

`Backend` is an **ABC**, not a `Protocol`, because subclasses inherit
`ThreadLocalConnectionMixin`, retry-on-stale-connection, and a default `ensure_schema()` driven by
`schema.ddl_for()`:

```python
class Backend(abc.ABC):
    scheme: ClassVar[tuple[str, ...]]
    def __init__(self, parsed: ParsedDSN, settings: Settings): ...
    @abc.abstractmethod
    def write(self, event: Event) -> Event: ...   # sets id + created_at
    def ensure_schema(self) -> None: ...
    def close(self) -> None: ...
```

| DSN | Backend | Extra needed |
|---|---|---|
| `sqlite:///./events.db`, `sqlite://:memory:` | `SQLiteBackend` | none (stdlib) |
| `postgresql://u:p@h:5432/db`, `postgres://…` | `PostgresBackend` | `[postgres]` |
| `mysql://…`, `mariadb://…` | `MySQLBackend` | `[mysql]` |
| `jsonl:///./events.jsonl` | `JSONLBackend` | none |
| `memory://`, `null://` | test / kill-switch | none |
| `django://<alias>` | `DjangoBackend` | `[django]` |

`registry.py` seeds schemes **lazily by module-path string**, so `import eventlog_pro` never imports
`psycopg`, `pymysql` or `django`. `register_backend(scheme, cls_or_dotted_path)` for custom
backends, plus `[project.entry-points."eventlog_pro.backends"]` discovery on first miss. A missing
driver raises `ConfigurationError("postgresql:// requires psycopg. Install: pip install
'eventlog-pro[postgres]'")` — always naming the extra.

Query params in the DSN land in `ParsedDSN.options`; `?table=` overrides `Settings.table`, so one env
var configures a whole deployment.

**Connections: one per thread, held open, created lazily** (`threading.local()`). `sqlite3.Connection`
is not thread-safe, and connect-per-write costs a TCP+TLS+auth round trip per log line on a webhook
path emitting 5–10 events per request. A `threading.RLock` guards writes for `jsonl` and `memory`
only. **No pooling** — documented stance: point the DSN at pgbouncer, or use `django://` and let
Django's `CONN_MAX_AGE` own the connection. A dead connection is detected on `write()`
(`OperationalError`/`InterfaceError`) and retried exactly once after reconnect.

### DDL parity — the core promise

`schema.ddl_for(dialect, table)` hand-writes DDL matching **what Django's own migration produces**,
so `migrate --fake-initial` works against a core-created table and both modes read each other's rows.

- **SQLite:** `id integer PRIMARY KEY AUTOINCREMENT` (not `bigint` — that breaks AUTOINCREMENT),
  `varchar(100)`, `text`, `datetime`. No `DEFAULT` clauses; Django doesn't emit them and every
  INSERT supplies all 12 columns.
- **PostgreSQL:** `id bigint GENERATED BY DEFAULT AS IDENTITY` (Django ≥4.1 emits identity, not
  `bigserial`), `timestamp with time zone`, `jsonb`. INSERT uses `%s::jsonb` with `json.dumps` on the
  Python side (never `psycopg.types.json.Jsonb`) plus `RETURNING id, created_at`.
- **MySQL/MariaDB:** `bigint AUTO_INCREMENT`, `datetime(6)`, `longtext`, `json`,
  `CHARSET=utf8mb4`. `id` via `cursor.lastrowid`; connect with `autocommit=True`.
- **JSONL:** one `json.dumps(asdict(event), default=str)` per line, `"a"` mode, utf-8, flushed under
  a lock, parent dirs created. `id` stays `None` — documented; no fake counter.

> **The `created_at` trap.** Django with `USE_TZ=True` stores SQLite/MySQL datetimes as UTC with
> tzinfo **stripped**, space-separated, no offset. The backends must do exactly
> `dt.astimezone(timezone.utc).replace(tzinfo=None).isoformat(sep=" ")`. An ISO `T` separator or a
> `+00:00` suffix makes rows unreadable by Django's converter and breaks admin `date_hierarchy`.
> This gets a dedicated test.

**Table name** defaults to `eventlog_eventlog` and is validated against `^[A-Za-z_][A-Za-z0-9_]*$`
before interpolation — it is the only user string reaching SQL unparameterised, so it gets a
whitelist regex, not an escape function.

**Indexes (an addition to the extracted behaviour):** `(created_at DESC)`,
`(app, category, event_code)`, `(entity_app, entity_model, entity_id)`. The original app has none;
this is the difference between an admin changelist that responds and one that table-scans.

### `entity=` without Django

`resolve_entity(entity) -> (app, model, id)`, tried in order:

1. `None` → `("", "", "")`.
2. Explicit `entity_app=`/`entity_model=`/`entity_id=` kwargs on `log_event` bypass resolution
   entirely — the escape hatch for pure-Python users with no objects.
3. `entity.__eventlog_entity__()` → 3-tuple or dict. Documented extension point.
4. **Duck-typed Django:** `entity._meta` has `app_label` + `model_name` →
   `(_meta.app_label, _meta.model_name, str(entity.pk))`. **Byte-identical to
   `eventlog_utilities.py:100-103`**, with no Django import.
5. `dict` with `entity_app`/`entity_model`/`entity_id` (or `app`/`model`/`id`).
6. 3-element `tuple`/`list` → positional.
7. Generic object: app = `type(entity).__module__.split(".")[0]`, model =
   `type(entity).__name__.lower()`, id = first non-`None` of `pk`/`id`/`uuid`/`slug`.
8. Scalars → `("", "", str(entity))`, so `entity="INV-1234"` just works.

Results truncated to 100 chars. **`resolve_entity` never raises** — a broken `__eventlog_entity__`
or exploding `__getattr__` degrades to `("", "", "")`.

### Failure policy

- `log_event(**kw) -> Event` — **raises by default.** This is today's behaviour at all 16 call
  sites; silently changing it during an extraction is the worst possible time, and a logger that
  silently returns `None` is how you discover in month three that nothing was recorded.
- `log_event_safe(**kw) -> Event | None` — never raises; `logger.exception(...)` on the stdlib
  logger `eventlog_pro` and returns `None`. The one to call from webhooks and signal handlers.
- Global kill switch `configure(raise_on_error=False)` / `EVENTLOG_SILENT=1` makes `log_event`
  behave like `log_event_safe`, so ops can defuse a misconfigured logger without a deploy.

`BaseException` (KeyboardInterrupt/SystemExit) is never swallowed in either mode.

## Part 4 — Django variant

Lives at `src/eventlog_pro/contrib/django/` — `contrib/` is the ecosystem convention for
"integration with an optional third party" and leaves room for `contrib/flask/` later.

```python
class EventLogProConfig(AppConfig):
    name = "eventlog_pro.contrib.django"
    label = "eventlog_pro"          # mandatory — otherwise Django derives the label "django"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self):
        # only if the user hasn't already configured
        configure(backend="django", dsn=f"django://{alias}", table=..., auto_create_table=False)
```

Users add `"eventlog_pro.contrib.django"` to `INSTALLED_APPS`. `default_app_config` is not used
(removed in Django 4.1).

### Migration & table-name compatibility — the critical decision

Existing installs have physical table `eventlog_eventlog` and four `django_migrations` rows under
`app='eventlog'`.

- **Option A** — keep `label = "eventlog"`, copy 0001–0004 verbatim. Zero-effort upgrade, but a
  PyPI package would squat the generic label `eventlog`: any project with its own `eventlog` app
  gets `ImproperlyConfigured: Application labels aren't unique`. It also welds the table name to the
  app label, blocking configurable `TABLE`.
- **Option B (recommended)** — `label = "eventlog_pro"`, one fresh `0001_initial` with explicit
  `db_table`. `db_table` **must** be explicit anyway — that is the mechanism by which the core
  backends and the ORM share a table. Once it is, there is no reason to hold the generic label
  hostage. Migrations 0002–0004 are pure churn (add `type` → alter help_text → rename to
  `event_type`); their end state is exactly today's `models.py`, so squashing is lossless.

**Ship the indexes in a separate `0002_add_indexes.py`, not in `0001_initial`** — that way an
existing install runs `--fake-initial` on 0001 (adopting the table) and *really applies* 0002,
turning the upgrade into four commands with no hand-written SQL.

```bash
# BACK UP FIRST.
# 1. INSTALLED_APPS: 'eventlog.apps.EventlogConfig' -> 'eventlog_pro.contrib.django'
python manage.py migrate eventlog zero --fake      # drop the old history, keep the table
python manage.py migrate eventlog_pro --fake-initial
python manage.py migrate eventlog_pro              # really applies 0002_add_indexes
```

Rollback restores `INSTALLED_APPS` and reverses the two fakes; the table is never dropped in either
direction.

The migration reads the table name from settings at import time (the standard settings-dependent
pattern used by `django-celery-results` / `django-axes`). Consequence — changing `TABLE` later will
not generate a rename — is stated in the docstring, and `checks.py` raises a Django system-check
warning when the configured table differs from the migration state.

### Settings and routing

```python
EVENTLOG_PRO = {
    "TABLE": "eventlog_eventlog", "DATABASE_ALIAS": "default",
    "ADMIN_ENABLED": True, "ADMIN_READONLY": True, "ADMIN_SEARCH_DATA": True,
    "ADMIN_LIST_PER_PAGE": 50, "RAISE_ON_ERROR": True, "DEFAULT_APP": "",
}
```

`conf.py` merges over defaults and raises `ImproperlyConfigured` listing unknown keys — a typo'd
setting that silently does nothing is a support-ticket generator.

`log_event()` is the *same function* in both modes. `DjangoBackend.write()` imports the model lazily
inside the method and does `EventLog.objects.using(alias).create(**event.to_orm_kwargs())`.
Deliberate asymmetry: in Django mode it returns the **model instance** (matching today's
`EventLog.objects.create(...)` return, which callers may rely on); in pure mode, the `Event`
dataclass. Both expose `.id`, `.app`, `.event_code`, `.data`, `.created_at`.

### Admin

Ported from `pel-automation/eventlog/admin.py` essentially as-is — `EventLogAdminForm` with the
`remarks` Textarea, all `list_display`/`list_filter`/`fieldsets`, `ordering = ("-created_at",)`,
`date_hierarchy`, `pretty_data` JSON `<pre>`, and `entity_admin_link` reversing
`admin:{entity_app}_{entity_model}_change` guarded by `NoReverseMatch`. Changes:

- Drop the duplicate `from django.contrib import admin` and the unused `from django.apps import apps`.
- Collapse `pretty_event_type`'s six-branch if/elif into a `_EVENT_TYPE_STYLES` dict, preserving the
  exact rendered output, overridable via settings.
- `search_fields` includes `"data"` only when `ADMIN_SEARCH_DATA` (see traps).
- Register at module bottom under `if ADMIN_ENABLED:` rather than the `@admin.register` decorator,
  so the toggle is clean; `EventLogAdmin` stays importable and subclassable.
- `ADMIN_READONLY = True` default disables add/change (delete stays). **Behaviour change from the
  source app** — flagged in the CHANGELOG — but an editable audit log is not an audit log.

## Part 5 — Public API

```python
__all__ = ["log_event", "log_event_safe", "configure", "get_settings", "reset",
           "Event", "Backend", "register_backend",
           "EventLogError", "ConfigurationError", "BackendError", "UnknownSchemeError",
           "__version__"]
```

All importable with **zero optional deps installed** — enforced by a CI job that installs the base
package alone and asserts `django`/`psycopg` are not in `sys.modules` after `import eventlog_pro`.

`eventlog_pro.utils.eventlog_utilities` re-exports `log_event` as a deprecated shim, so migrating
`from eventlog.utils.eventlog_utilities import log_event` is a one-token edit.

**Mode selection — no autodetect.** Three explicit mechanisms, in precedence order:
`configure(backend="django")` → DSN scheme `django://<alias>` → `AppConfig.ready()` (which fires
only because the user put the app in `INSTALLED_APPS`, so it is a declaration, not detection).

## Part 6 — Tests

`tests/` at repo root, outside `src/`, run against the installed package (`pip install -e .[dev]`) —
src-layout catches missing-package-data bugs an in-tree layout hides.

Django half uses **pytest-django** with a ~20-line `tests/django_settings.py` (in-memory SQLite,
`USE_TZ=True`, minimal `INSTALLED_APPS`, and a `tests/urls.py` including `admin.site.urls` so
`entity_admin_link`'s `reverse()` has a target). `tests/django/` is skipped at collection via
`collect_ignore_glob` guarded by `find_spec("django")`, so the core-only CI job passes cleanly.

Core backends use `tmp_path` DSNs with an autouse `reset()` fixture, and assert by reading back with
a raw `sqlite3.connect` / `json.loads` — testing the writer with the writer proves nothing.

Two parity tests carry the core promise:
- `test_schema_parity.py` — build the table twice into two SQLite files, once via
  `schema.ddl_for("sqlite", …)` and once via `call_command("migrate")`, then compare
  `PRAGMA table_info` column-by-column.
- Write a row through the core SQLite backend, read it through the Django ORM in the same file,
  assert `created_at` round-trips to the correct instant (the datetime trap above).

CI matrix: core-only on py3.10–3.13 (base install); Django on py3.10/3.12/3.13 × Django 4.2/5.2
(4.2 × 3.13 excluded); Postgres and MySQL integration jobs on service containers, `skipif` on
`EVENTLOG_TEST_{POSTGRES,MYSQL}_DSN` so they no-op locally; a lint job (ruff + mypy).

## Part 7 — Release

Version `0.1.0`, SemVer, source of truth `src/eventlog_pro/__about__.py` (not `importlib.metadata`,
which breaks for editable installs; not a git-tag plugin, which makes tarball sdists unbuildable).
License MIT. CHANGELOG in Keep-a-Changelog format, with `0.1.0` explicitly listing the deliberate
deviations from the in-repo app: added indexes, admin readonly by default, `default=str` JSON
coercion, varchar truncation, `log_event_safe`, app label `eventlog_pro`.

```bash
python -m build && twine check dist/*
python -m zipfile -l dist/*.whl | grep -E "migrations|py.typed"   # MUST show 0001, 0002, py.typed
pip install dist/*.whl   # in a clean venv, base install only, then smoke-test log_event
twine upload --repository testpypi dist/*                          # TestPyPI first
git tag v0.1.0 && git push --tags                                  # GH Action publishes
```

The `zipfile | grep` step is not optional — a Django app whose migrations missed the wheel installs
fine and fails at `migrate` in the user's production deploy.

`.github/workflows/publish.yml`: tag-triggered, a `build` job (build → `twine check` → assert
migrations shipped → upload artifact) and a `publish` job with `environment: pypi`,
`permissions: id-token: write`, and `pypa/gh-action-pypi-publish@release/v1`. **Trusted publishing —
no `PYPI_API_TOKEN` secret is ever created.** One-time PyPI setup: project → Publishing → add the
GitHub trusted publisher (repo `eventlog-pro`, workflow `publish.yml`, environment `pypi`).

## Part 8 — Traps carried over from the source app

| Trap | Handling |
|---|---|
| `eventlog/utils/` has **no `__init__.py`** (works only via PEP 420) | Real `__init__.py` everywhere; CI check for implicit namespace dirs. Most likely thing to break a naive copy-paste extraction. |
| `search_fields` includes the JSONField `"data"` (`admin.py:71`) — unindexable full-table scan on Postgres, can raise on MySQL 8 | Kept for parity, gated by `ADMIN_SEARCH_DATA`; documented under Limitations with the "set False past ~1M rows" advice and a note that a GIN index does **not** help `LIKE`. |
| Callers pass `app="auto.pel"` — not a Django app label | Documented: `app` is arbitrary caller-chosen text, max 100 chars, dots allowed, **no validation**. Validating it would break every existing caller. |
| `event_type` is free text; `pretty_event_type` lowercases to match but its `else` branch renders original casing | Matching stays `.lower()`-based; the casing inconsistency is preserved verbatim in 0.1.0 and listed in CHANGELOG as a 0.2 candidate. No enum, no `choices`. |
| `sub_category=` and `entity=` have **zero** production callers | Both kept in the signature, but they are the least-tested paths. `test_entity.py` gives `resolve_entity` exhaustive coverage of all 8 branches — new coverage, not ported. |
| `tests.py` has no assertions and a commented-out `input()` | Not ported; its *intent* becomes real assertion-bearing tests. |
| `__str__` commented out, with a `categoty` typo | Ported as a real `__str__`; typo not preserved. |

## Part 9 — The two documentation files

Both are written into `pel-automation/.docs/` and describe the package as an external dependency.

### `.docs/eventlog_readme.md` — package reference

What it is (the 12-column row; explicitly *not* a replacement for stdlib `logging`) · two modes
side-by-side · install lines · quickstarts · **full API reference** (`log_event` every parameter with
type/max-length/default/return/raises; `log_event_safe`; `configure` precedence and
re-configuration semantics; `get_settings`/`reset`; the `Event` dataclass; the `Backend` ABC and
`register_backend` with a complete ~30-line custom-backend example; the four exception types) ·
**DSN formats** one subsection per scheme with query params, required extra and quirks · **the
schema** (columns per dialect, verbatim DDL, the three indexes, the datetime storage rule, the
"both modes, one table" guarantee and its limits) · **`entity=` resolution** with a worked example
per branch and the `__eventlog_entity__` protocol · the Django app · the Django admin (every column,
the colour rules, `entity_admin_link` and its failure text, every `ADMIN_*` toggle) ·
**configuration reference** — one exhaustive table of setting | env var | `configure()` kwarg |
`EVENTLOG_PRO` key | type | default · failure policy & performance (raise vs safe, the
one-connection-per-thread model, the explicit no-pooling stance, why no async/batching in 0.1) ·
recipes (webhook logging, audit wrapper, querying events back out, pruning, shipping JSONL to a
collector) · limitations & FAQ · compatibility matrix · changelog/license links.

### `.docs/eventlog_setup.md` — install & setup

Prerequisites (noting pel-automation is Python 3.12 / Django 5.2 / Postgres → needs
`[django,postgres]`) · a three-question decision tree ending in one pip line · install commands with
the `~=0.1.0` pinning recommendation · **pure-Python quickstart, one numbered subsection per DSN**
(pip line → `configure()` call → env-var-only alternative → a `log_event()` call → the exact
SQL/`cat` command that proves the row landed) · **Django quickstart** (install → `INSTALLED_APPS`
line → the fully-commented `EVENTLOG_PRO` block → `migrate eventlog_pro` → confirm the table → find
"Event Log" in `/admin/` → a `manage.py shell` round-trip) · env var table + `.env` and Dockerfile
`ENV` examples matching pel-automation · a six-command verification checklist with expected output ·
**upgrading from the in-repo app** — the exact file/line change list
(`settings.py:199`, `pel/views.py:50`, `_checks/third_party_imports.py:15`,
`_checks/file_list_diff.py:24`), the four-command fake-migration path under a **BACK UP FIRST**
banner, the staging-rehearsal requirement, the index-lock warning for large tables, rollback, and a
before/after `EventLog.objects.count()` · upgrading between versions · a symptom → cause → fix
troubleshooting table (missing extra, duplicate app labels, `no such table`, `table already exists`
needing `--fake-initial`, stray `events.db`, admin section missing, "Admin page not registered",
`created_at` off by hours, empty JSONL, migrations missing from a bad wheel) · uninstall/disable via
`EVENTLOG_DSN=null://`.

---

## Optional follow-up — NOT part of this task

Listed only so the work is scoped. Nothing here is executed now; pel-automation is left untouched.

1. `pel-automation/requirements.txt` — add `eventlog-pro[django]~=0.1.0`.
2. `pel-automation/pel_automation/settings.py:199` — `'eventlog.apps.EventlogConfig'` →
   `'eventlog_pro.contrib.django'`.
3. `pel-automation/pel/views.py:50` (and `views_20260809.py:50`) — import from `eventlog_pro`. Consider switching
   the 16 `_zoho_log` call sites to `log_event_safe` — the main behavioural win, since `_zoho_log`
   sits on the Zoho webhook hot path with no exception guard today.
4. `pel-automation/_checks/third_party_imports.py:15` — drop `"eventlog"` from `LOCAL`.
5. `pel-automation/_checks/file_list_diff.py:24` — drop `"eventlog/"` from `KEEP_PREFIXES`.
6. Delete `pel-automation/eventlog/` — only after the above is green in staging.
7. **Rehearse the fake-migration against a copy of the production Postgres DB.** `--fake-initial`
   matches on table existence only, not columns, so drift would fake successfully and leave a broken
   model; and the three new indexes take a lock proportional to table size (use
   `CREATE INDEX CONCURRENTLY` by hand if large). Note `pel-automation/pel_automation/settings.py:273-282`
   swaps to SQLite when `"test" in sys.argv`, so `manage.py test` will never exercise the real
   migration path.
8. Update the app tables in `pel-automation/README.md:41` and `pel-automation/CLAUDE.md:15,98`.

## Verification

In `eventlog-pro/`:

```powershell
pip install -e ".[dev]"
pytest                                  # full suite incl. schema-parity tests
pytest -p no:cacheprovider tests/test_schema_parity.py -v
ruff check . ; mypy
python -m build ; twine check dist/*
python -m zipfile -l dist/*.whl | Select-String "migrations|py.typed"
```

Clean-venv smoke test, base install only (proves zero-dependency mode and no accidental imports):

```powershell
python -m venv $env:TEMP\evp ; & "$env:TEMP\evp\Scripts\pip" install .\dist\eventlog_pro-0.1.0-py3-none-any.whl
& "$env:TEMP\evp\Scripts\python" -c "import sys, eventlog_pro; assert 'django' not in sys.modules and 'psycopg' not in sys.modules; e = eventlog_pro.log_event(app='t', category='t', event_code='OK'); print(e.id)"
```

Django-mode end-to-end (a throwaway project, **not** pel-automation): `[django]` extra installed,
app in `INSTALLED_APPS`, `migrate eventlog_pro`, `log_event()` from `manage.py shell`, then confirm
the row in `/admin/` and that `date_hierarchy` and the entity link render.

Cross-mode parity, by hand: write via `sqlite:///./events.db` from pure Python, point a Django
project's `DATABASES` at the same file, and read the row back through `EventLog.objects.first()` —
the timestamp must match to the second.

Docs: read `.docs/eventlog_readme.md` and `.docs/eventlog_setup.md` and execute every command block
in the setup guide verbatim in a scratch directory; each must produce the stated output.
