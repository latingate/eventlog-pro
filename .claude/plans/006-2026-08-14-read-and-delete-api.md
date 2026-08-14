# Read and delete APIs (`event_query()` / `delete_events()`)

Status: done Owner: Gal Sarig Last updated: 2026-08-14

The first feature plan since the package shipped. It picks up the `## Read side`
and `## Delete side` entries of [`TODO.md`](../../TODO.md) — recorded there as deliberate omissions from 0.1.0, not
defects — and turns them into one piece of work, because the delete API is built on the read API's filter layer rather
than beside it. Releasing what it produces follows the standing checklist in
[005-2026-08-14-releasing-a-new-version.md](005-2026-08-14-releasing-a-new-version.md).

**Executed 2026-08-14.** All three Open Questions were answered and built as described. Steps 1–7 are done; step 8
(the 0.2.0 version bump) is left for whenever the release is actually cut, per plan 005 — the CHANGELOG entry sits
under `## [Unreleased]` until then.

Two things came out differently from the design below, both discovered while implementing:

- `data=` on the **Django** backend needed `Cast("data", TextField())`. `data__contains` on a `JSONField` means JSON
  *containment*, not substring, and raises `NotSupportedError` on SQLite.
- The public functions take **explicit keyword-only parameters** rather than `**filters`, matching how `log_event()`
  spells its arguments, so IDEs and mypy see the real signature.

## Context

0.1.0 is write-only outside Django. `Backend` exposes only `write`,
`ensure_schema`, `create_schema`, `ddl` and `close` (`src/eventlog_pro/backends/base.py:33-78`); pure-Python callers
read the table with `psql`, DBeaver or `sqlite3`, and there is no supported way to prune it. `TODO.md:9-48` records both
gaps and the shape they should take: a read function returning `list[Event]` first, then a delete function returning
`int`
built **on** the read filter layer rather than beside it, so one filter implementation serves both and a caller can
preview with `event_query()` exactly what
`delete_events()` will remove.

This plan delivers both, with the filter surface the request asks for: every stored column usable as an argument,
`created_at` accepting a `date` or a
`datetime`, `from_created_at` / `to_created_at` range bounds, a flexible
`order_by`, and `limit` — which matters most on delete, where it turns
"drop everything older than 90 days" into a bounded, repeatable batch.

Target release: **0.2.0** (minor — new public surface, no breaking change).

## Goal

- `eventlog_pro.event_query(**filters) -> list[Event]`, backend-agnostic.
- `eventlog_pro.delete_events(**filters) -> int`, sharing one filter implementation with `event_query()`, and refusing
  to run unfiltered.

## Scope

**In scope**

- New filter/criteria module, shared by both APIs.
- SQL builders (`select_sql`, `delete_sql`, `where_clause`) beside the existing
  `insert_sql` in `src/eventlog_pro/schema.py:237`.
- Row → `Event` inversion, including per-dialect `created_at` parsing (the inverse of `to_db_datetime`, `schema.py:250`,
  which today has none).
- `Backend.read()` / `Backend.delete()` on the ABC plus implementations for
  `sqlite`, `postgres`, `mysql`, `django`, `memory`, `null`, `jsonl`.
- Public `event_query` / `delete_events` in `api.py` and `__init__.py`.
- Tests, README `## API` sections, `docs/features/read-api.md` and
  `docs/features/delete-api.md`, CHANGELOG `## [Unreleased]`.

**Out of scope**

- CLI and dashboard (`TODO.md:20-24`) — this is their foundation, not them.
- `configure(allow_delete=True)` opt-in gating (`TODO.md:43-45`) — decided against for now; "require a filter" is the
  chosen guard.
- Reconciling `ADMIN_READONLY` with the Django admin's delete permission (`contrib/django/admin.py:156-164`) — stays
  as-is, tracked in `TODO.md`.
- Pagination/`offset`, aggregation, `count()`, structural JSON querying — `data=` is a text substring match
  (Question 1), and nothing treats `data` as a document: no key lookup, no containment, no path expressions.
