"""Single source of truth for the package version.

Kept import-side-effect free so ``[tool.hatch.version]`` can read it without
importing the package (and so ``__init__`` can import it without cost).
"""

__version__ = "0.2.0"
