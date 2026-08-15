# The `jsonl://` backend

`jsonl:///./events.jsonl` · `jsonl:////var/log/events.jsonl`

Appends one JSON object per line to a file. Implemented in
`src/eventlog_pro/backends/jsonl.py`.

**This is a shipping format, not a database, and it is not the recommended
backend.** If what you want is "an event log without running a database server",
use `sqlite://` — it is in the standard library, adds no dependency, needs no
server, and supports the whole API including `delete_events()`. See
[configuration.md](configuration.md#the-dsn).

Use `jsonl://` when the file itself is the point: something else — Fluent Bit,
Vector, Loki, Promtail, a sidecar, `logrotate` plus S3 and Athena — picks the
file up and becomes the system of record. In that arrangement this package is a
writer, and the collector owns identity, retention and querying.

## What it writes

One `json.dumps` line per event, appended under a lock and flushed
(`backends/jsonl.py:50-61`):

```python
with self._lock, self.path.open("a", encoding=self.encoding, newline="\n") as handle:
    handle.write(line + "\n")
    handle.flush()
```

Opening in `"a"` and writing one line is the whole write. Nothing already in the
file is read, parsed or rewritten, so a write costs the same on an empty file and
a two-gigabyte one, and the file is valid before and after every write.

`created_at` is serialised as an ISO-8601 UTC string; everything else is the
event's field dict. `?encoding=` overrides the default `utf-8`.

`create_schema()` creates the parent directory and nothing else — a file has no
schema.

## Consequences

Three things follow from being a flat append-only file. All are deliberate.

### `id` is always `None`

A file has no sequence. Inventing a counter would produce ids that collide
across processes and restarts, so the field stays `None` and the collector
downstream assigns identity. This also means `event_query(id=…)` cannot match
anything, and `order_by="id"` sorts every row equal (`criteria.py:401-406` maps a
`None` id to `-1`).

### Reads are a full file scan

There is no index and no query language, so `read()` opens the file and tests
every line with `Criteria.matches()` — the same filter object the SQL backends
translate into a `WHERE` clause, evaluated in Python instead. Filtering is
therefore complete: every column by equality, `data=` by substring, `created_at`
ranges, `order_by` and `limit` all behave as documented in
[read-api.md](read-api.md).

The cost is that `limit` does not stop the scan early. Sorting and slicing happen
after the whole file has been read (`backends/jsonl.py:83-84`), so
`event_query(limit=10)` still parses every line and still holds every match in
memory. Cost is proportional to file size, not to result size, on every query.

Two failure modes are handled rather than raised on: a missing file reads as
`[]`, and a line that will not parse is skipped. That second one is why the
append-only design matters — a torn final write costs you one event, not the log.

### `delete_events()` raises

`delete()` raises `BackendError` (`backends/jsonl.py:86-96`). Deleting would
mean reading the file, filtering it and rewriting it whole, which is exactly the
operation this backend is shaped to avoid:

- The rewrite has a crash window. Interrupt it and you lose not the deleted rows
  but everything past the write cursor — the one thing an audit log must never
  do.
- The lock is a `threading.RLock`, so it is per-process. Concurrent appends from
  another process are safe; a concurrent read-modify-write is not.
- With `id` always `None`, there is no way to name a specific row anyway.
- It would cost O(file) to delete O(1) rows, and need disk headroom for two
  copies.

This is settled, not pending: a read-filter-rewrite delete is **rejected**, not
deferred.

## Retention

Rotate the file; do not delete rows. Closing the current file and starting a new
one, then dropping old files whole, is atomic, costs `O(1)`, is safe against
concurrent writers, and is what every log shipper already expects. `logrotate`,
a sidecar, or the collector's own retention policy all work — this package does
not need to be involved.

If you need selective deletion — "remove this customer's events", "drop
everything before a cutoff but keep the rest" — that is a database operation.
Use `sqlite://`, `postgresql://`, `mysql://` or `django://`; see
[delete-api.md](delete-api.md).

## Choosing between `jsonl://` and `sqlite://`

| | `jsonl://` | `sqlite://` |
|---|---|---|
| Dependencies | none | none (stdlib) |
| Server needed | no | no |
| `event_query()` | full file scan, every time | indexed |
| `delete_events()` | raises | supported |
| `id` | always `None` | assigned |
| Good for | handing the file to a collector | everything else |

The zero-dependency install gets both. Pick `sqlite://` unless the file leaving
the process is the actual requirement.

## Tests

`tests/test_backend_files.py` covers the write, the read path including the
skipped-unparsable-line and missing-file cases, and the `delete()` refusal.
