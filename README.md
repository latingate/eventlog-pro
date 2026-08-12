# eventlog-pro

A small structured event log: one `log_event()` call, one twelve-column row, two
interchangeable modes.

- **Pure Python** — the default install has **zero dependencies**. Writes to
  SQLite, PostgreSQL, MySQL/MariaDB or JSONL, chosen by a DSN.
- **Django** — the app, model, migrations and admin, routed through the ORM.

Both modes write the **same table shape**, so one database can be read by
either. This is not a replacement for stdlib `logging`: it records structured
business events you will query later, not lines of text you will grep.

```python
import eventlog_pro

eventlog_pro.configure(dsn="postgresql://user:pw@db/app")

eventlog_pro.log_event(
    app="api",
    category="webhook",
    sub_category="zoho",
    event_type="error",
    event_code="SIGNATURE_MISMATCH",
    entity=customer,                  # or "INV-1234", or ("pel", "customer", 7)
    remarks="Invalid webhook signature",
    data={"path": request.path, "ip": request.META.get("REMOTE_ADDR")},
    created_by="system",
)
```

## Install

```bash
pip install eventlog-pro                 # SQLite + JSONL, no dependencies
pip install "eventlog-pro[django]"       # the Django app
pip install "eventlog-pro[postgres]"     # psycopg 3
pip install "eventlog-pro[mysql]"        # PyMySQL
pip install "eventlog-pro[all]"          # everything
```

Python 3.10+. Django 4.2+ if you use the app.

## Two modes

### Pure Python

```python
import eventlog_pro

eventlog_pro.configure(dsn="sqlite:///./events.db")
event = eventlog_pro.log_event(app="api", category="system", event_code="STARTUP")
print(event.id)
```

Or configure nothing in code and set `EVENTLOG_DSN` in the environment.

### Django

```python
# settings.py
INSTALLED_APPS = [
    ...,
    "eventlog_pro.contrib.django",
]

EVENTLOG_PRO = {
    "TABLE": "eventlog_eventlog",
    "DATABASE_ALIAS": "default",
    "ADMIN_ENABLED": True,
    "ADMIN_READONLY": True,      # add/change disabled; delete still allowed
    "ADMIN_SEARCH_DATA": True,   # searching the JSON column: see Limitations
    "ADMIN_LIST_PER_PAGE": 50,
    "RAISE_ON_ERROR": True,
    "DEFAULT_APP": "",
}
```

```bash
python manage.py migrate eventlog_pro
```

`log_event()` is the *same function* in both modes. In Django mode it returns
the `EventLog` model instance (matching what `EventLog.objects.create(...)`
returned before); in pure mode, an `Event` dataclass. Both expose `.id`, `.app`,
`.event_code`, `.data` and `.created_at`.

**Mode selection is explicit — never autodetected.** In precedence order:
`configure(backend="django")`, then a `django://<alias>` DSN, then
`AppConfig.ready()`, which only fires because you put the app in
`INSTALLED_APPS`.

## DSN formats

| DSN | Backend | Extra |
|---|---|---|
| `sqlite:///./events.db` · `sqlite:////abs/path.db` · `sqlite://:memory:` | SQLite | none |
| `postgresql://u:pw@host:5432/db` · `postgres://…` | PostgreSQL | `[postgres]` |
| `mysql://u:pw@host:3306/db` · `mariadb://…` | MySQL/MariaDB | `[mysql]` |
| `jsonl:///./events.jsonl` | JSON Lines | none |
| `memory://` | in-process list, for tests | none |
| `null://` | accepts and discards everything | none |
| `django://` · `django://<alias>` | Django ORM | `[django]` |

Query parameters: `?table=` overrides the table name in any backend, so one
environment variable can configure a whole deployment. SQLite also takes
`?timeout=` and `?journal_mode=`; MySQL takes `?charset=`, `?connect_timeout=`,
`?unix_socket=` and `?ssl_disabled=`; PostgreSQL passes every other parameter
straight through to libpq (`?sslmode=require`, `?application_name=…`).

