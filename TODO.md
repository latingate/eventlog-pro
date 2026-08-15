# TODO

Ideas for versions after 0.1.0. **Nothing here is a defect** — 0.1.0 works as
documented, and everything below is either a deliberate omission or a known
rough edge, recorded so it is not rediscovered from scratch.

Nothing here is scheduled. Order within a section is rough priority.

## Read side

The read API itself is **done** — `event_query()`, built per
[`.claude/plans/006-2026-08-14-read-and-delete-api.md`](.claude/plans/006-2026-08-14-read-and-delete-api.md)
and documented in [`docs/features/read-api.md`](docs/features/read-api.md). What
it was going to be the foundation for is still open:

- **A CLI** — `eventlog-pro tail --dsn … --follow`, via `[project.scripts]`.
  Useful for ops, and can stay dependency-free now that the query layer exists.
- **A dashboard for pure mode** — the equivalent of the Django admin for people
  not running Django. Needs a server and templates, so it would have to be an
  optional `[web]` extra; the base install must stay dependency-free.

Worth doing only if consumers actually write to SQLite or PostgreSQL *without*
Django. For `pel-automation` the question is moot — it runs Django.

Smaller things the read API left on the table:

- **No `offset` / pagination and no `count()`.** A caller wanting page two has
  to raise `limit` and slice. Adding `offset` is easy; deciding whether it
  should exist without a stable sort guarantee is the actual question.
- **`data=` is a text scan** with no index behind it, and its case-sensitivity
  follows the backend's collation (case-insensitive on MySQL, sensitive
  elsewhere). Structural JSON querying — key lookup, containment, path
  expressions — is deliberately absent.

## Delete side

The delete API is **done** — `delete_events()`, documented in
[`docs/features/delete-api.md`](docs/features/delete-api.md). Of the three
things that needed settling first, one was built and two were not:

- **Require a filter.** Built: a bare `delete_events()` raises, and `limit` /
  `order_by` do not count as filters.
- **Opt-in gating.** *Not built.* `configure(allow_delete=True)`, default
  `False`, so a compromised or careless caller cannot erase history in a
  deployment that never intended it. Requiring a filter was judged enough for
  now; this stays available and is purely additive.
- **The Django admin.** *Unchanged.* `ADMIN_READONLY` still forbids add and
  change but permits delete, so the admin and the API disagree about how sacred
  deletion is. Worth making consistent either way.

Also deferred:

- **A limited delete is not atomic** — it selects ids and then deletes them,
  because `DELETE ... LIMIT` is MySQL-only. Fine for retention batching, wrong
  for "delete exactly this set". Closing that would mean a transaction per
  backend.

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
