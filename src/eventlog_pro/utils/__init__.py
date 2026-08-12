"""Compatibility shims for the in-repo ``eventlog`` app this package replaced.

A real ``__init__.py``, unlike the source app's ``eventlog/utils/``, which had
none and survived only on PEP 420 implicit namespace packages — that breaks
``find_packages()``, mypy resolution and frozen bundling.
"""
