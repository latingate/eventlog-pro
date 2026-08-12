"""The admin page.

Ported from ``pel-automation/eventlog/admin.py`` essentially as-is: the same
form widget, ``list_display``, ``list_filter``, ``fieldsets``, ``ordering``,
``date_hierarchy``, the pretty-printed JSON block and the entity link. The
deliberate changes:

* the duplicate ``from django.contrib import admin`` and the unused
  ``from django.apps import apps`` are gone;
* ``pretty_event_type``'s six-branch if/elif is a dict lookup, rendering the
  same output, overridable via ``EVENTLOG_PRO["EVENT_TYPE_STYLES"]``;
* ``search_fields`` includes ``"data"`` only when ``ADMIN_SEARCH_DATA`` is on
  (it is by default) — on PostgreSQL that is an unindexable full-table scan,
  and on MySQL 8 searching a JSON column can raise;
* registration happens at the bottom under ``if ADMIN_ENABLED:`` instead of the
  ``@admin.register`` decorator, so ``EventLogAdmin`` stays importable and
  subclassable when the page is switched off;
* ``ADMIN_READONLY`` (**on by default**) disables add and change. This is a
  behaviour change from the source app, listed in the CHANGELOG — an editable
  audit log is not an audit log. Delete is still permitted.
"""

from __future__ import annotations

import json

from django import forms
from django.contrib import admin
from django.contrib.admin.utils import quote
from django.http import HttpRequest
from django.urls import NoReverseMatch, reverse
from django.utils.html import format_html
from django.utils.timezone import localtime

from .conf import get_config
from .models import EventLog

__all__ = ["EventLogAdminForm", "EventLogAdmin"]

_CONFIG = get_config()


class EventLogAdminForm(forms.ModelForm):
    class Meta:
        model = EventLog
        fields = "__all__"
        widgets = {
            "remarks": forms.Textarea(
                attrs={
                    "rows": 2,
                    "cols": 80,
                }
            ),
        }


def _search_fields() -> tuple[str, ...]:
    fields = (
        "id",
        "created_by",
        "app",
        "category",
        "sub_category",
        "event_type",
        "event_code",
        "entity_app",
        "entity_model",
        "entity_id",
        "remarks",
    )
    # Kept for parity with the source app, but switchable: past a million rows
    # this is what makes the changelist search time out. A GIN index does not
    # help, because the query is a LIKE.
    return (*fields, "data") if _CONFIG["ADMIN_SEARCH_DATA"] else fields


class EventLogAdmin(admin.ModelAdmin):
    form = EventLogAdminForm
    list_display = (
        "id",
        "pretty_created_at",
        "pretty_event_type",
        "pretty_event_code",
        "created_by",
        "app",
        "category",
        "sub_category",
        "entity_app",
        "entity_model",
        "entity_id",
        "entity_admin_link",
    )
    list_filter = (
        "app",
        "category",
        "sub_category",
        "event_type",
        "event_code",
        "entity_app",
        "entity_model",
        "created_at",
        "created_by",
    )

    search_fields = _search_fields()

    ordering = ("-created_at",)

    readonly_fields = (
        "pretty_created_at",
        "entity_admin_link",
        "pretty_data",
    )

    date_hierarchy = "created_at"

    list_per_page = _CONFIG["ADMIN_LIST_PER_PAGE"]

    fieldsets = (
        (
            "Event Info",
            {
                "fields": (
                    "pretty_created_at",
                    "event_code",
                    "created_by",
                    "app",
                    "category",
                    "sub_category",
                    "event_type",
                )
            },
        ),
        (
            "Details",
            {
                "fields": (
                    "remarks",
                    "pretty_data",
                )
            },
        ),
        (
            "Related Entity",
            {
                "fields": (
                    "entity_app",
                    "entity_model",
                    "entity_id",
                    "entity_admin_link",
                )
            },
        ),
    )

    def has_add_permission(self, request: HttpRequest) -> bool:
        if _CONFIG["ADMIN_READONLY"]:
            return False
        return super().has_add_permission(request)

    def has_change_permission(self, request: HttpRequest, obj: EventLog | None = None) -> bool:
        if _CONFIG["ADMIN_READONLY"]:
            return False
        return super().has_change_permission(request, obj)

    @admin.display(description="Event Code", ordering="event_code")
    def pretty_event_code(self, obj: EventLog) -> str:
        return format_html("<b>{}</b>", obj.event_code)

    @admin.display(description="Event Type", ordering="event_type")
    def pretty_event_type(self, obj: EventLog) -> str:
        event_type = obj.event_type.lower()
        styles = _CONFIG["EVENT_TYPE_STYLES"]
        if event_type not in styles:
            # Preserved quirk: an unrecognised type keeps its original casing,
            # while every known one is upper-cased.
            return format_html("{}", obj.event_type)
        style = styles[event_type]
        if not style:
            return format_html("{}", obj.event_type.upper())
        return format_html("<div style='{}'>{}</div>", style, obj.event_type.upper())

    @admin.display(description="Creation Date & Time", ordering="created_at")
    def pretty_created_at(self, obj: EventLog) -> str:
        if not obj or not obj.created_at:
            return ""

        dt = localtime(obj.created_at)
        return dt.strftime("%d/%m/%Y %H:%M:%S")

    @admin.display(description="JSON Data")
    def pretty_data(self, obj: EventLog) -> str:
        if not obj or obj.data is None:
            return ""

        pretty = json.dumps(
            obj.data,
            indent=4,
            ensure_ascii=False,
            sort_keys=True,
            default=str,
        )

        return format_html(
            "<pre style='white-space: pre-wrap; font-family: monospace;'>{}</pre>",
            pretty,
        )

    @admin.display(description="Entity URL")
    def entity_admin_link(self, obj: EventLog) -> str:
        if not obj.entity_app or not obj.entity_model or not obj.entity_id:
            return "-"

        try:
            url = reverse(
                f"admin:{obj.entity_app}_{obj.entity_model}_change",
                args=[quote(obj.entity_id)],
            )
        except NoReverseMatch:
            return "Admin page not registered"

        return format_html('<a href="{}" target="_blank">Open entity</a>', url)


if _CONFIG["ADMIN_ENABLED"]:
    admin.site.register(EventLog, EventLogAdmin)