Three slashes means a relative path, four means absolute — the SQLAlchemy
convention.

## API

### `log_event(**kwargs) -> Event`

**Raises** on failure. That is today's behaviour at every existing call site,
and a logger that silently returns `None` is how you discover in month three
that nothing was recorded.

| Parameter | Type | Notes |
|---|---|---|
| `app` | `str` | Source system. Arbitrary text, max 100, dots allowed, unvalidated. Falls back to `default_app`. |
| `category` | `str` | Required. Main grouping. |
| `event_code` | `str` | Required. Stable machine-readable code. |
| `event_type` | `str` | Free text: `"error"`, `"info"`, `"warning"`, … |
| `sub_category` | `str` | Optional secondary grouping. |
| `entity` | any | See below. |
| `remarks` | `str` | Unbounded text. |
| `data` | `dict \| list \| None` | JSON payload; `None` is stored as `{}`. |
| `created_by` | `str \| None` | Username, email or process name. |
| `entity_app` / `entity_model` / `entity_id` | `str` | Set the entity columns directly, bypassing `entity=`. |

Every `varchar(100)` value is silently **truncated** to fit rather than
rejected, and `data` is serialised with `default=str`, so a stray datetime never
takes down the caller.

### `log_event_safe(**kwargs) -> Event | None`

Never raises. Logs the traceback to the `eventlog_pro` stdlib logger and returns
`None`. **This is the one to call from webhooks and signal handlers.**

`KeyboardInterrupt` and `SystemExit` are never swallowed, in either function.

### Kill switch

`configure(raise_on_error=False)` or `EVENTLOG_SILENT=1` makes `log_event()`
behave like `log_event_safe()`, so ops can defuse a misconfigured logger without
a deploy. `EVENTLOG_DSN=null://` turns logging off entirely.

### Configuration

| Setting | `configure()` | Env var | `EVENTLOG_PRO` key | Default |
|---|---|---|---|---|
| DSN | `dsn` | `EVENTLOG_DSN` | — | `sqlite:///./events.db` |
| Table | `table` | `EVENTLOG_TABLE` | `TABLE` | `eventlog_eventlog` |
| Backend override | `backend` | `EVENTLOG_BACKEND` | — | `None` |
| Raise on error | `raise_on_error` | `EVENTLOG_SILENT` (inverted) | `RAISE_ON_ERROR` | `True` |
| Create the table | `auto_create_table` | `EVENTLOG_AUTO_CREATE_TABLE` | — | `True` |
| Default `app` | `default_app` | `EVENTLOG_DEFAULT_APP` | `DEFAULT_APP` | `""` |

Precedence: explicit `configure()` → environment → defaults. Nothing connects at
import time; the first `log_event()` resolves the backend and runs
`CREATE TABLE IF NOT EXISTS` once per process. Re-configuring closes the live
backend, and `reset()` tears everything down — both safe in tests.

If nothing is configured anywhere, the package logs a one-time warning naming
the `events.db` file it is about to create.

### `entity=`

`resolve_entity()` tries, in order: `None`; an explicit `entity_*` kwarg; an
`__eventlog_entity__()` method returning a 3-tuple or dict; a duck-typed Django
model (`_meta.app_label`, `_meta.model_name`, `pk`); a dict with
`entity_app`/`entity_model`/`entity_id` or `app`/`model`/`id`; a 3-element
tuple or list; a generic object (module, class name, first of
`pk`/`id`/`uuid`/`slug`); and finally any scalar, so `entity="INV-1234"` just
works.

**It never raises.** A broken `__eventlog_entity__` or an exploding
`__getattr__` degrades to `("", "", "")`.

### Custom backends

```python
from eventlog_pro import Backend, register_backend

class RedisBackend(Backend):
    schemes = ("redis",)

    def write(self, event):
        ...
        return event

register_backend("redis", RedisBackend)          # or "my_pkg.backends:RedisBackend"
```