- `delete_events()` for `jsonl://` (Question 2) — deferred to a later version, recorded in `TODO.md`.

## Assumptions

- `Event` stays the return type in every mode; the Django backend converts
  `EventLog` instances to `Event` on read (the write path's documented asymmetry at `backends/django.py:7-11` is not
  extended to reads — reads return the same type everywhere).
- The base install stays dependency-free (`pyproject.toml` `dependencies = []`).
- All filter *values* are bound parameters; only column names reach SQL unparameterised, and they are whitelisted
  against `COLUMNS` the same way
  `validate_table_name` (`schema.py:137`) whitelists the table.

## Open Questions

- **Question:** Should `data` (the JSON column) be usable as a filter argument? Equality on `jsonb` / `json` / `text`
  behaves differently in all three dialects. *Re-asked after the follow-up "what about checking whether the string
  passed in the argument is included in the data field?" — a substring test is a better fit than equality, and it is
  worth its own argument rather than overloading `data=`.*  
  (1) No — reject `data=` with a clear `TypeError`; every other column filters.  
  (2) Yes — `data=` compares the serialised JSON string for equality, documented as a literal text match.  
  (3) A separate `data_contains="…"` argument — substring match against the JSON column rendered as text
  (`"data" LIKE '%…%'` on SQLite, `"data"::text LIKE %s` on PostgreSQL, `CAST(`data` AS CHAR) LIKE %s` on MySQL), with
  `%` / `_` / `\` escaped in the caller's string. `data=` stays rejected. Portable for a single token
  (`data_contains="INV-1234"` finds it whether it is a key or a value); **not** portable for anything spanning JSON
  punctuation, because PostgreSQL's `jsonb` re-serialises on the way out — it reorders keys and normalises whitespace,
  so `data_contains='{"a": 1'` matches on SQLite and MySQL but not necessarily on PostgreSQL. Unindexed, so it is a
  full scan; pair it with `app=` / a date range in anything hot.  
  (4) Other. Enter your own answer or follow up question.
- **Recommendation:** 3 — it answers the real need (find the event that mentions this invoice number) without pretending
  JSON structure is queryable, and it stays honest about being a text scan. If it should also work on `remarks`, say so
  and it becomes `remarks_contains=` too, same machinery.
- **Answer:** 3 - but I prefer the argument name to be `data`, in the README.md - it will be explained.


- **Question:** Should `delete_events()` be supported for `jsonl://`? Reading is a line scan; deleting means rewriting
  the whole file with no primary key to anchor on.  
  (1) Read yes, delete raises `BackendError("jsonl:// does not support delete")`.  
  (2) Both, implemented as a full read-filter-rewrite of the file under the existing lock.  
  (3) Other. Enter your own answer or follow up question.
- **Recommendation:** 1 — `jsonl://` is a debug/tail sink; a rewrite that truncates on interruption is a bad trade for a
  format nobody retains.
- **Answer:** for now go with option 1, in the future we can consider implementing option 2.


- **Question:** Should `event_query()` apply a default `limit` when the caller gives none?  
  (1) No implicit cap — `event_query()` returns everything that matches; the caller owns the risk.  
  (2) Default `limit=1000`, overridable, with `limit=None` meaning unbounded.  
  (3) Other. Enter your own answer or follow up question.
- **Recommendation:** 1 — a silent cap makes `event_query()` a liar and breaks the "preview exactly what
  `delete_events()` will remove" property that `TODO.md:32-36` asks for.
- **Answer:** 2, but set the default to 100

## Design

### Filter surface (shared by both APIs)

New module `src/eventlog_pro/criteria.py`, exporting a frozen `Criteria`
dataclass and `build_criteria(**kwargs)`.

Accepted keyword arguments:

