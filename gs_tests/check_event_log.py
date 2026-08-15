"""Manual check of log_event() against the unconfigured default DSN.

Configures nothing on purpose, so the package falls back to DEFAULT_DSN and
emits its one-per-process warning. Run it to see that the warning names the
file the backend actually goes on to create, then check the file appears:

    python check_event_log.py

Writes ./eventlog-pro.db in the working directory (the default since 0.2.0 --
see .claude/plans/007-2026-08-15-default-sqlite-filename-rename.md). Run it
twice: the warning should describe the file differently each time.

Expected on a first run, on stderr:

    eventlog_pro is not configured; falling back to sqlite:///./eventlog-pro.db,
    which created <cwd>\\eventlog-pro.db. Set EVENTLOG_DSN or call
    eventlog_pro.configure(dsn=...) to choose a destination.

and on every run after that, with the file already in place:

    eventlog_pro is not configured; falling back to sqlite:///./eventlog-pro.db,
    which is using the existing <cwd>\\eventlog-pro.db. Set EVENTLOG_DSN or call
    eventlog_pro.configure(dsn=...) to choose a destination.
"""

from eventlog_pro import log_event


def main() -> None:
    print(
        log_event(
            app="api",
            category="webhook",
            sub_category="zoho3",
            event_type="error",
            event_code="SIGNATURE_MISMATCH",
            entity="test",
            remarks="Invalid webhook signature",
            data={"path": "some path", "ip": "this is my ip"},
            created_by="system",
        )
    )


if __name__ == "__main__":
    main()
