"""Manual check of the log, read and delete APIs (log_event, event_query, delete_events).

Creates a throwaway SQLite database, writes a handful of events into it, then
runs event_query() with different filters and prints what comes back, and
finishes with a preview-then-delete pass through delete_events().

    python check_log_read_delete_api.py             # fresh db each run (deleted first)
    python check_log_read_delete_api.py --keep      # keep the db file to poke at it
    python check_log_read_delete_api.py --db my.db  # use a specific file

Then open a REPL against the same file and try your own filters:

    import eventlog_pro
    eventlog_pro.configure(dsn="sqlite:///./eventlog_check.db")
    eventlog_pro.event_query(app="api")
"""

from __future__ import annotations

import argparse
import os
from datetime import date, datetime, timedelta, timezone

import eventlog_pro
from eventlog_pro import configure, delete_events, event_query, log_event

NOW = datetime.now(timezone.utc)


def seed() -> None:
    """Write a small, deliberately varied set of events."""
    log_event(
        app="api",
        category="webhook",
        sub_category="stripe",
        event_code="RECEIVED",
        event_type="info",
        created_by="alice",
        remarks="first webhook",
        data={"invoice": "INV-1234", "amount": 100},
        entity_app="billing",
        entity_model="Invoice",
        entity_id="1234",
    )
    log_event(
        app="api",
        category="webhook",
        sub_category="stripe",
        event_code="SIGNATURE_MISMATCH",
        event_type="error",
        created_by="alice",
        remarks="bad signature",
        data={"invoice": "INV-9999"},
    )
    log_event(
        app="accounts",
        category="auth",
        event_code="LOGIN_FAILED",
        event_type="warning",
        created_by="bob",
        data={"ip": "10.0.0.7", "attempts": 3},
    )
    log_event(
        app="accounts",
        category="auth",
        event_code="LOGIN_OK",
        event_type="info",
        created_by="bob",
    )
    log_event(
        app="reports",
        category="export",
        event_code="GENERATED",
        event_type="info",
        created_by="cron",
        data=["nightly", "csv"],
    )


def show(title: str, events) -> None:
    print(f"\n=== {title} ===")
    print(f"{len(events)} row(s)")
    for e in events:
        print(
            f"  id={e.id!s:<4} {e.created_at:%Y-%m-%d %H:%M:%S} "
            f"app={e.app:<9} category={e.category:<8} code={e.event_code:<19} "
            f"type={e.event_type:<8} by={e.created_by:<6} data={e.data}"
        )


def expect(title: str, events, count: int) -> bool:
    """Print the result and flag whether it matched what the docs promise."""
    show(title, events)
    ok = len(events) == count
    print("  -> expected", count, "OK" if ok else "*** MISMATCH ***")
    return ok


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default="eventlog_check.db", help="sqlite file to use")
    parser.add_argument("--keep", action="store_true", help="do not delete the db first")
    args = parser.parse_args()

    db_path = os.path.abspath(args.db)
    if not args.keep and os.path.exists(db_path):
        os.remove(db_path)

    print(f"eventlog-pro {eventlog_pro.__version__}")
    print(f"database: {db_path}")

    # Forward slashes keep the DSN valid on Windows.
    configure(dsn=f"sqlite:///{db_path.replace(os.sep, '/')}")

    seed()
    print("seeded 5 events")

    results = [
        expect("everything (default limit=100, newest first)", event_query(), 5),
        expect("app='api'", event_query(app="api"), 2),
        expect("category='auth', event_type='info'",
               event_query(category="auth", event_type="info"), 1),
        expect("created_by='bob'", event_query(created_by="bob"), 2),
        # data= is a SUBSTRING match against the stored JSON text, not equality.
        expect("data='INV-1234' (substring)", event_query(data="INV-1234"), 1),
        expect("data='INV-' (substring, both invoices)", event_query(data="INV-"), 2),
        # Empty string is a real filter: rows whose column is ''.
        expect("sub_category='' (empty, not unfiltered)", event_query(sub_category=""), 3),
        expect("limit=2", event_query(limit=2), 2),
        expect("order_by='app' then '-event_code'",
               event_query(order_by=["app", "-event_code"]), 5),
        expect("today (created_at=date.today())", event_query(created_at=date.today()), 5),
        expect("from yesterday", event_query(from_created_at=NOW - timedelta(days=1)), 5),
        expect("to yesterday (should be empty)",
               event_query(to_created_at=(NOW - timedelta(days=1)).date()), 0),
        expect("entity_model='Invoice'", event_query(entity_model="Invoice"), 1),
        expect("no match", event_query(app="nope"), 0),
    ]

    # id= round trip: read one row, then fetch it back by primary key.
    newest = event_query(limit=1)[0]
    results.append(expect(f"id={newest.id}", event_query(id=newest.id), 1))

    # Errors the docs promise.
    print("\n=== errors that should be raised ===")
    for label, call in (
        ("data={'invoice': ...} (dict, not str)", lambda: event_query(data={"invoice": "x"})),
        ("created_at + from_created_at together",
         lambda: event_query(created_at=date.today(), from_created_at=date.today())),
        ("order_by='drop table'", lambda: event_query(order_by="drop table")),
        ("order_by={'app', 'category'} (a set)",
         lambda: event_query(order_by={"app", "category"})),
        ("bare delete_events() (no filter)", delete_events),
    ):
        try:
            call()
        except Exception as exc:
            print(f"  {label}\n    -> {type(exc).__name__}: {exc}")
            results.append(True)
        else:
            print(f"  {label}\n    -> *** no error raised ***")
            results.append(False)

    # Preview-then-delete, the pairing the delete docs call out.
    print("\n=== delete_events(app='accounts') ===")
    preview = event_query(app="accounts", limit=None)
    print(f"  preview says {len(preview)} row(s) will go")
    deleted = delete_events(app="accounts")
    print(f"  deleted {deleted}")
    results.append(expect("what is left", event_query(), 3))

    failed = results.count(False)
    print(f"\n{len(results) - failed}/{len(results)} checks matched expectations")
    if not args.keep:
        print(f"\nRe-run with --keep to hold on to {db_path} and query it yourself.")


if __name__ == "__main__":
    main()
