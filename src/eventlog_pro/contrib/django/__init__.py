"""The Django app: model, migrations, admin.

Add it to ``INSTALLED_APPS``::

    INSTALLED_APPS = [
        ...,
        "eventlog_pro.contrib.django",
    ]

The app label is ``eventlog_pro`` (see :mod:`~eventlog_pro.contrib.django.apps`),
not ``eventlog``, so it cannot collide with a project's own ``eventlog`` app.

``default_app_config`` is deliberately absent — Django removed it in 4.1 and
finds :class:`~eventlog_pro.contrib.django.apps.EventLogProConfig` on its own.
"""
