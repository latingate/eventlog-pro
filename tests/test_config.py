"""Settings precedence, re-configuration and the unconfigured-DSN warning."""

from __future__ import annotations

import dataclasses
import logging
from pathlib import Path

import pytest

import eventlog_pro
from eventlog_pro import ConfigurationError, configure, get_settings, reset
from eventlog_pro.config import (
    DEFAULT_DSN,
    LEGACY_DEFAULT_FILENAME,
    get_backend,
    is_configured,
)
from eventlog_pro.dsn import parse_dsn


def test_defaults():
    settings = get_settings()
    assert settings.dsn == DEFAULT_DSN
    assert settings.table == "eventlog_eventlog"
    assert settings.raise_on_error is True
    assert settings.auto_create_table is True
    assert settings.backend is None


def test_explicit_configure_wins_over_env(monkeypatch):
    monkeypatch.setenv("EVENTLOG_DSN", "memory://")
    configure(dsn="null://")
    assert get_settings().dsn == "null://"


def test_env_wins_over_defaults(monkeypatch):
    monkeypatch.setenv("EVENTLOG_DSN", "memory://")
    monkeypatch.setenv("EVENTLOG_TABLE", "audit_events")
    monkeypatch.setenv("EVENTLOG_DEFAULT_APP", "auto.pel")
    settings = get_settings()
    assert (settings.dsn, settings.table, settings.default_app) == (
        "memory://",
        "audit_events",
        "auto.pel",
    )


def test_silent_env_var_is_inverted(monkeypatch):
    monkeypatch.setenv("EVENTLOG_SILENT", "1")
    assert get_settings().raise_on_error is False


@pytest.mark.parametrize("value,expected", [("0", True), ("false", True), ("no", True)])
def test_silent_off_keeps_raising(monkeypatch, value, expected):
    monkeypatch.setenv("EVENTLOG_SILENT", value)
    assert get_settings().raise_on_error is expected


def test_bad_boolean_env_var_is_reported(monkeypatch):
    monkeypatch.setenv("EVENTLOG_AUTO_CREATE_TABLE", "maybe")
    with pytest.raises(ConfigurationError, match="not a boolean"):
        get_settings()


def test_unknown_setting_is_rejected():
    with pytest.raises(ConfigurationError, match="Unknown setting"):
        configure(dsnn="memory://")


def test_bad_table_name_is_rejected_at_configure_time():
    with pytest.raises(ConfigurationError):
        configure(table="not a table")


def test_reconfiguring_closes_the_live_backend():
    configure(dsn="memory://")
    first = get_backend()
    eventlog_pro.log_event(app="a", category="c", event_code="ONE")
    configure(dsn="memory://")
    second = get_backend()
    assert second is not first
    assert second.events == []


def test_reset_forgets_everything(monkeypatch):
    configure(dsn="memory://")
    assert is_configured()
    reset()
    assert not is_configured()
    assert get_settings().dsn == DEFAULT_DSN


def test_dsn_query_option_overrides_the_table():
    configure(dsn="memory://?table=audit_events")
    assert get_backend().table == "audit_events"


def test_backend_override_beats_the_dsn_scheme():
    configure(dsn="sqlite:///./unused.db", backend="null")
    backend = get_backend()
    assert type(backend).__name__ == "NullBackend"


def test_unconfigured_dsn_warns_once_naming_the_file(caplog, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)  # the fallback drops the file in the CWD
    with caplog.at_level(logging.WARNING, logger="eventlog_pro"):
        configure(dsn="memory://")  # not the default -> silent
        get_backend()
        assert caplog.records == []

        reset()
        get_backend()  # falls back to ./eventlog-pro.db
    messages = [r.getMessage() for r in caplog.records]
    assert len(messages) == 1
    assert "eventlog-pro.db" in messages[0]
    assert "EVENTLOG_DSN" in messages[0]


def test_the_warning_names_the_file_the_backend_actually_creates(tmp_path, monkeypatch):
    """DEFAULT_DSN and the warned-about path must not drift apart."""
    monkeypatch.chdir(tmp_path)
    reset()
    get_backend().write(eventlog_pro.build_event(category="c", event_code="E"))
    created = [p.name for p in tmp_path.iterdir() if p.suffix == ".db"]
    assert created == [Path(parse_dsn(DEFAULT_DSN).database).name]


def test_an_old_events_db_is_named_and_left_alone(caplog, tmp_path, monkeypatch):
    """Upgrading into the 0.2.0 rename must not silently abandon the old log."""
    monkeypatch.chdir(tmp_path)
    legacy = tmp_path / LEGACY_DEFAULT_FILENAME
    legacy.write_bytes(b"not really a database")

    reset()
    with caplog.at_level(logging.WARNING, logger="eventlog_pro"):
        get_backend().write(eventlog_pro.build_event(category="c", event_code="E"))

    messages = [r.getMessage() for r in caplog.records]
    assert len(messages) == 2
    assert LEGACY_DEFAULT_FILENAME in messages[1]
    assert "eventlog-pro.db" in messages[1]
    assert legacy.read_bytes() == b"not really a database"  # untouched


def test_no_legacy_warning_when_there_is_no_old_file(caplog, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    reset()
    with caplog.at_level(logging.WARNING, logger="eventlog_pro"):
        get_backend()
    assert len(caplog.records) == 1


def test_settings_are_immutable():
    settings = get_settings()
    with pytest.raises(dataclasses.FrozenInstanceError):
        settings.dsn = "memory://"
