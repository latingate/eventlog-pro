"""Storage backends.

Each backend is imported lazily, by dotted path, the first time its DSN scheme
is used — so ``import eventlog_pro`` never imports ``psycopg``, ``pymysql`` or
``django``.
"""