| Argument                                                                                                                          | Type                 | Meaning                                                                                                             |
|-----------------------------------------------------------------------------------------------------------------------------------|----------------------|---------------------------------------------------------------------------------------------------------------------|
| `id`                                                                                                                              | `int`                | Exact match.                                                                                                        |
| `created_by`, `app`, `category`, `sub_category`, `event_code`, `event_type`, `entity_app`, `entity_model`, `entity_id`, `remarks` | `str`                | Exact match. `""` is a real filter (matches the empty column); `None` means "not filtered".                         |
| `created_at`                                                                                                                      | `datetime` \| `date` | A `datetime` matches that instant; a **`date` matches the whole UTC day** (`>= 00:00`, `< next day`).               |
| `from_created_at`                                                                                                                 | `datetime` \| `date` | Inclusive lower bound. A `date` means `00:00:00` that day.                                                          |
| `to_created_at`                                                                                                                   | `datetime` \| `date` | Upper bound. A `datetime` is **inclusive** (`<=`); a **`date` means "through the end of that day"** (`< next day`). |
| `data`                                                                                                                            | `str`                | **Substring**, not equality — see below. `data="INV-1234"` matches any row whose JSON text contains it.             |
| `order_by`                                                                                                                        | see below            | Sort. Ignored by `delete_events()` only if `limit` is absent.                                                       |
| `limit`                                                                                                                           | `int \| None`        | Maximum rows returned / deleted. Must be `>= 1`, or `None` for unbounded.                                           |

`created_at` may not be combined with `from_created_at` / `to_created_at` — raise `TypeError`. Naive datetimes are
treated as UTC, exactly as
`Event.__post_init__` (`event.py:48-51`) already does, so the filter and the write path agree.

**`limit` defaults differently on the two functions** (Question 3):

- `event_query()` defaults to **`limit=100`**. Pass an explicit number for more, or `limit=None` for everything. A
  bounded default keeps an accidental `event_query()` on a million-row production table from loading the lot.
- `delete_events()` has **no default limit** — an unlimited delete is a single `DELETE … WHERE …`, and quietly capping
  it at 100 would make a retention call look like it succeeded while leaving most of the rows behind. Deletion is
  already guarded by the require-a-filter rule.

The consequence to document loudly in both the README and the feature docs: because the defaults differ,
`event_query(**filters)` is an exact preview of `delete_events(**filters)` **only when the same `limit` is passed to
both** — `event_query(**filters, limit=None)` for an unlimited delete. This is the one place the "preview what you are
about to delete" property needs the caller's help.

`limit` requires a deterministic `order_by`, otherwise "the first 100" is whatever the planner returns. Since
`event_query()` is now always limited unless told otherwise, its default sort applies always, not only when the caller
passes `limit`: `created_at DESC, id DESC` — newest first, so the default call is "the 100 most recent events".
`delete_events()` defaults to `created_at ASC, id ASC` when a `limit` is given, because deleting the *oldest* N is the
retention use case.

### `order_by` normalisation

`normalize_order_by(value) -> tuple[tuple[str, str], ...]`, accepting:

```python
order_by = "category"  # ("category", "ASC")
order_by = "-created_at"  # Django-style shorthand for DESC
order_by = ("category", "ASC")  # a single (field, direction) pair
order_by = ["category", ("created_at", "DESC")]  # mixed sequence, priority = order
order_by = [("category", "asc"), ("created_at", "desc")]
```

Rules:

- Direction is case-insensitive; only `ASC` / `DESC` accepted, anything else raises `ConfigurationError` (the type
  `schema.py` already raises for bad dialects and table names).
- Field names are validated against `("id", *COLUMNS)`; unknown names raise.
- The two-element-tuple form is disambiguated from the sequence form by checking that both elements are strings **and**
  the second is a direction keyword — so `("category", "app")` is read as two fields, not a bad direction.
- **A `set` of more than one element is rejected** with an explicit message:
  the request's `order_by={('category','ASC'), ('created_at','DESC')}` example cannot preserve sort priority, because
  Python sets are unordered. Pass a list or tuple instead. This is worth an explicit error rather than a silent
  arbitrary sort order.
- Duplicate fields raise.

### SQL construction

