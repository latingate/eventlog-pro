"""The Django model and the ``django://`` backend."""

from __future__ import annotations

import pytest
from django.apps import apps
from django.contrib.auth.models import User

import eventlog_pro
from eventlog_pro import BackendError, configure, log_event
from eventlog_pro.config import get_backend
from eventlog_pro.contrib.django.models import EventLog

pytestmark = pytest.mark.django_db


def test_app_label_is_not_the_generic_one():
    # A PyPI package must not squat the label "eventlog": a project with its
    # own eventlog app would get ImproperlyConfigured.
    assert EventLog._meta.app_label == "eventlog_pro"
    assert apps.get_app_config("eventlog_pro").name == "eventlog_pro.contrib.django"


def test_db_table_is_explicit():
    assert EventLog._meta.db_table == "eventlog_eventlog"


def test_fields_match_the_source_app():
    fields = {f.name: f for f in EventLog._meta.get_fields()}
    assert set(fields) == {
        "id",
        "created_at",
        "created_by",
        "app",
        "category",
        "sub_category",
        "event_code",
        "event_type",
        "entity_app",
        "entity_model",
        "entity_id",
        "remarks",
        "data",
    }
    for name in (
        "created_by",
        "app",
        "category",
        "sub_category",
        "event_code",
        "event_type",
        "entity_app",
        "entity_model",
        "entity_id",
    ):
        assert fields[name].max_length == 100
    assert fields["created_at"].auto_now_add is True
    assert fields["event_code"].blank is False
    assert fields["data"].get_default() == {}


def test_str_reports_identity():
    instance = EventLog(id=3, app="pel", category="webhook", event_code="OK")
    assert str(instance) == "pk=3 | app=pel | category=webhook | event_code=OK"


def test_app_config_configured_the_core_automatically():
    settings = eventlog_pro.get_settings()
    assert settings.backend == "django"
    assert settings.dsn == "django://default"
    assert settings.auto_create_table is False


def test_log_event_writes_through_the_orm():
    event = log_event(app="a", category="c", event_code="VIA_ORM", data={"n": 1})
    assert isinstance(event, EventLog)
    assert EventLog.objects.get(pk=event.pk).data == {"n": 1}


def test_returned_object_exposes_the_shared_attributes():
    event = log_event(app="a", category="c", event_code="E")
    for attribute in ("id", "app", "event_code", "data", "created_at"):
        assert hasattr(event, attribute)


def test_entity_resolution_uses_the_real_model():
    user = User.objects.create_user("someone")
    event = log_event(app="a", category="c", event_code="E", entity=user)
    assert (event.entity_app, event.entity_model, event.entity_id) == (
        "auth",
        "user",
        str(user.pk),
    )


def test_created_at_is_stamped_by_the_orm():
    event = log_event(app="a", category="c", event_code="E")
    assert event.created_at is not None
    assert event.created_at.tzinfo is not None


def test_truncation_still_applies_in_django_mode():
    event = log_event(app="x" * 200, category="c", event_code="E")
    assert len(event.app) == 100


def test_explicit_alias_is_honoured():
    configure(dsn="django://default")
    log_event(app="a", category="c", event_code="ALIAS")
    assert EventLog.objects.filter(event_code="ALIAS").exists()


def test_unknown_alias_is_a_backend_error():
    configure(dsn="django://nope")
    with pytest.raises(BackendError):
        log_event(app="a", category="c", event_code="E")


def test_backend_never_creates_schema():
    configure(dsn="django://default", auto_create_table=True)
    backend = get_backend()
    backend.create_schema()  # explicitly a no-op
    assert backend.dialect is None
