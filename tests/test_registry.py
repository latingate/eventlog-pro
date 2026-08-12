"""Backend registry: lazy resolution and custom backends."""

from __future__ import annotations

from typing import ClassVar

import pytest

import eventlog_pro
from eventlog_pro import Backend, ConfigurationError, UnknownSchemeError, register_backend
from eventlog_pro.registry import get_backend_class, known_schemes, unregister_backend


class DummyBackend(Backend):
    schemes = ("dummy",)
    written: ClassVar[list] = []

    def write(self, event):
        self.written.append(event)
        event.id = len(self.written)
        return event


@pytest.fixture
def dummy():
    register_backend("dummy", DummyBackend)
    DummyBackend.written = []
    yield DummyBackend
    unregister_backend("dummy")


def test_built_in_schemes_are_registered():
    assert {"sqlite", "postgresql", "mysql", "jsonl", "memory", "null", "django"} <= set(
        known_schemes()
    )


def test_lazy_resolution_returns_the_class():
    from eventlog_pro.backends.sqlite import SQLiteBackend

    assert get_backend_class("sqlite") is SQLiteBackend
    assert get_backend_class("SQLITE") is SQLiteBackend


def test_unknown_scheme_lists_what_is_available():
    with pytest.raises(UnknownSchemeError) as info:
        get_backend_class("redis")
    assert "redis" in str(info.value)
    assert "sqlite" in str(info.value)


def test_custom_backend_can_be_registered_and_used(dummy):
    eventlog_pro.configure(dsn="dummy://somewhere")
    event = eventlog_pro.log_event(app="a", category="c", event_code="CUSTOM")
    assert event.id == 1
    assert dummy.written[0].event_code == "CUSTOM"


def test_custom_backend_can_be_registered_by_dotted_path():
    register_backend("dotted", "eventlog_pro.backends.memory:MemoryBackend")
    try:
        from eventlog_pro.backends.memory import MemoryBackend

        assert get_backend_class("dotted") is MemoryBackend
    finally:
        unregister_backend("dotted")


def test_registering_a_non_backend_is_rejected():
    register_backend("bogus", "eventlog_pro.event:Event")
    try:
        with pytest.raises(ConfigurationError, match="not a Backend subclass"):
            get_backend_class("bogus")
    finally:
        unregister_backend("bogus")


def test_registering_nonsense_is_rejected():
    with pytest.raises(ConfigurationError):
        register_backend("x", 42)
    with pytest.raises(ConfigurationError):
        register_backend("", DummyBackend)


def test_missing_attribute_names_the_module():
    register_backend("missing", "eventlog_pro.backends.memory:NoSuchBackend")
    try:
        with pytest.raises(ConfigurationError, match="has no attribute"):
            get_backend_class("missing")
    finally:
        unregister_backend("missing")


def test_unregister_is_forgiving():
    unregister_backend("never-existed")