In `src/eventlog_pro/schema.py`, beside `insert_sql`:

```python
def where_clause(dialect, criteria) -> tuple[str, tuple[Any, ...]]


    def order_clause(dialect, order_by) -> str

    def select_sql(dialect, table, criteria) -> tuple[str, tuple[Any, ...]]

    def delete_sql(dialect, table, criteria) -> tuple[str, tuple[Any, ...]]

    def select_ids_sql(dialect, table, criteria) -> tuple[str, tuple[Any, ...]]

    def delete_by_ids_sql(dialect, table, ids) -> tuple[str, tuple[Any, ...]]
```

Reusing `quote_identifier` (`:154`), `placeholder` (`:159`),
`normalize_dialect` (`:126`) and `validate_table_name` (`:137`). Datetime bounds go through the existing
`to_db_datetime` (`:250`) so a range filter is expressed in exactly the storage format the write path produced — for
SQLite that is the space-separated text form, which sorts lexicographically and therefore compares correctly.

**`limit` on delete is the one genuinely hard part.** `DELETE ... LIMIT` is not portable: PostgreSQL has no such clause
at all, and stdlib `sqlite3` is usually built without `SQLITE_ENABLE_UPDATE_DELETE_LIMIT`. Only MySQL supports it. So a
limited delete is **two statements on one connection**:

1. `SELECT id FROM t WHERE … ORDER BY … LIMIT n`
2. `DELETE FROM t WHERE id IN (?, ?, …)`

An unlimited delete stays a single `DELETE … WHERE …`. Both run inside one
`self.run(...)` call so the existing retry-once-and-wrap behaviour (`base.py:125`) applies unchanged. Document the
obvious race: a concurrent insert between the two statements is not deleted, which is correct for retention batching.

### Row → `Event`

`Event.from_row(row, dialect)` in `src/eventlog_pro/event.py`, the inverse of
`values()` (`event.py:99`), plus `from_db_datetime(value, dialect)` in
`schema.py` beside `to_db_datetime`:

- sqlite: `datetime.fromisoformat(text)` then attach `timezone.utc`.
- mysql: naive `datetime` → attach `timezone.utc`.
- postgresql: already aware → `astimezone(timezone.utc)` (same normalisation
  `backends/postgres.py:107-113` already does after a write).
- `data`: `json.loads` when the driver hands back text; already a dict for
  `jsonb`/`json` columns.

`Event.__post_init__` must not re-truncate or otherwise mangle values coming back from the database — it already only
truncates to 100 chars, which stored values satisfy by construction, so no change is needed there.

### Backend surface

On `Backend` (`backends/base.py`), beside `write` (`:51`):

```python
def read(self, criteria: Criteria) -> list[Event]:
    raise BackendError(f"{self.__class__.__name__} does not support read")


def delete(self, criteria: Criteria) -> int:
    raise BackendError(f"{self.__class__.__name__} does not support delete")
```

Non-abstract, so **existing custom backends registered via `register_backend`
keep working** — they simply raise a clear error if read from. That backward-compatibility point is why these are hooks
and not `@abstractmethod`.

Per backend:

- **sqlite / postgres / mysql** — `ensure_schema()`, build SQL from `schema.py`, execute through
  `self.run(op, what="query")` / `what="delete"`.
- **django** (`backends/django.py`) — translate `Criteria` to a queryset:
  `EventLog.objects.using(self.alias).filter(**lookups)`, `created_at__gte` /
  `created_at__lt`, `.order_by(*django_order)`, `[:limit]`; delete via
  `.filter(pk__in=…).delete()` when limited, `.delete()` otherwise. Returns
  `Event` objects, not model instances.
- **memory** (`backends/memory.py`) — filter the in-process list in Python; gives the test suite a backend-free way to
  exercise the filter semantics.
