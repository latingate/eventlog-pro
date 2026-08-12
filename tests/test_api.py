"""log_event / log_event_safe: signature, failure policy, entity handling."""

from __future__ import annotations

import logging

import pytest

import eventlog_pro
from eventlog_pro import build_event, configure, log_event, log_event_safe
from eventlog_pro.config import get_backend


@pytest.fixture(autouse=True)
def memory_backend():
    configure(dsn="memory://")
    return get_backend()


def test_records_every_field(memory_backend):
    event = log_event(
        app="auto.pel",
        category="webhook",
        sub_category="zoho",
        event_type="error",
        event_code="SIGNATURE_MISMATCH",
        remarks="nope",
        data={"k": "v"},
        created_by="system",
    )
    assert memory_backend.events == [event]
    assert event.id == 1
    assert (event.app, event.category, event.sub_category) == ("auto.pel", "webhook", "zoho")
    assert (event.event_type, event.event_code) == ("error", "SIGNATURE_MISMATCH")
    assert (event.remarks, event.data, event.created_by) == ("nope", {"k": "v"}, "system")


def test_category_and_event_code_stay_required():
    with pytest.raises(TypeError):
        log_event(app="a", category="c")
    with pytest.raises(TypeError):
        log_event(app="a", event_code="E")


def test_app_falls_back_to_default_app():
    configure(dsn="memory://", default_app="auto.pel")
    assert log_event(category="c", event_code="E").app == "auto.pel"


def test_created_by_none_becomes_empty():
    assert log_event(app="a", category="c", event_code="E", created_by=None).created_by == ""


def test_app_is_arbitrary_text_and_never_validated():
    # Callers pass "auto.pel", which is not a Django app label. Validating it
    # would break every existing call site.
    assert log_event(app="auto.pel", category="c", event_code="E").app == "auto.pel"


def test_explicit_entity_kwargs_bypass_resolution():
    event = log_event(
        app="a",
        category="c",
        event_code="E",
        entity={"entity_app": "ignored", "entity_model": "ignored", "entity_id": "ignored"},
        entity_app="pel",
        entity_model="customer",
        entity_id="7",
    )
    assert (event.entity_app, event.entity_model, event.entity_id) == ("pel", "customer", "7")


def test_partial_entity_kwargs_override_only_what_they_name():
    event = log_event(
        app="a", category="c", event_code="E", entity=("pel", "customer", "1"), entity_id="99"
    )
    assert (event.entity_app, event.entity_model, event.entity_id) == ("pel", "customer", "99")


def test_build_event_does_not_write(memory_backend):
    event = build_event(app="a", category="c", event_code="E")
    assert event.id is None
    assert memory_backend.events == []


def test_log_event_raises_by_default():
    configure(dsn="nope://nowhere")
    with pytest.raises(eventlog_pro.UnknownSchemeError):
        log_event(app="a", category="c", event_code="E")


def test_log_event_safe_never_raises(caplog):
    configure(dsn="nope://nowhere")
    with caplog.at_level(logging.ERROR, logger="eventlog_pro"):
        assert log_event_safe(app="a", category="c", event_code="E") is None
    assert caplog.records and caplog.records[0].exc_info


def test_log_event_safe_survives_bad_keywords():
    assert log_event_safe(nonsense=1) is None


def test_log_event_safe_does_not_log_the_payload(caplog):
    configure(dsn="nope://nowhere")
    with caplog.at_level(logging.ERROR, logger="eventlog_pro"):
        log_event_safe(app="a", category="c", event_code="E", data={"password": "hunter2"})
    assert "hunter2" not in caplog.text


def test_kill_switch_makes_log_event_silent(caplog):
    configure(dsn="nope://nowhere", raise_on_error=False)
    with caplog.at_level(logging.ERROR, logger="eventlog_pro"):
        assert log_event(app="a", category="c", event_code="E") is None
    assert caplog.records


def test_kill_switch_via_env(monkeypatch):
    monkeypatch.setenv("EVENTLOG_SILENT", "1")
    monkeypatch.setenv("EVENTLOG_DSN", "nope://nowhere")
    eventlog_pro.reset()
    assert log_event(app="a", category="c", event_code="E") is None


def test_null_dsn_disables_logging_without_erroring():
    configure(dsn="null://")
    assert log_event(app="a", category="c", event_code="E").id is None
    assert get_backend().dropped == 1


def test_base_exceptions_are_never_swallowed(monkeypatch):
    def explode(self, event):
        raise KeyboardInterrupt

    configure(dsn="memory://", raise_on_error=False)
    monkeypatch.setattr(type(get_backend()), "write", explode)
    with pytest.raises(KeyboardInterrupt):
        log_event(app="a", category="c", event_code="E")
    with pytest.raises(KeyboardInterrupt):
        log_event_safe(app="a", category="c", event_code="E")
