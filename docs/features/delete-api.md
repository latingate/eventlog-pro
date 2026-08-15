# Delete API — `delete_events()`

Removes stored events and returns how many went. Retention is the use case it
exists for: "drop anything older than 90 days", as one bounded, repeatable call.

It is built **on** the read API's filter layer rather than beside it, so one
filter implementation serves both and a caller can see what a delete will take.
The filter arguments are documented once, in [read-api.md](read-api.md#filters);
which store it reaches is settled by [configuration.md](configuration.md).

## Public surface

```python
from datetime import date, timedelta
from eventlog_pro import delete_events

delete_events(to_created_at=date.today() - timedelta(days=90))
delete_events(to_created_at=date.today() - timedelta(days=90), limit=10_000)
```

Exported from `eventlog_pro`, defined in `src/eventlog_pro/api.py`. Returns an
`int`. **Raises** on failure — like `event_query()` and unlike `log_event()`, it
is not affected by `raise_on_error=False`, because a silent zero-delete is a
worse outcome than an exception.

## At least one filter is required

A bare `delete_events()` raises `ConfigurationError`. `limit` and `order_by` do
**not** count: they choose *which* rows go, not whether a row matches.

This is the guard the design settled on instead of an opt-in
`configure(allow_delete=True)` flag. An audit log that can empty itself by
accident is a different product; one that refuses the no-argument case is enough
to make erasure deliberate. To delete everything on purpose, pass a range that
covers everything.

The Django admin's own delete permission is unchanged and still governed by
`ADMIN_READONLY` — the two are not yet consistent, which `TODO.md` records.

## Previewing a delete

`event_query()` and `delete_events()` take identical filters, so they can be
paired — with one catch:

**`event_query()` caps at 100 rows by default and `delete_events()` never
caps.** The obvious check-then-delete pair therefore compares a 100-row preview
against an unbounded delete. Pass the same `limit` to both:

```python
doomed = event_query(to_created_at=cutoff, limit=None)   # limit=None matters
assert delete_events(to_created_at=cutoff) == len(doomed)
```

The asymmetry is deliberate. A default cap on the read protects an accidental
unfiltered query; the same cap on the delete would make a retention run report
success while leaving most of the rows behind.

## `limit`, and why it is two statements

With `limit` set, the **oldest** matching rows go first — `created_at ASC, id
ASC` — because deleting the oldest N is the retention case. An explicit
`order_by` overrides it. Without `limit` there is no "first N", so an unlimited
delete is not ordered at all.

`DELETE ... LIMIT` is not portable: PostgreSQL has no such clause, and stdlib
`sqlite3` is normally built without `SQLITE_ENABLE_UPDATE_DELETE_LIMIT`. Only
MySQL supports it. So a limited delete is two statements on one connection:

1. `SELECT id ... ORDER BY ... LIMIT n`
2. `DELETE ... WHERE id IN (...)`

Both run inside a single `run()` call, so the retry-once-on-dead-connection
behaviour is unchanged — but they are still two statements. **A row inserted
between them is not deleted.** That is correct for retention batching, where the
next run picks it up, and it is the reason `delete_events()` is not a safe way
to implement "delete exactly these rows, atomically".

An unlimited delete is a single `DELETE ... WHERE ...`.

## Per-backend behaviour

| Backend | How |
|---|---|
| `sqlite`, `postgresql`, `mysql` | `schema.delete_sql()`, or the two-statement form via `select_ids_sql()` + `delete_by_ids_sql()` when limited. Returns `cursor.rowcount`. |
| `django` | `queryset.delete()`, or `filter(pk__in=ids)` first when limited — `.delete()` refuses to run on a sliced queryset, which is the same two-statement shape for the same reason. |
| `memory` | Filters the in-process list. |
| `jsonl` | **Raises `BackendError`, and always will.** The file is append-only; deleting would mean rewriting it whole, and an interrupted rewrite truncates a log that exists to be shipped elsewhere. The lock is per-process, so a concurrent rewrite is unsafe in a way a concurrent append is not, and with `id` always `None` there is no way to name a row anyway. A read-filter-rewrite implementation is **rejected**, not deferred: retention on an append-only file is rotation. See [jsonl-backend.md](jsonl-backend.md). |
| `null` | Always `0`. |

Custom backends registered with `register_backend()` inherit a `delete()` that
raises `BackendError`, so a 0.1.x backend keeps working for writes and fails
clearly if a delete is attempted.

## Tests

`tests/test_api.py` covers the require-a-filter rule and the read/kill-switch
interaction. Per-backend deletes, including delete-oldest-N and the
`jsonl://` refusal, live in `tests/test_backend_sqlite.py`,
`test_backend_postgres.py`, `test_backend_mysql.py`, `test_backend_files.py`
and `tests/django_mode/test_models_and_backend.py`.
