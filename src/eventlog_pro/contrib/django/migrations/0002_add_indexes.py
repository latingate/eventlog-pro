"""Add the three indexes the source app never had.

Separate from ``0001`` on purpose: an existing install adopts its table with
``migrate eventlog_pro --fake-initial`` and then *really applies* this one.

On a large table each ``CREATE INDEX`` takes a lock proportional to the row
count. On PostgreSQL, create them by hand with ``CREATE INDEX CONCURRENTLY``
first and fake this migration instead.
"""

from django.db import migrations, models

from eventlog_pro.contrib.django.conf import table_name
from eventlog_pro.schema import index_name

TABLE = table_name()


class Migration(migrations.Migration):
    dependencies = [
        ("eventlog_pro", "0001_initial"),
    ]

    operations = [
        migrations.AddIndex(
            model_name="eventlog",
            index=models.Index(fields=["-created_at"], name=index_name(TABLE, "created")),
        ),
        migrations.AddIndex(
            model_name="eventlog",
            index=models.Index(
                fields=["app", "category", "event_code"],
                name=index_name(TABLE, "app_cat"),
            ),
        ),
        migrations.AddIndex(
            model_name="eventlog",
            index=models.Index(
                fields=["entity_app", "entity_model", "entity_id"],
                name=index_name(TABLE, "entity"),
            ),
        ),
    ]
