"""The public surface, and the promise that the base install stays dependency-free."""

from __future__ import annotations

import subprocess
import sys

import pytest

import eventlog_pro


def test_documented_names_are_exported():
    expected = {
        "log_event",
        "log_event_safe",
        "event_query",
        "delete_events",
        "configure",
        "get_settings",
        "reset",
        "Event",
        "Backend",
        "register_backend",
        "EventLogError",
        "ConfigurationError",
        "BackendError",
        "UnknownSchemeError",
        "__version__",
    }
    assert expected <= set(eventlog_pro.__all__)
    for name in eventlog_pro.__all__:
        assert hasattr(eventlog_pro, name), name


def test_version_is_a_release_number():
    parts = eventlog_pro.__version__.split(".")
    assert len(parts) == 3
    assert all(part.isdigit() for part in parts)


def test_exception_hierarchy():
    assert issubclass(eventlog_pro.ConfigurationError, eventlog_pro.EventLogError)
    assert issubclass(eventlog_pro.BackendError, eventlog_pro.EventLogError)
    assert issubclass(eventlog_pro.UnknownSchemeError, eventlog_pro.ConfigurationError)


def test_importing_the_package_pulls_in_no_optional_dependency():
    """A subprocess, because this test session has Django imported already."""
    code = (
        "import sys, eventlog_pro;"
        "leaked = {'django', 'psycopg', 'psycopg2', 'pymysql', 'MySQLdb'} & set(sys.modules);"
        "assert not leaked, leaked;"
        "print('clean')"
    )
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "clean"


def test_package_ships_a_py_typed_marker():
    from importlib.resources import files

    assert (files("eventlog_pro") / "py.typed").is_file()


def test_every_package_directory_has_an_init():
    """No implicit namespace packages — the trap that broke the source app.

    ``eventlog/utils/`` had no ``__init__.py`` and survived only on PEP 420,
    which breaks ``find_packages()``, mypy resolution and frozen bundling.
    """
    from pathlib import Path

    root = Path(eventlog_pro.__file__).parent
    missing = [
        str(directory.relative_to(root))
        for directory in root.rglob("*")
        if directory.is_dir()
        and directory.name != "__pycache__"
        and not (directory / "__init__.py").is_file()
    ]
    assert not missing, missing


@pytest.mark.filterwarnings("ignore::DeprecationWarning")
def test_deprecated_shim_still_works():
    from eventlog_pro.utils.eventlog_utilities import log_event

    eventlog_pro.configure(dsn="memory://")
    assert log_event(app="a", category="c", event_code="SHIM").id == 1


def test_deprecated_shim_warns():
    import eventlog_pro.utils.eventlog_utilities as shim

    with pytest.warns(DeprecationWarning, match="import from eventlog_pro directly"):
        assert callable(shim.log_event)
    with pytest.warns(DeprecationWarning):
        assert callable(shim.log_event_safe)


def test_shim_does_not_invent_names():
    import eventlog_pro.utils.eventlog_utilities as shim

    with pytest.raises(AttributeError):
        getattr(shim, "no_such_thing")  # noqa: B009 - the point is the lookup