- **null** — `read` returns `[]`, `delete` returns `0`.
- **jsonl** (Question 2) — `read` is supported: scan the file line by line, `json.loads` each, apply the same `Criteria`
  in Python that the memory backend uses, and return `Event`s with `id=None` (`jsonl.py` never assigns one). `delete`
  raises `BackendError("jsonl:// does not support delete")`. The read-filter-rewrite alternative is deferred, not
  rejected — record it in `TODO.md` under `## Delete side` so it is not rediscovered.

### Public API

In `src/eventlog_pro/api.py`, beside `log_event`:

```python
def event_query(**filters: Any) -> list[Event]


    def delete_events(**filters: Any) -> int
```

Both resolve the backend with the existing `get_backend()` (`config.py:133`). Unlike `log_event`, **both always raise on
failure** — `raise_on_error=False`
is a write-path kill switch (a dropped log line is acceptable; a silently empty read result or a silent zero-delete is
not). State this explicitly in the docstrings and README.

`delete_events()` with no filter argument raises `ConfigurationError`
(message: at least one filter is required; pass an explicit range to delete everything). `limit` and `order_by` alone do
**not** count as filters.

The filter kwargs are identical across the two functions; only the `limit` default and the default sort direction
differ, and both live in `build_criteria(..., for_delete: bool)` so there is still exactly one filter implementation.

## Steps

1. **Add `criteria.py`** — `Criteria`, `build_criteria`, `normalize_order_by`, date/datetime coercion. Pure functions,
   no backend imports; unit-testable on its own.
2. **Extend `schema.py`** — `where_clause`, `order_clause`, `select_sql`,
   `delete_sql`, `select_ids_sql`, `delete_by_ids_sql`, `from_db_datetime`.
3. **Extend `event.py`** — `Event.from_row`.
4. **Add the `read` / `delete` hooks to `backends/base.py`**, then implement them backend by backend: `sqlite.py`,
   `postgres.py`, `mysql.py`,
   `django.py`, `memory.py`, `null.py`, `jsonl.py`.
5. **Add `event_query` / `delete_events` to `api.py`**, export from `__init__.py`
   `__all__`, and update `tests/test_public_api.py:13` which asserts the documented surface.
6. **Tests** (see Validation).
7. **Docs** — `docs/features/read-api.md` and `docs/features/delete-api.md`
   (these are the **first** files under `docs/features/`; the directory does not exist yet, and `AGENTS.md` requires one
   file per feature, so two files, not one). README `## API` gains `### event_query(**filters) -> list[Event]` and
   `### delete_events(**filters) -> int` after `### log_event_safe(...)` and before `### Kill switch`, in the existing
   heading-is-the-signature + three-column-parameter-table style — including the explanation of `data=` as a substring
   match, which the answer to Question 1 makes a documentation requirement, not a nicety. `## Limitations` gains notes
   on the two-statement limited delete, the `limit=100` read default, `data=` case-sensitivity per backend, and
   `jsonl://` being read-only. CHANGELOG
   `## [Unreleased] / ### Added`. Add the deferred `jsonl://` delete to `TODO.md` under `## Delete side`.
8. **Bump to 0.2.0** in `src/eventlog_pro/__about__.py` when releasing, per
   `.claude/plans/005-2026-08-14-releasing-a-new-version.md`.

## Validation

- `tests/test_criteria.py` (new) — pure unit tests for every `order_by` spelling in the table above, the multi-element-
  `set` rejection, `date` vs `datetime`
  coercion on all three timestamp arguments, the
  `created_at` + `from_created_at` conflict, `limit < 1`, unknown field names, and the two `limit` defaults —
  `event_query()` builds `limit=100` and `delete_events()` builds `limit=None` from the same kwargs.
- `tests/test_schema.py` — extend with the generated SQL and parameter tuples per dialect (string assertions, no
  database needed), matching how the existing DDL/insert tests work.
- `tests/test_backend_sqlite.py` — round trip: write rows with the **raw driver** (the suite's standing convention,
  `test_backend_sqlite.py:2-5`), read them back with `event_query()`, then delete with `delete_events()` and verify the
  remaining rows with the raw driver. This keeps reader and writer independent. Cover: exact-column filters,
  day-granularity `created_at`, an inclusive
  `to_created_at` date, `order_by` with two fields and mixed directions,
  `limit`, and delete-oldest-N. Include the default-cap case explicitly: write 150 rows, assert bare `event_query()`
  returns 100 newest-first and `event_query(limit=None)` returns all 150.
