# TODO

Ideas for versions after 0.1.0. **Nothing here is a defect** — 0.1.0 works as
documented, and everything below is either a deliberate omission or a known
rough edge, recorded so it is not rediscovered from scratch.

Nothing here is scheduled. Order within a section is rough priority.

## Read side

Planned in [`.claude/plans/006-2026-08-14-read-and-delete-api.md`](.claude/plans/006-2026-08-14-read-and-delete-api.md),
together with the delete API below.

0.1.0 is **write-only** outside Django: `Backend` exposes `write`,
`ensure_schema`, `create_schema`, `ddl` and `close`, and there is no query API,
no CLI and no viewer. Django users get the admin at
`/admin/eventlog_pro/eventlog/`; pure-Python users read the table with whatever
they already use — `psql`, DBeaver, `sqlite3`, or `Get-Content` for `jsonl://`.

- **A read API** — something like `query(app=…, since=…, limit=…) -> list[Event]`,
  backend-agnostic. This is the foundation the other two need, and the smallest
  useful piece on its own.
- **A CLI** — `eventlog-pro tail --dsn … --follow`, via `[project.scripts]`.
  Useful for ops, and can stay dependency-free.
- **A dashboard for pure mode** — the equivalent of the Django admin for people
  not running Django. Needs a server and templates, so it would have to be an
  optional `[web]` extra; the base install must stay dependency-free.

Worth doing only if consumers actually write to SQLite or PostgreSQL *without*
Django. For `pel-automation` the question is moot — it runs Django.

## Delete side

Planned in [`.claude/plans/006-2026-08-14-read-and-delete-api.md`](.claude/plans/006-2026-08-14-read-and-delete-api.md).
Of the three questions below, that plan adopts the first (require a filter) and
deliberately leaves the other two — `allow_delete` gating and the admin
inconsistency — open and unbuilt.

- **A delete API** — `delete(app=…, before=…, …) -> int`, taking the same
  filters as the read API above and returning the number of rows removed. Build
  it on the read API rather than beside it, so one filter implementation serves
  both and a caller can preview with `query()` exactly what `delete()` will
  remove. Retention ("drop anything older than 90 days") is the obvious first
  use.

Three things to settle before writing it, because an audit log that can quietly
erase itself is a different product from one that cannot:

- **Require a filter.** An unfiltered `delete()` that truncates the table is a
  footgun; make the no-argument case raise rather than delete everything.
- **Decide whether it is opt-in.** Something like
  `configure(allow_delete=True)`, default `False`, so a compromised or careless
  caller cannot erase history in a deployment that never intended it.
- **Mind the Django admin.** `ADMIN_READONLY` already forbids add and change but
  permits delete, so deletion is not currently treated as sacred — worth making
  the two consistent either way.

## Notifications

- **`notify_email` and `notify_name` arguments on `log_event()`** — optional
  kwargs that send an email when that event is recorded, e.g.
  `log_event(..., notify_email="ops@example.com", notify_name="Ops")`.

This one needs the most design care of anything on this list, because it cuts
against the package's two firmest properties:

- **The base install has no dependencies.** Sending mail via `smtplib` keeps
  that, but anything richer (SES, SendGrid, Django's mail backend) has to be an
  optional extra. Django mode should almost certainly delegate to
  `django.core.mail` rather than open its own SMTP connection.
- **`log_event()` must stay fast and must not fail the caller.** It sits on
  webhook paths. A synchronous SMTP round trip inside the write path would add
  latency to every notified event and a new way for a logging call to raise —
  the exact failure `log_event_safe` exists to prevent. Send after the row is
  committed, never before, and swallow send failures the way `log_event_safe`
  swallows write failures.
- **Where does the config live?** SMTP host, credentials and a from-address are
  deployment settings, not call-site arguments — so the call site would supply
  only the recipient, with transport configured through `configure()` /
  `EVENTLOG_*` / `EVENTLOG_PRO`.

Open questions: are `notify_email` / `notify_name` stored as columns (a schema
change, and therefore a migration and a break in the DDL parity with
`pel-automation`'s existing table) or used transiently and discarded? Is
throttling needed so a webhook storm cannot send a thousand emails? Would a
generic hook — `on_event(callback)` — serve better than email specifically, with
email as one supplied callback?

## Data model

- `event_type` casing is inconsistent: recognised values render upper-cased,
  unrecognised ones keep their original casing. Preserved verbatim from the
  source app, quirk and all.
- No `choices` or enum on `event_type`, and no validation on `app`.
- `jsonl://` leaves `id` as `None`.
- Changing `EVENTLOG_PRO["TABLE"]` after import neither moves the table nor
  generates a rename; the `eventlog_pro.W001` system check reports the drift.

## Performance

- No connection pooling, batching or async. The documented stance is to point
  the DSN at pgbouncer, or use `django://` and let Django's `CONN_MAX_AGE` own
  the connection.

## Ecosystem

- `contrib/flask/` is possible with the current layout; nobody has asked.
- An optional `[dotenv]` extra that calls `load_dotenv()` explicitly — never on
  import. `.env` already works without it (see README, *`.env` files*), so this
  is convenience only, and it must not touch the base install.

## Defaults and messages

- **Rename the default SQLite file from `events.db` to `eventlog-pro.db`.**
  `DEFAULT_DSN` is `sqlite:///./events.db` (`config.py:30`), which is generic
  enough to collide with another tool's file in the same directory; the new name
  matches the package. Roughly 25 references outside `.venv/`: `config.py:30` and `:191`,
  `dsn.py:9-10, 100, 148`, `backends/sqlite.py:3`, `__init__.py:8`,
  `README.md:79, 125, 184, 197`, `ci.yml:184`, six spots in `tests/`, and the
  historical mentions in plan 001 — leave the plans alone, they record what was
  true at the time. This changes behaviour for anyone relying on the default, so
  it belongs in a minor release with a CHANGELOG note, not a patch.
- **The fallback warning claims it will create a file that may already exist.**
  Second and later runs print "…which will create C:\…\events.db" about a file
  it is merely reusing — verified 2026-08-14. `_warn_if_default_dsn`
  (`config.py:180-192`) fires before the backend is built and never checks for
  the file. Fix: record whether the path existed, then log after
  `ensure_schema()` succeeds — "created X" or "using the existing X" — so the
  message is accurate in both cases and only appears once the write path
  actually worked. A second "database created" message was considered and
  rejected: one warning per process is already the right amount of noise, and
  success is observable from the file itself. `tests/test_config.py:99-109`
  asserts on this text and would need updating.

## Housekeeping

- Local development resolves to Django 6.1 (the extra is `Django>=4.2`) while CI
  covers 4.2 and 5.2. Pinning the dev environment to 5.2 would match
  `pel-automation` production more closely. Both 5.2.17 and 6.1 have been
  verified by hand against the built wheel.
- CI covers `postgres:16` and `mysql:8`. PostgreSQL 18.3 has been verified by
  hand; adding 18 to the CI matrix would make that continuous rather than a
  one-off.
- Every backend has now been exercised from the built wheel against a real
  server — SQLite, PostgreSQL 18.3 and MySQL 8.4.11 — but only by hand, once, on
  one machine. Only CI makes that continuous.
