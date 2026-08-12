"""DSN parsing."""

from __future__ import annotations

import pytest

from eventlog_pro import ConfigurationError, parse_dsn
from eventlog_pro.dsn import redact


@pytest.mark.parametrize(
    "dsn,scheme,database",
    [
        ("sqlite:///./events.db", "sqlite", "./events.db"),
        ("sqlite:////var/log/events.db", "sqlite", "/var/log/events.db"),
        ("sqlite:///C:/tmp/events.db", "sqlite", "C:/tmp/events.db"),
        ("sqlite://:memory:", "sqlite", ":memory:"),
        ("sqlite:///:memory:", "sqlite", ":memory:"),
        ("jsonl:///./events.jsonl", "jsonl", "./events.jsonl"),
        ("postgresql://u:p@h:5432/db", "postgresql", "db"),
        ("mysql://root@localhost/pel", "mysql", "pel"),
        ("django://replica", "django", "replica"),
        ("django://", "django", ""),
        ("memory://", "memory", ""),
        ("null://", "null", ""),
    ],
)
def test_scheme_and_database(dsn, scheme, database):
    parsed = parse_dsn(dsn)
    assert (parsed.scheme, parsed.database) == (scheme, database)


def test_credentials_host_and_port():
    parsed = parse_dsn("postgresql://user:pa%40ss@db.example.com:5433/events")
    assert parsed.username == "user"
    assert parsed.password == "pa@ss"
    assert parsed.host == "db.example.com"
    assert parsed.port == 5433


def test_driver_suffix_is_split_off():
    parsed = parse_dsn("postgresql+psycopg://u@h/db")
    assert (parsed.scheme, parsed.driver) == ("postgresql", "psycopg")


def test_query_options():
    parsed = parse_dsn("sqlite:///./e.db?table=audit&timeout=30&wal=yes&blank=")
    assert parsed.option("table") == "audit"
    assert parsed.int_option("timeout") == 30
    assert parsed.bool_option("wal") is True
    assert parsed.bool_option("missing", True) is True
    assert parsed.option("blank") == ""


def test_bad_int_option_is_a_configuration_error():
    with pytest.raises(ConfigurationError, match="must be an integer"):
        parse_dsn("sqlite:///./e.db?timeout=soon").int_option("timeout")


@pytest.mark.parametrize("dsn", ["", "   ", "not-a-dsn", None, 42])
def test_unusable_dsns_are_rejected(dsn):
    with pytest.raises(ConfigurationError):
        parse_dsn(dsn)


def test_invalid_port_is_reported_clearly():
    with pytest.raises(ConfigurationError, match="invalid port"):
        parse_dsn("postgresql://u@h:notaport/db")


def test_password_is_redacted_in_messages():
    assert redact("postgresql://u:hunter2@h/db") == "postgresql://u:***@h/db"
    assert "hunter2" not in str(parse_dsn("postgresql://u:hunter2@h/db"))
    assert redact("sqlite:///./e.db") == "sqlite:///./e.db"
