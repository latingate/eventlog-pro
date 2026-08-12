"""Shared fixtures.

The Django half is skipped at collection when Django is not installed, so the
core-only CI job (base install, zero dependencies) passes cleanly.
"""

from __future__ import annotations

import os
import sys
from importlib.util import find_spec

import pytest

sys.path.insert(0, os.path.dirname(__file__))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "django_settings")

# The Django-mode tests live in `django_mode/`, not `django/`: this directory is
# on sys.path, and a directory called `django` would shadow the real package as
# a PEP 420 namespace package — making find_spec("django") below always true.
HAS_DJANGO = find_spec("django") is not None

collect_ignore_glob: list[str] = (
    [] if HAS_DJANGO else ["django_mode", "django_mode/*", "test_schema_parity.py"]
)

#: Environment variables that would otherwise leak the developer's own
#: configuration into every test.
ENV_VARS = (
    "EVENTLOG_DSN",
    "EVENTLOG_TABLE",
    "EVENTLOG_BACKEND",
    "EVENTLOG_SILENT",
    "EVENTLOG_AUTO_CREATE_TABLE",
    "EVENTLOG_DEFAULT_APP",
)


@pytest.fixture(autouse=True)
def clean_state(monkeypatch: pytest.MonkeyPatch) -> None:
    """Reset configuration before and after every test."""
    import eventlog_pro

    for name in ENV_VARS:
        monkeypatch.delenv(name, raising=False)
    eventlog_pro.reset()
    yield
    eventlog_pro.reset()


@pytest.fixture
def sqlite_dsn(tmp_path):
    """A DSN pointing at a fresh SQLite file, plus the path to read it back."""
    path = tmp_path / "events.db"
    return f"sqlite:///{path.as_posix()}", path
