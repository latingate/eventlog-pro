"""EVENTLOG_PRO settings merging and the system checks."""

from __future__ import annotations

import pytest
from django.core.checks import run_checks
from django.core.exceptions import ImproperlyConfigured
from django.test import override_settings

from eventlog_pro import ConfigurationError
from eventlog_pro.contrib.django.conf import DEFAULTS, database_alias, get_config, table_name

# Django's own model checks open a connection, so the check tests need the DB.
pytestmark = pytest.mark.django_db


def check_ids(**overrides):
    with override_settings(**overrides):
        return [message.id for message in run_checks()]


def test_defaults_are_complete():
    assert set(DEFAULTS) == {
        "TABLE",
        "DATABASE_ALIAS",
        "ADMIN_ENABLED",
        "ADMIN_READONLY",
        "ADMIN_SEARCH_DATA",
        "ADMIN_LIST_PER_PAGE",
        "RAISE_ON_ERROR",
        "DEFAULT_APP",
        "EVENT_TYPE_STYLES",
    }


def test_settings_are_merged_over_defaults():
    with override_settings(EVENTLOG_PRO={"ADMIN_LIST_PER_PAGE": 10}):
        config = get_config()
    assert config["ADMIN_LIST_PER_PAGE"] == 10
    assert config["TABLE"] == "eventlog_eventlog"  # untouched default


def test_unknown_key_is_rejected_with_the_valid_ones_listed():
    with (
        override_settings(EVENTLOG_PRO={"TABEL": "typo"}),
        pytest.raises(ImproperlyConfigured, match="Unknown EVENTLOG_PRO key"),
    ):
        get_config()


def test_non_dict_setting_is_rejected():
    with (
        override_settings(EVENTLOG_PRO=["nope"]),
        pytest.raises(ImproperlyConfigured, match="must be a dict"),
    ):
        get_config()


def test_missing_setting_falls_back_to_defaults():
    with override_settings(EVENTLOG_PRO=None):
        assert get_config() == DEFAULTS


def test_table_name_is_validated():
    with (
        override_settings(EVENTLOG_PRO={"TABLE": "not a table"}),
        pytest.raises(ConfigurationError),
    ):
        table_name()


def test_helpers():
    assert table_name() == "eventlog_eventlog"
    assert database_alias() == "default"


def test_a_clean_configuration_produces_no_messages():
    assert run_checks() == []


def test_unknown_alias_is_an_error():
    assert "eventlog_pro.E001" in check_ids(EVENTLOG_PRO={"DATABASE_ALIAS": "replica"})


def test_table_changed_after_import_is_a_warning():
    ids = check_ids(EVENTLOG_PRO={"TABLE": "somewhere_else"})
    assert "eventlog_pro.W001" in ids


def test_core_and_django_table_disagreement_is_a_warning():
    import eventlog_pro

    eventlog_pro.configure(table="audit_events")
    try:
        assert "eventlog_pro.W002" in [message.id for message in run_checks()]
    finally:
        eventlog_pro.reset()


def test_typo_in_the_settings_dict_is_reported_as_a_check():
    assert "eventlog_pro.E003" in check_ids(EVENTLOG_PRO={"NOPE": 1})
