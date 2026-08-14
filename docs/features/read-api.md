# Read API — `event_query()`

Reads stored events back, in both modes, without the caller knowing which
backend is configured. The filter layer it is built on is shared with
[delete-api.md](delete-api.md), so a query can preview a delete.

## Public surface

```python
from eventlog_pro import event_query

events: list[Event] = event_query(**filters)
```

Exported from `eventlog_pro` and defined in `src/eventlog_pro/api.py`. Always
returns `Event` objects — including in Django mode, where `log_event()` returns
an `EventLog` model instance instead. Reads are typed consistently on purpose;
the write path's asymmetry exists for backwards compatibility and is not
extended here.

**It raises on failure.** `configure(raise_on_error=False)` / `EVENTLOG_SILENT`
is a write-path kill switch: dropping a log line is survivable, and a read that
silently returns `[]` is not.

## Filters

All filtering is normalised by `build_criteria()` in
`src/eventlog_pro/criteria.py` into a frozen `Criteria`, which each backend
translates. `None` means "not filtered"; `""` is a real filter matching the
empty column.

| Argument | Meaning |
|---|---|
| `id` | Exact primary key. Must be an `int`. |
| `created_by`, `app`, `category`, `sub_category`, `event_code`, `event_type`, `entity_app`, `entity_model`, `entity_id`, `remarks` | Exact match. |
| `created_at` | A `datetime` matches that instant; a `date` matches the whole UTC day. Cannot be combined with the range arguments — that raises `TypeError`. |
| `from_created_at` | Inclusive lower bound. A `date` means `00:00` that day. |
| `to_created_at` | Inclusive as a `datetime`; a `date` means "through the end of that day", i.e. `< the next midnight`. |
| `data` | Substring against the stored JSON text. See below. |
| `order_by` | Sort. See below. |
| `limit` | Maximum rows. Defaults to 100; `limit=None` is unbounded. |

Values for the nine `varchar(100)` columns are truncated to 100 characters
before comparison, matching what the write path stored — an over-long filter
would otherwise match nothing at all.

Naive datetimes are read as UTC, the same rule `Event.__post_init__` applies to
writes, so filters and stored values agree.

### `data=` is a substring match

The one argument that does not mean equality. `data="INV-1234"` matches any row
whose stored JSON contains that text, in a key or a value.

- A non-`str` value raises `TypeError` naming the semantics. `data={"invoice":
  "INV-1234"}` is what a caller reasoning from `app=` would write, so it must
  fail loudly rather than coerce and match nothing.
- `%`, `_` and `\` in the search string are escaped, so a wildcard in caller
  data stays data. SQLite and PostgreSQL are told so with an explicit
  `ESCAPE '\'`; **MySQL is not**, because backslash is already its default
  `LIKE` escape and spelling it out is a syntax error — MySQL treats backslash
  as an escape inside string literals too, so `ESCAPE '\'` reads as an escaped
  quote (error 1064).
- **Case-sensitive on SQLite and PostgreSQL, case-insensitive on MySQL**, whose
  default collation decides. This is documented rather than normalised: forcing
  `LOWER()` everywhere would change two backends to fix one, and defeat any
  future index.
- Single tokens are portable; structure is not. PostgreSQL's `jsonb`
  re-serialises on read — keys reordered, whitespace normalised — so a search
  string spanning JSON punctuation can match on SQLite and MySQL and not on
  PostgreSQL.
- Unindexed full scan. Pair it with `app=` or a date range on a large table.

### `order_by`

```python
order_by="category"                                # ascending
order_by="-created_at"                             # descending
order_by=("category", "ASC")                       # one (field, direction) pair
order_by=["category", ("created_at", "DESC")]      # position is sort priority
```

Direction is case-insensitive and must be `ASC` or `DESC`. Field names are
whitelisted against `id` plus the twelve stored columns — they are the only
caller-supplied strings that reach SQL unbound. Naming the same field twice
raises, as does giving the direction twice (`("-app", "DESC")`).

A `set` of more than one term is **rejected**: a set has no order, so sort
priority would be arbitrary. Pass a list or a tuple.

Defaults to `created_at DESC, id DESC`. Because a read is always limited unless
told otherwise, the default sort always applies — "which 100 rows" is always a
real question.

### `limit` defaults to 100

A bare `event_query()` returns the 100 most recent events. `limit=None` returns
every match. The cap exists so an accidental unfiltered read on a production
table does not load the whole log; it is the one place this API is not literal.

`delete_events()` deliberately has no such default — see
[delete-api.md](delete-api.md#previewing-a-delete).

## Per-backend behaviour

| Backend | How |
|---|---|
| `sqlite`, `postgresql`, `mysql` | `SELECT` built by `schema.select_sql()`, executed through the existing `run()` wrapper, so a dead connection is still retried once. |
| `django` | Translated to a queryset. `data=` needs `Cast("data", TextField())` first: `data__contains` on a `JSONField` means JSON *containment*, not substring, and raises `NotSupportedError` on SQLite. |
| `memory`, `jsonl` | Filtered in Python by `Criteria.matches()`, then sorted by `criteria.sort_events()`. Case-sensitive, so they agree with SQLite and PostgreSQL rather than MySQL. |
| `jsonl` | Full file scan, one JSON object per line. A missing file reads as `[]`; an unparsable line is skipped, so a torn final write does not make the log unreadable. `id` stays `None`. |
| `null` | Always `[]`. |

Custom backends registered with `register_backend()` inherit a `read()` that
raises `BackendError` — they keep working for writes and fail clearly if read
from.

## Reading rows back

`Event.from_row(row, dialect)` inverts `Event.values()`, using
`schema.from_db_datetime()` and `schema.from_db_data()`. Timestamps always come
back tz-aware UTC whatever the backend stored, and parsing is deliberately more
forgiving than writing: a `T` separator, a missing microsecond component and a
trailing `Z` all parse, because rows in an adopted table may have been written
by Django rather than by this package.

On SQLite, `created_at` is text, and the range filters compare it as text. That
works only because the stored format is fixed-width and zero-padded, so
lexicographic order matches chronological order.
`tests/test_schema.py::test_sqlite_timestamps_are_fixed_width_so_range_filters_can_compare_them`
guards it.

## Tests

`tests/test_criteria.py` covers the argument semantics with no database.
Per-backend round trips live in `tests/test_backend_sqlite.py`,
`test_backend_postgres.py`, `test_backend_mysql.py`, `test_backend_files.py` and
`tests/django_mode/test_models_and_backend.py`. Rows are seeded with the raw
driver and read back through the API, so a bug shared by reader and writer
cannot hide.
