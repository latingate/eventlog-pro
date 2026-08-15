# Configuration — the DSN, the settings, and where they come from

How the package decides which store to write to. One URL configures a whole
deployment, and nothing is autodetected: which backend runs is always settled by
configuration, never by what happens to be importable.

## Public surface

```python
import eventlog_pro

eventlog_pro.configure(dsn="sqlite:///./eventlog-pro.db")   # once, at startup
eventlog_pro.get_settings()                                 # the current snapshot
eventlog_pro.reset()                                        # tear it all down
```

Defined in `src/eventlog_pro/config.py`. `Settings` is a frozen dataclass, so a
snapshot cannot drift under a caller holding it; `configure()` builds a new one
and discards any live backend.

## Precedence

Explicit `configure()` keywords → environment variables → defaults. In Django
mode the `EVENTLOG_PRO` settings dict in `settings.py` sits alongside these; it
is documented in `src/eventlog_pro/contrib/django/conf.py`, which owns the
merge and rejects unknown keys with `ImproperlyConfigured`.

| Setting | `configure()` | Env var | Default |
|---|---|---|---|
| DSN | `dsn` | `EVENTLOG_DSN` | `sqlite:///./eventlog-pro.db` |
| Table | `table` | `EVENTLOG_TABLE` | `eventlog_eventlog` |
| Backend override | `backend` | `EVENTLOG_BACKEND` | `None` |
| Raise on error | `raise_on_error` | `EVENTLOG_SILENT` (inverted) | `True` |
| Create the table | `auto_create_table` | `EVENTLOG_AUTO_CREATE_TABLE` | `True` |
| Default `app` | `default_app` | `EVENTLOG_DEFAULT_APP` | `""` |

`EVENTLOG_SILENT` is deliberately inverted: the environment variable names the
unusual state, so `EVENTLOG_SILENT=1` sets `raise_on_error=False`.

Unknown keywords to `configure()` raise `ConfigurationError` rather than being
ignored — a typo'd setting that silently does nothing is a support ticket
waiting to happen.

`Settings.dsn_source` (`"explicit"`, `"env"` or `"default"`) is internal. It
exists only so the fallback warning below can tell "the user chose SQLite" from
"nobody chose anything".

## Nothing happens at import time

Importing `eventlog_pro` pulls in the standard library and nothing else: no
Django, no database driver. The first `get_backend()` call materialises the
settings, resolves the backend class from the DSN scheme, and — unless
`auto_create_table=False` — runs `CREATE TABLE IF NOT EXISTS` once per process.

This is what makes `.env` files work with no dependency here: the environment is
read on first use, so `load_dotenv()` called *after* `import eventlog_pro` is
still picked up. Loading the file stays the application's job; a library that
read files from the working directory and mutated `os.environ` would affect
every other library in the process.

Re-configuring mid-process closes the live backend first, so it is safe between
tests. `reset()` tears down settings and backend together.

## The DSN

Parsed by `parse_dsn()` in `src/eventlog_pro/dsn.py`, permissive about shape and
strict about nothing except the scheme being present. Path conventions follow
the SQLAlchemy precedent, which is what people already have in their heads.

| DSN | Backend | Extra |
|---|---|---|
| `sqlite:///./eventlog-pro.db` · `sqlite:////abs/path.db` · `sqlite://:memory:` | SQLite | none |
| `postgresql://u:pw@host:5432/db` · `postgres://…` | PostgreSQL | `[postgres]` |
| `mysql://u:pw@host:3306/db` · `mariadb://…` | MySQL/MariaDB | `[mysql]` |
| `django://` | The Django ORM | `[django]` |
| `jsonl:///./events.jsonl` | One JSON object per line | none |
| `memory://` · `null://` | In-process list · discard everything | none |

Three slashes is a relative path and four is absolute, so
`sqlite:///./eventlog-pro.db` writes beside the working directory and
`sqlite:////var/log/events.db` writes to an absolute one. Windows drive letters
work with three.

Query options ride on the DSN: `?table=` everywhere, plus `?timeout=` and
`?journal_mode=` on SQLite. A missing driver for a scheme raises
`ConfigurationError` naming the extra to install, not `ImportError`.

`backend=` overrides the scheme outright. `configure(backend="django")` with no
matching DSN is a complete configuration on its own, so the mismatched scheme is
replaced rather than fought with.

Credentials are redacted by `redact()` wherever a DSN reaches a log line or an
exception message.

## The unconfigured fallback

With nothing configured anywhere, the default DSN applies and the package logs
one warning per process naming the absolute path of the file it is about to
create. The path in that warning is derived from `DEFAULT_DSN` rather than
written out a second time, so the file named is always the file opened.

### The 0.2.0 rename

The default filename was `events.db` before 0.2.0 and is `eventlog-pro.db` from
0.2.0 on — generic enough to collide with another tool's file in the same
directory, versus named after the package.

Only callers relying on the default are affected; anyone who set `EVENTLOG_DSN`
or called `configure()` sees no change. When the fallback fires and an
`events.db` is present in the same directory, a second warning names it, states
that it is untouched, and gives the one-line way to keep using it:

```python
eventlog_pro.configure(dsn="sqlite:///./events.db")
```

or `EVENTLOG_DSN=sqlite:///./events.db`. Nothing is moved, copied or opened
automatically. Adopting the old file silently was considered and rejected: it
would make the default DSN depend on directory contents, so two machines running
identical code would write to different files.

## Tests

`tests/test_config.py` covers precedence, re-configuration, unknown keywords,
the fallback warning, and that `DEFAULT_DSN` and the warned-about path cannot
drift apart. `tests/test_dsn.py` covers parsing. Django-mode settings live in
`tests/django_mode/test_conf_and_checks.py`.
