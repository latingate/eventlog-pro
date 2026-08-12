"""The ``EventLog`` model.

Ported from ``pel-automation/eventlog/models.py``: the twelve fields are
byte-identical in name, type, ``max_length``, ``blank`` and ``default``. What
was added around them:

* an explicit ``db_table``, which is the mechanism by which the core backends
  and the ORM share one table;
* the three indexes the source app lacked (applied by ``0002_add_indexes``);
* a real ``__str__`` — the source had one commented out, with a ``categoty``
  typo that is not preserved.
"""

from __future__ import annotations

from django.db import models

from ...schema import index_name
from .conf import table_name

__all__ = ["EventLog"]

_TABLE = table_name()


class EventLog(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.CharField(max_length=100, blank=True, default="")

    app = models.CharField(max_length=100, default="")
    category = models.CharField(max_length=100, default="")
    sub_category = models.CharField(max_length=100, blank=True, default="")
    event_code = models.CharField(max_length=100)
    event_type = models.CharField(
        max_length=100,
        blank=True,
        default="",
        help_text="e.g. 'error', 'info', 'warning', 'debug', 'info' etc.",
    )

    entity_app = models.CharField(max_length=100, blank=True, default="")
    entity_model = models.CharField(max_length=100, blank=True, default="")
    entity_id = models.CharField(max_length=100, blank=True, default="")

    remarks = models.TextField(blank=True, default="")
    data = models.JSONField(blank=True, default=dict)

    class Meta:
        db_table = _TABLE
        verbose_name = "Event Log"
        verbose_name_plural = "Event Logs"
        indexes = [
            models.Index(fields=["-created_at"], name=index_name(_TABLE, "created")),
            models.Index(
                fields=["app", "category", "event_code"],
                name=index_name(_TABLE, "app_cat"),
            ),
            models.Index(
                fields=["entity_app", "entity_model", "entity_id"],
                name=index_name(_TABLE, "entity"),
            ),
        ]

    def __str__(self) -> str:
        return (
            f"pk={self.id} | app={self.app} | category={self.category} "
            f"| event_code={self.event_code}"
        )
