"""Settings precedence, re-configuration and the unconfigured-DSN warning."""

from __future__ import annotations

import dataclasses
import logging

import pytest

import eventlog_pro
from eventlog_pro import ConfigurationError, configure, get_settings, reset
from eventlog_pro.config import DEFAULT_DSN, get_backend, is_configured


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
    monkeypatch.chdir(tmp_path)  # the fallback drops events.db in the CWD
    with caplog.at_level(logging.WARNING, logger="eventlog_pro"):
        configure(dsn="memory://")  # not the default -> silent
        get_backend()
        assert caplog.records == []

        reset()
        get_backend()  # falls back to ./events.db
    messages = [r.getMessage() for r in caplog.records]
    assert len(messages) == 1
    assert "events.db" in messages[0]
    assert "EVENTLOG_DSN" in messages[0]


def test_settings_are_immutable():
    settings = get_settings()
    with pytest.raises(dataclasses.FrozenInstanceError):
        settings.dsn = "memory://"