- `tests/test_backend_files.py` — `jsonl://` reads back through the same filters; `delete_events()` against a `jsonl://`
  DSN raises `BackendError`.
- `tests/test_backend_postgres.py` / `test_backend_mysql.py` — the same round trip behind the existing
  `EVENTLOG_TEST_*_DSN` gates and
  `pytest.mark.integration`, so CI's `postgres:16` and `mysql:8` jobs cover them. MySQL in particular must confirm the
  naive-UTC `datetime(6)` bound comparison.
- `tests/django_mode/test_models_and_backend.py` — queryset translation returns
  `Event`, `created_at` comes back tz-aware, delete counts match.
- `tests/test_api.py` — unfiltered `delete_events()` raises; `raise_on_error=False`
  does **not** silence `event_query()`.
- `tests/test_public_api.py` — the two new names.
- Lint/type gate, exactly as CI runs it:
  ```powershell
  .\.venv\Scripts\python.exe -m ruff check .
  .\.venv\Scripts\python.exe -m ruff format --check .
  .\.venv\Scripts\python.exe -m mypy
  .\.venv\Scripts\python.exe -m pytest
  ```
  `mypy` is `strict = true` over `src/eventlog_pro`, so the `Criteria` types and the `order_by` union must annotate
  cleanly.
- Manual end-to-end against the built wheel in a clean venv, the way plan 004 smoke-tests: write a handful of events,
  `event_query(app=…, from_created_at=date(...))`, then `delete_events(to_created_at=date(...), limit=2)` and confirm
  the count.

## Risks

- **A delete API in an audit log.** Mitigated by requiring a filter, by `limit`, and by `event_query()` previewing what
  `delete_events()` removes. The `configure(allow_delete=True)` gate from `TODO.md:43-45` is deliberately not built; if
  that turns out to be wanted it is additive.
- **The preview is only exact when `limit` matches.** `event_query()` caps at 100 by default and `delete_events()` does
  not cap at all, so the obvious "check first, then delete" pair silently compares 100 rows against an unbounded delete.
  Mitigated by documentation, by a worked `limit=None` example in both feature docs, and by mentioning it in the
  `delete_events()` docstring rather than only in the README — this is the sharpest edge the answered questions
  introduce.
- **SQLite `created_at` is text.** Range comparison relies on the stored format sorting lexicographically. It does,
  because `to_db_datetime` emits a zero-padded fixed-width `YYYY-MM-DD HH:MM:SS.ffffff` — but any future change to that
  format silently breaks range filters. Add a test that asserts the format explicitly next to the range test.
- **Rows written by something else.** `pel-automation`'s existing table may hold
  `created_at` values written by Django rather than by this package. The parsing side must tolerate a missing
  microsecond component and a `T` separator, not just the exact string this package writes.
- **Limited delete is not atomic** (select-then-delete). Documented, not fixed.
- **`data` round trip** differs per driver (text vs dict). Handled in
  `Event.from_row`, and worth a per-backend assertion.

## Rollout Order

1. `criteria.py` → 2. `schema.py` builders → 3. `Event.from_row` →
4. backend hooks + SQLite → 5. postgres/mysql → 6. django/memory/null/jsonl →
7. `api.py` + `__init__.py` → 8. tests → 9. docs + CHANGELOG → 10. 0.2.0 release per plan 005.

Steps 1-3 are pure and testable with no database; land them first so the backend work has a settled contract to
implement against.

## Rollback

Every change is additive — new module, new functions, new non-abstract backend hooks, new `__all__` entries. Nothing on
the write path changes. Reverting the feature is `git revert` of its commits; no migration, no schema change, no
stored-format change, and 0.1.x callers are unaffected either way.
