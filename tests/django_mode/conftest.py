"""Django-mode fixtures."""

from __future__ import annotations

import pytest
from django.apps import apps


@pytest.fixture(autouse=True)
def django_mode():
    """Re-apply ``AppConfig.ready()`` after the root ``reset()`` fixture.

    The root fixture clears all configuration, which in Django mode is exactly
    what ``ready()`` had set up — so without this every test here would quietly
    fall back to the default SQLite DSN.
    """
    apps.get_app_config("eventlog_pro").ready()
    return None