Packages can also advertise backends through the `eventlog_pro.backends` entry
point group.

### Exceptions

`EventLogError` is the base. `ConfigurationError` covers bad DSNs, invalid table
names and missing drivers (the message always names the extra to install);
`UnknownSchemeError` is a subclass of it. `BackendError` means the store refused
the write, with the driver's exception kept as `__cause__`.

## The schema

Twelve columns plus `id`, defined once and built identically by both modes:
`created_at`, `created_by`, `app`, `category`, `sub_category`, `event_code`,
`event_type`, `entity_app`, `entity_model`, `entity_id`, `remarks`, `data`.

| | SQLite | PostgreSQL | MySQL |
|---|---|---|---|
| `id` | `integer … AUTOINCREMENT` | `bigint … GENERATED BY DEFAULT AS IDENTITY` | `bigint AUTO_INCREMENT` |
| `created_at` | `datetime` | `timestamp with time zone` | `datetime(6)` |
| char columns | `varchar(100)` | `varchar(100)` | `varchar(100)` |
| `remarks` | `text` | `text` | `longtext` |
| `data` | `text` + `JSON_VALID` check | `jsonb` | `json` |

Plus three indexes: `(created_at DESC)`, `(app, category, event_code)` and
`(entity_app, entity_model, entity_id)`.

**Datetime storage.** With `USE_TZ=True`, Django stores SQLite and MySQL
datetimes as UTC with the tzinfo stripped and a space separator — no `T`, no
`+00:00`. The core backends write exactly that, which is what lets both modes
read each other's rows and keeps the admin's `date_hierarchy` working. The test
suite builds the table both ways and compares the DDL character for character.

## Upgrading from an in-repo `eventlog` app

**Back up first**, and rehearse against a copy of production.

```bash
# INSTALLED_APPS: 'eventlog.apps.EventlogConfig' -> 'eventlog_pro.contrib.django'
python manage.py migrate eventlog zero --fake      # drop the old history, keep the table
python manage.py migrate eventlog_pro --fake-initial
python manage.py migrate eventlog_pro              # applies 0002_add_indexes
```

`0001` is adopted, `0002` really runs, and the table is never dropped in either
direction. If the table was created by the **core backends** it already has the
indexes, so fake both instead: `python manage.py migrate eventlog_pro --fake`.

On a large table the three `CREATE INDEX` statements take a lock proportional to
row count; on PostgreSQL, create them with `CREATE INDEX CONCURRENTLY` by hand
and fake `0002`.

## Limitations

- The admin searches the JSON `data` column by default — a full-table `LIKE`
  scan that no index helps. Set `ADMIN_SEARCH_DATA = False` past ~1M rows.
- No pooling, no batching, no async in 0.1. One connection per thread, held
  open; point the DSN at pgbouncer, or use `django://`.
- `jsonl://` leaves `id` as `None`.
- Changing `TABLE` after the app has loaded does not move the table or generate
  a rename; the `eventlog_pro.W001` check reports the drift.

See [CHANGELOG.md](CHANGELOG.md) for the full list of deliberate deviations from
the app this package replaced.

## Development

```bash
pip install -e ".[dev]"
pytest                      # Postgres/MySQL tests skip themselves
ruff check . && ruff format --check . && mypy

# integration tests, against throwaway containers
docker run -d --rm -e POSTGRES_PASSWORD=secret -e POSTGRES_DB=evp -p 55432:5432 postgres:16-alpine
docker run -d --rm -e MYSQL_ROOT_PASSWORD=secret -e MYSQL_DATABASE=evp -p 33306:3306 mysql:8
EVENTLOG_TEST_POSTGRES_DSN=postgresql://postgres:secret@localhost:55432/evp \
EVENTLOG_TEST_MYSQL_DSN=mysql://root:secret@localhost:33306/evp pytest
```

## License

MIT — see [LICENSE](LICENSE).
