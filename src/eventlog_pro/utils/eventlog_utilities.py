"""Deprecated shim for ``eventlog.utils.eventlog_utilities``.

Migrating an existing call site is a one-token edit::

    from eventlog.utils.eventlog_utilities import log_event      # before
    from eventlog_pro.utils.eventlog_utilities import log_event  # works
    from eventlog_pro import log_event                           # preferred

Importing a name from here emits a :class:`DeprecationWarning`. Scheduled for
removal in 1.0.
"""

from __future__ import annotations

import warnings
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover - re-exported for type checkers only
    from ..api import log_event, log_event_safe

__all__ = ["log_event", "log_event_safe"]

_MESSAGE = (
    "eventlog_pro.utils.eventlog_utilities is deprecated; "
    "import from eventlog_pro directly (from eventlog_pro import {name}). "
    "This shim will be removed in 1.0."
)


def __getattr__(name: str) -> Any:
    # The names are resolved here rather than imported at module level so the
    # warning actually fires: module __getattr__ only runs on a globals() miss.
    if name in __all__:
        warnings.warn(_MESSAGE.format(name=name), DeprecationWarning, stacklevel=2)
        from .. import api

        return getattr(api, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
