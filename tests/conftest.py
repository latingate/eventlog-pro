"""Shared fixtures.

The Django half is skipped at collection when Django is not installed, so the
core-only CI job (base install, zero dependencies) passes cleanly.
"""

from __future__ import annotations

import os
import re
import sys
from importlib.util import find_spec
from pathlib import Path

import pytest

sys.path.insert(0, os.path.dirname(__file__))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "django_settings")


def _fail_on_a_stale_install() -> None:
    """Refuse to run the suite against a copy of the package nobody edited.

    ``src/`` is not on ``sys.path``, so ``import eventlog_pro`` resolves to
    whatever is installed. A non-editable install left over from an earlier
    version therefore shadows the working tree *in complete silence* — the
    suite passes, having exercised code nobody wrote. This happened once, and
    surfaced only because a new test happened to assert new behaviour.

    CI installs non-editable deliberately, so that it tests the built package;
    this compares versions rather than paths, which is true in both modes. It
    cannot catch drift *within* one version — an editable install is still the
    right way to develop — but it catches the case that actually bit.
    """
    about = Path(__file__).resolve().parent.parent / "src" / "eventlog_pro" / "__about__.py"
    if not about.is_file():
        return  # installed without the source tree; nothing to compare against
    match = re.search(r'__version__\s*=\s*"([^"]+)"', about.read_text(encoding="utf-8"))
    if match is None:  # pragma: no cover - only if __about__.py is restructured
        return

    import eventlog_pro

    if eventlog_pro.__version__ != match.group(1):
        raise RuntimeError(
            f"tests would run against eventlog_pro {eventlog_pro.__version__} from "
            f"{eventlog_pro.__file__}, but {about} says {match.group(1)}. An installed "
            'copy is shadowing src/. Fix it with:  pip install -e ".[dev]"'
        )


_fail_on_a_stale_install()

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
