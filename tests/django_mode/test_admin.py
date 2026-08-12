"""The admin page, rendered through the test client."""

from __future__ import annotations

import pytest
from django.contrib import admin as django_admin
from django.contrib.auth.models import User
from django.test import Client

from eventlog_pro import log_event
from eventlog_pro.contrib.django.admin import EventLogAdmin
from eventlog_pro.contrib.django.models import EventLog

pytestmark = pytest.mark.django_db


@pytest.fixture
def client():
    User.objects.create_superuser("admin", "admin@example.com", "pw")
    client = Client()
    client.login(username="admin", password="pw")
    return client


@pytest.fixture
def model_admin():
    return EventLogAdmin(EventLog, django_admin.site)


@pytest.fixture
def event():
    return log_event(
        app="auto.pel",
        category="webhook",
        sub_category="zoho",
        event_type="error",
        event_code="SIGNATURE_MISMATCH",
        remarks="Invalid webhook signature",
        data={"path": "/hook", "n": 1},
        created_by="system",
    )


def test_model_is_registered():
    assert EventLog in django_admin.site._registry


def test_changelist_renders(client, event):
    response = client.get("/admin/eventlog_pro/eventlog/")
    assert response.status_code == 200
    assert "SIGNATURE_MISMATCH" in response.content.decode()


def test_change_page_renders(client, event):
    response = client.get(f"/admin/eventlog_pro/eventlog/{event.pk}/change/")
    body = response.content.decode()
    assert response.status_code == 200
    assert "Event Info" in body and "Details" in body and "Related Entity" in body
    assert "<pre style='white-space: pre-wrap; font-family: monospace;'>" in body


def test_date_hierarchy_drilldown_works(client, event):
    # A wrongly stored created_at breaks exactly this.
    response = client.get(f"/admin/eventlog_pro/eventlog/?created_at__year={event.created_at.year}")
    assert response.status_code == 200
    assert "SIGNATURE_MISMATCH" in response.content.decode()


def test_search_works(client, event):
    response = client.get("/admin/eventlog_pro/eventlog/?q=SIGNATURE")
    assert response.status_code == 200
    assert "SIGNATURE_MISMATCH" in response.content.decode()


def test_admin_is_readonly_by_default(client, event):
    assert client.get("/admin/eventlog_pro/eventlog/add/").status_code == 403
    assert (
        client.get(f"/admin/eventlog_pro/eventlog/{event.pk}/change/").context[
            "has_change_permission"
        ]
        is False
    )


def test_delete_is_still_allowed(client, event, model_admin):
    assert model_admin.has_delete_permission(_request(client)) is True


def _request(client):
    request = client.get("/admin/eventlog_pro/eventlog/").wsgi_request
    return request


@pytest.mark.parametrize(
    "event_type,expected",
    [
        ("error", "<div style='color: red; font-weight: bold;'>ERROR</div>"),
        ("success", "<div style='color: green; font-weight: bold;'>SUCCESS</div>"),
        ("warning", "WARNING"),
        ("info", "INFO"),
        ("notification", "NOTIFICATION"),
        ("debug", "DEBUG"),
    ],
)
def test_event_type_rendering_matches_the_source_app(model_admin, event_type, expected):
    assert model_admin.pretty_event_type(EventLog(event_type=event_type)) == expected


def test_unknown_event_type_keeps_its_original_casing(model_admin):
    # Preserved quirk from the source app; a 0.2 candidate, not a 0.1 change.
    assert model_admin.pretty_event_type(EventLog(event_type="Weird")) == "Weird"


def test_event_code_is_bold(model_admin):
    assert model_admin.pretty_event_code(EventLog(event_code="X")) == "<b>X</b>"


def test_created_at_is_formatted_in_local_time(model_admin, event):
    rendered = model_admin.pretty_created_at(event)
    assert len(rendered) == 19 and rendered[2] == "/" and rendered[10] == " "


def test_created_at_of_an_unsaved_row_is_blank(model_admin):
    assert model_admin.pretty_created_at(EventLog()) == ""


def test_pretty_data_pretty_prints(model_admin):
    # format_html escapes the JSON's quotes, which is the point of using it.
    rendered = model_admin.pretty_data(EventLog(data={"b": 1, "a": 2}))
    assert "&quot;a&quot;: 2" in rendered
    assert rendered.index("&quot;a&quot;") < rendered.index("&quot;b&quot;")  # sort_keys


def test_pretty_data_handles_unserialisable_values(model_admin):
    from datetime import datetime

    assert "2026" in model_admin.pretty_data(EventLog(data={"when": datetime(2026, 1, 1)}))


def test_entity_link_reverses_to_the_target_admin(model_admin):
    user = User.objects.create_user("linked")
    instance = EventLog(entity_app="auth", entity_model="user", entity_id=str(user.pk))
    assert f'href="/admin/auth/user/{user.pk}/change/"' in model_admin.entity_admin_link(instance)


def test_entity_link_without_an_entity(model_admin):
    assert model_admin.entity_admin_link(EventLog()) == "-"


def test_entity_link_for_an_unregistered_model(model_admin):
    instance = EventLog(entity_app="nope", entity_model="nah", entity_id="1")
    assert model_admin.entity_admin_link(instance) == "Admin page not registered"


def test_list_per_page_and_search_fields_follow_settings():
    assert EventLogAdmin.list_per_page == 50
    assert "data" in EventLogAdmin.search_fields
    assert EventLogAdmin.ordering == ("-created_at",)
    assert EventLogAdmin.date_hierarchy == "created_at"


def test_remarks_widget_is_a_small_textarea():
    from eventlog_pro.contrib.django.admin import EventLogAdminForm

    widget = EventLogAdminForm().fields["remarks"].widget
    assert widget.attrs["rows"] == 2 and widget.attrs["cols"] == 80
