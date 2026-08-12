"""Create the event table.

The fields are the source app's 0001-0004 collapsed into their end state, in
the model's declaration order. ``db_table`` is explicit — that is the mechanism
by which the core backends and the ORM share a table.

The table name is read from ``EVENTLOG_PRO["TABLE"]`` **at import time**, the
standard settings-dependent migration pattern (``django-celery-results`` and
``django-axes`` do the same). Consequence: changing ``TABLE`` later will not
generate a rename migration. ``checks.py`` raises ``eventlog_pro.W001`` when the
setting and the built model disagree.
"""

from django.db import migrations, models

from eventlog_pro.contrib.django.conf import table_name

TABLE = table_name()


class Migration(migrations.Migration):
    initial = True

    dependencies: list[tuple[str, str]] = []

    operations = [
        migrations.CreateModel(
            name="EventLog",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("created_by", models.CharField(blank=True, default="", max_length=100)),
                ("app", models.CharField(default="", max_length=100)),
                ("category", models.CharField(default="", max_length=100)),
                ("sub_category", models.CharField(blank=True, default="", max_length=100)),
                ("event_code", models.CharField(max_length=100)),
                (
                    "event_type",
                    models.CharField(
                        blank=True,
                        default="",
                        help_text="e.g. 'error', 'info', 'warning', 'debug', 'info' etc.",
                        max_length=100,
                    ),
                ),
                ("entity_app", models.CharField(blank=True, default="", max_length=100)),
                ("entity_model", models.CharField(blank=True, default="", max_length=100)),
                ("entity_id", models.CharField(blank=True, default="", max_length=100)),
                ("remarks", models.TextField(blank=True, default="")),
                ("data", models.JSONField(blank=True, default=dict)),
            ],
            options={
                "verbose_name": "Event Log",
                "verbose_name_plural": "Event Logs",
                "db_table": TABLE,
            },
        ),
    ]
