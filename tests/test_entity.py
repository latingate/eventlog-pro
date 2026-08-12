"""resolve_entity: all eight branches, and the promise that it never raises.

New coverage, not ported: ``entity=`` has no production callers in the source
app, which makes it the least-tested path in the extraction.
"""

from __future__ import annotations

import pytest

from eventlog_pro.entity import resolve_entity


class FakeMeta:
    app_label = "pel"
    model_name = "customer"


class FakeModel:
    """Duck-typed Django model instance — no Django import involved."""

    _meta = FakeMeta()

    def __init__(self, pk=4711):
        self.pk = pk


class WithHook:
    def __eventlog_entity__(self):
        return ("billing", "invoice", "INV-1")


class WithDictHook:
    def __eventlog_entity__(self):
        return {"entity_app": "billing", "entity_model": "invoice", "entity_id": 9}


class BrokenHook:
    def __eventlog_entity__(self):
        raise RuntimeError("boom")


class Exploding:
    def __getattr__(self, name):
        raise RuntimeError("boom")


class Plain:
    def __init__(self):
        self.id = 12


# 1. None
def test_none_resolves_to_empty():
    assert resolve_entity(None) == ("", "", "")


# 3. __eventlog_entity__
def test_hook_tuple():
    assert resolve_entity(WithHook()) == ("billing", "invoice", "INV-1")


def test_hook_dict():
    assert resolve_entity(WithDictHook()) == ("billing", "invoice", "9")


# 4. duck-typed Django model
def test_django_model_matches_the_source_apps_three_lines():
    assert resolve_entity(FakeModel()) == ("pel", "customer", "4711")


def test_unsaved_model_has_no_id():
    assert resolve_entity(FakeModel(pk=None)) == ("pel", "customer", "")


# 5. dict
@pytest.mark.parametrize(
    "value",
    [
        {"entity_app": "pel", "entity_model": "customer", "entity_id": 1},
        {"app": "pel", "model": "customer", "id": 1},
    ],
)
def test_dicts_with_either_key_set(value):
    assert resolve_entity(value) == ("pel", "customer", "1")


def test_dict_without_recognised_keys():
    assert resolve_entity({"unrelated": 1}) == ("", "", "")


# 6. positional triple
@pytest.mark.parametrize("value", [("pel", "customer", 7), ["pel", "customer", 7]])
def test_three_element_sequences(value):
    assert resolve_entity(value) == ("pel", "customer", "7")


def test_wrong_length_sequence_degrades():
    assert resolve_entity(("pel", "customer")) == ("", "", "")


# 7. generic object
def test_generic_object_uses_module_and_class_name():
    app, model, identifier = resolve_entity(Plain())
    assert model == "plain"
    assert identifier == "12"
    assert app  # the top-level module name of the test file


# 8. scalars
@pytest.mark.parametrize(
    "value,expected", [("INV-1234", "INV-1234"), (42, "42"), (b"bytes", "bytes"), (1.5, "1.5")]
)
def test_scalars_become_the_id(value, expected):
    assert resolve_entity(value) == ("", "", expected)


def test_results_are_truncated():
    app, model, identifier = resolve_entity(("a" * 200, "b" * 200, "c" * 200))
    assert (len(app), len(model), len(identifier)) == (100, 100, 100)


@pytest.mark.parametrize("factory", [BrokenHook, Exploding], ids=["broken-hook", "exploding"])
def test_resolution_never_raises(factory):
    # Instantiated inside the test: an object whose every attribute access
    # raises cannot survive pytest's collection-time introspection.
    assert resolve_entity(factory()) == ("", "", "")
