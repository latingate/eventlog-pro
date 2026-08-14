# Smoke-test `eventlog-pro` from a throwaway consumer project, installed from git

Status: active
Owner: Gal Sarig
Last updated: 2026-08-14

Runs **before** [002-2026-08-12-remaining-work-and-decisions.md](002-2026-08-12-remaining-work-and-decisions.md).
Prove the package works when it is installed like a dependency rather than
imported from `src/`, while a mistake is still free — a PyPI release cannot be
replaced, only yanked.

## Goal

Install `eventlog-pro` from `git+https://github.com/latingate/eventlog-pro` into
a clean virtual environment belonging to a project that is not this repository,
and confirm both modes work end to end: pure-Python against SQLite, and Django
against the ORM with migrations and admin.

## Scope

**In scope**

- A throwaway consumer project outside this repository, with its own venv.
- Installing from git, with the `[django]` extra.
- Verifying the *installed* artefact: migrations and `py.typed` present in
  `site-packages`, no editable/path install, version matches `__about__.py`.
- A pure-mode write/read-back, and a Django-mode migrate/write/read-back/admin.
- That the `[postgres]` and `[mysql]` extras resolve and their backend modules
  import from an installed distribution (step 3b) — imports only, no server.
- The installed wheel against a **real PostgreSQL server** (step 5b), added
  2026-08-14. CI proves the Postgres code works; this proves the built artefact
  does, which nothing else covered.

**Out of scope**

- Running SQL against a real MySQL server. `ci.yml:97-120` runs 9 tests against
  a `mysql:8` container, and no MySQL server is available here. The MySQL half
  of step 3b (the extra resolves, the module imports) is the coverage this plan
  offers.
- Publishing anything — that is plan 002.
- The `pel-automation` cutover — that is plan 003.

## Assumptions

- Everything is pushed to `latingate/eventlog-pro`. Verified on 2026-08-14:
  anonymous `git ls-remote` returns `refs/heads/main` at `fd6bea4`, matching
  local `HEAD`. `fd6bea4` adds only plan and rule files on top of `56d190d`;
  `src/` is identical between them. Re-pin if you commit source changes before
  testing.
- Python 3.12 and git are on `PATH`.
- The commands below are PowerShell, matching the working environment. The
  Python is identical on any platform.
- No PyPI account is needed for any step here. That account is only required by
  plan 002.

## Open Questions

Each carries a recommendation. Reply with the number of the option you want.

**Question 1.** Is `latingate/eventlog-pro` public or private? A private
repository cannot be installed over anonymous `git+https://` — pip will hang on
a credential prompt or fail with a 404 that looks like a missing repository.
Decide before step 2.
1. Public — use `git+https://` exactly as written below.
2. Private — use `git+ssh://git@github.com/latingate/eventlog-pro.git` with a key already loaded.
3. Other. Enter your own answer or follow up question.
**Recommendation:** 1 — settled by fact, not preference: anonymous `git ls-remote https://github.com/latingate/eventlog-pro` succeeded on 2026-08-14, which only a public repository allows.
**Answer:** 1

**Question 2.** Pin the install to which revision? Decide during step 2.
1. The commit SHA `fd6bea4` — reproducible, and exactly what plan 002 will tag.
2. `main` — whatever is newest at install time.
3. Tag `v0.1.0` first, then install that — makes this a full release rehearsal.
4. Other. Enter your own answer or follow up question.
**Recommendation:** 1 — a SHA cannot drift between the install and the result, and creating the real tag before the smoke test spends the one tag name you get.
**Answer:** 1

**Question 3.** Which modes to exercise? Decide during step 4.
1. Both — pure SQLite (step 4) and Django (step 5).
2. Pure SQLite only.
3. Django only.
4. Other. Enter your own answer or follow up question.
**Recommendation:** 1 — they are different code paths with different failure modes. Django is the one `pel-automation` will actually use; pure mode is the one a stranger installing from PyPI hits first.
**Answer:** 1

## Steps

Every path is relative to the throwaway project. **Do not create it inside this
repository** — see Risks.

1. **Create the project and its venv.**
   ```powershell
   New-Item -ItemType Directory -Force "$env:USERPROFILE\PycharmProjects\eventlog-consumer-smoke"
   Set-Location "$env:USERPROFILE\PycharmProjects\eventlog-consumer-smoke"
   py -3.12 -m venv .venv
   .\.venv\Scripts\Activate.ps1
   python -m pip install --upgrade pip
   ```

2. **Install from git, with the Django extra.** PEP 508 direct-reference form —
   the extra goes on the *name*, before the `@`:
   ```powershell
   pip install --no-cache-dir "eventlog-pro[django] @ git+https://github.com/latingate/eventlog-pro@fd6bea4"
   ```
   `--no-cache-dir` matters: pip caches git clones by URL and revision, and a
   cached clone is exactly what would hide a "the fix was never pushed" mistake.
   This builds a wheel from the repository through hatchling — the same build
   path PyPI would serve, which is what makes the test meaningful.

3. **Verify what actually got installed**, before running any of it.
   ```powershell
   pip show eventlog-pro
   python -c "import eventlog_pro, pathlib; print(eventlog_pro.__version__); print(pathlib.Path(eventlog_pro.__file__).parent)"
   python -c "import eventlog_pro, pathlib; root = pathlib.Path(eventlog_pro.__file__).parent; [print(p.relative_to(root)) for p in [root/'py.typed', root/'contrib/django/migrations/0001_initial.py', root/'contrib/django/migrations/0002_add_indexes.py'] if p.exists()]"
   python -c "import django; print('django', django.get_version())"
   ```
   The printed path must be under `.venv\Lib\site-packages`, **not** under
   `PycharmProjects\eventlog-pro\src`. All three files must print. The version
   must be `0.1.0`.

3b. **Check the `[postgres]` and `[mysql]` extras resolve.** Nothing else tests
   this: CI's database jobs install the repository checkout with the dev extra,
   never `eventlog-pro[postgres]` from a distribution, and CI's packaging job
   (`ci.yml:150-183`) installs the wheel base-only and asserts the optional
   dependencies are *absent*. The extras are three lines in `pyproject.toml:36-40`,
   so the risk is small — but it is unmeasured, and this costs a minute and no
   server.
   ```powershell
   pip install --no-cache-dir "eventlog-pro[postgres,mysql] @ git+https://github.com/latingate/eventlog-pro@fd6bea4"
   python -c "import psycopg, pymysql; print('drivers', psycopg.__version__, pymysql.__version__)"
   python -c "from eventlog_pro.backends.postgres import PostgresBackend; from eventlog_pro.backends.mysql import MySQLBackend; print('backend modules import')"
   python -c "from eventlog_pro import known_schemes; print(known_schemes())"
   ```
   `known_schemes()` must list all ten: `django`, `jsonl`, `mariadb`, `memory`,
   `mysql`, `null`, `postgres`, `postgresql`, `sqlite`, `sqlite3`. This proves
   the extras install and the modules import; it proves nothing about SQL, which
   is what CI's container jobs are for.

   Do this **after** step 3, not before — installing the extras first would mean
   step 3 no longer verifies that a `[django]`-only install stays lean.

4. **Pure mode — write a row and read it back without the ORM.** Save as
   `smoke_pure.py`:
   ```python
   import sqlite3

   import eventlog_pro
   from eventlog_pro import log_event

   eventlog_pro.configure(dsn="sqlite:///./smoke.db", default_app="smoke")

   event = log_event(
       category="webhook",
       event_code="OK",
       event_type="success",
       sub_category="zoho",
       remarks="installed from git",
       data={"payload": {"id": 42}},
   )
   print("wrote:", event.id, event.app, event.event_code, event.created_at)

   rows = sqlite3.connect("smoke.db").execute(
       "SELECT id, app, category, event_code, data FROM eventlog_eventlog"
   ).fetchall()
   print("read back:", rows)
   assert len(rows) == 1 and rows[0][0] == event.id
   print("PURE MODE OK")
   ```
   ```powershell
   python smoke_pure.py
   ```
   This also exercises the table being auto-created (`auto_create_table`
   defaults to `True`) and `default_app` filling in `app` when the call omits
   it.

4b. **Strict pure-Python check, in a venv that has nothing else in it.** Step 4
   runs inside the `[django]` venv, so it proves the SQLite path works but not
   that the base install stands alone. A second project settles that:
   ```powershell
   $pure = "$env:USERPROFILE\PycharmProjects\eventlog-pure-smoke"
   py -3.12 -m venv "$pure\.venv"
   & "$pure\.venv\Scripts\python.exe" -m pip install --no-cache-dir "eventlog-pro @ git+https://github.com/latingate/eventlog-pro@fd6bea4"
   & "$pure\.venv\Scripts\python.exe" -m pip list --format=freeze   # only eventlog-pro and pip
   ```
   The script there (`smoke_pure.py`, kept in that project) asserts, in order:
   no optional dependency is importable; a SQLite write read back through the
   stdlib; the return type is the `Event` dataclass, not `EventLog`; the table
   was auto-created; a second write appends; `sqlite://:memory:`; `jsonl://`;
   `null://`; nested paths created by `sqlite.py:57-59`; `postgresql://` with no
   driver raising a `ConfigurationError` that names the extra; `log_event_safe`
   returning `None` on that same failure; and an unknown scheme raising
   `UnknownSchemeError` listing all ten known schemes.

   A clean run prints one line per check and ends with `PURE MODE OK`, exit
   code 0. There is deliberately **no traceback in the output**: `log_event_safe`
   logs the exception it swallows (`api.py:175`), and printed raw that looks
   exactly like a crash, so the script installs a capturing handler and asserts
   against the record instead — `ERROR` level, `exc_info` present, the event
   identified, and the `data` payload redacted per `api.py:179`. Suppressing the
   noise made the check stronger, not weaker.

   **Always invoke the interpreter by path**, never a bare `python`:
   ```powershell
   .\.venv\Scripts\python.exe smoke_pure.py
   ```
   PyCharm activates the *project's* venv when a terminal opens, and `cd` does
   not change that — so a terminal opened on `eventlog-pro` keeps that venv
   active after moving here, the prompt still reads `(.venv)`, and bare `python`
   imports `eventlog_pro` from the repository's `src/` tree. Every result would
   then describe the working copy rather than the installed wheel. `smoke_pure.py`
   guards against this: it prints `sys.executable` and the import path, and exits
   with `WRONG INTERPRETER` if the package did not come from `site-packages`.

5. **Django mode — migrate, write through the ORM, open the admin.** Three
   files:

   `settings.py`
   ```python
   SECRET_KEY = "smoke-test-only-not-a-real-secret"
   DEBUG = True
   ALLOWED_HOSTS = ["127.0.0.1", "localhost"]
   ROOT_URLCONF = "urls"
   USE_TZ = True

   INSTALLED_APPS = [
       "django.contrib.admin",
       "django.contrib.auth",
       "django.contrib.contenttypes",
       "django.contrib.sessions",
       "django.contrib.messages",
       "django.contrib.staticfiles",
       "eventlog_pro.contrib.django",
   ]

   MIDDLEWARE = [
       "django.contrib.sessions.middleware.SessionMiddleware",
       "django.middleware.common.CommonMiddleware",
       "django.contrib.auth.middleware.AuthenticationMiddleware",
       "django.contrib.messages.middleware.MessageMiddleware",
   ]

   DATABASES = {
       "default": {"ENGINE": "django.db.backends.sqlite3", "NAME": "django_smoke.db"}
   }
   STATIC_URL = "static/"

   TEMPLATES = [{
       "BACKEND": "django.template.backends.django.DjangoTemplates",
       "APP_DIRS": True,
       "OPTIONS": {"context_processors": [
           # `request` is required by the admin sidebar — without it,
           # `manage.py check` reports admin.W411.
           "django.template.context_processors.request",
           "django.contrib.auth.context_processors.auth",
           "django.contrib.messages.context_processors.messages",
       ]},
   }]

   EVENTLOG_PRO = {
       "DATABASE_ALIAS": "default",
       "ADMIN_READONLY": True,
       "ADMIN_SEARCH_DATA": True,
   }
   ```

   `urls.py`
   ```python
   from django.contrib import admin
   from django.urls import path

   urlpatterns = [path("admin/", admin.site.urls)]
   ```

   `manage.py`
   ```python
   import os
   import sys

   if __name__ == "__main__":
       os.environ.setdefault("DJANGO_SETTINGS_MODULE", "settings")
       from django.core.management import execute_from_command_line

       execute_from_command_line(sys.argv)
   ```

   Then:
   ```powershell
   python manage.py check
   python manage.py migrate
   python manage.py shell -c "from eventlog_pro import log_event; e = log_event(app='smoke', category='webhook', event_code='OK', event_type='success', data={'x': 1}); print('wrote', e.pk, type(e).__name__)"
   python manage.py shell -c "from eventlog_pro.contrib.django.models import EventLog; print(EventLog.objects.count(), EventLog.objects.first().data)"
   ```
   Note the deliberate asymmetry documented at `backends/django.py:7-11`: in
   Django mode `log_event` returns the **model instance**, so `type(e).__name__`
   prints `EventLog`, not `Event`.

   `python manage.py check` is doing real work here — the app ships system
   checks (`contrib/django/checks.py`), including `eventlog_pro.W001` for a
   `TABLE` setting that drifted from the model's `db_table`.

5b. **The installed wheel against a real PostgreSQL server.** Everything else
   here is SQLite, and every other Postgres check in the project runs the test
   suite from a source checkout. This is the built artefact against a live
   server. It needs a disposable database — never an existing one, because the
   script drops its table first to exercise the DDL path:
   ```sql
   CREATE ROLE eventlog_smoke LOGIN PASSWORD 'smoke';
   CREATE DATABASE smoke OWNER eventlog_smoke;
   ```
   ```powershell
   .\.venv\Scripts\python.exe smoke_postgres.py   # dsn is at the top of the file
   ```
   `smoke_postgres.py` checks: table and the three indexes created from nothing;
   column types matching the `postgresql` dialect in `schema.py:107-114`; `id`
   as `GENERATED BY DEFAULT AS IDENTITY` rather than `bigserial` (Django ≥ 4.1
   parity); `RETURNING` populating `id` and a timezone-aware `created_at` inside
   the surrounding wall-clock window; a raw-SQL read-back with no `eventlog_pro`
   involved; `jsonb` round-tripping nested lists, dicts and booleans; a second
   backend against the live table proving `ensure_schema` is idempotent;
   truncation of a 250-character `event_code` to 100; and a `jsonb @>`
   containment query, which only succeeds if the column is genuinely `jsonb`.

   Teardown, once it passes:
   ```sql
   DROP DATABASE smoke;
   DROP ROLE eventlog_smoke;
   ```

6. **Admin, in a browser.**
   ```powershell
   python manage.py createsuperuser
   python manage.py runserver
   ```
   Open `http://127.0.0.1:8000/admin/eventlog_pro/eventlog/`. Confirm the row
   lists, the date hierarchy drills down, and — because `ADMIN_READONLY` is
   `True` — there is **no "Add event log" button** and the change form's fields
   are read-only. That last one is the behaviour change plan 003's question 2 is
   about, so this is the cheapest place to see it and decide.

7. **Record the outcome** in this file's Validation section, then start plan
   002. If anything failed, fix it in `eventlog-pro`, push, and repeat step 2
   with the new SHA.

## Validation

**Executed 2026-08-14, Python 3.12.10, Windows. All checks passed.** The project
is at `~\PycharmProjects\eventlog-consumer-smoke`, left in place for the browser
check in step 6.

The installs above actually pulled **`f155821`**; the plan was re-pinned to
`fd6bea4` afterwards, when that commit appeared on `origin/main`. The results
carry over unchanged because `git diff --stat f155821 fd6bea4` touches only the
four files under `.claude/plans/` — `src/`, `pyproject.toml` and the workflows
are byte-identical, so the wheel built from either commit is the same. Re-run
step 2 onwards if a later commit changes anything the package actually ships.

| Check | Expected | Result |
|---|---|---|
| `pip show eventlog-pro` | version `0.1.0`; `Location` inside the smoke project's `.venv` | pass — `0.1.0`, and `Requires:` is empty, so the base install pulls nothing |
| `eventlog_pro.__file__` | under `.venv\Lib\site-packages\eventlog_pro`, never under this repository's `src/` | pass — `…eventlog-consumer-smoke\.venv\Lib\site-packages\eventlog_pro` |
| Step 3 file listing | all three of `py.typed`, `0001_initial.py`, `0002_add_indexes.py` print | pass — all three |
| Step 3b extras | `psycopg` and `pymysql` import; both backend modules import; `known_schemes()` lists all ten | pass — psycopg 3.3.4, pymysql 2.2.8, all ten schemes |
| `python smoke_pure.py` | prints `PURE MODE OK`; `smoke.db` exists and holds exactly one row | pass — table auto-created, `default_app` filled `app`, JSON round-tripped |
| Step 4b base-only venv | `pip list` shows only `eventlog-pro` and `pip`; every assertion passes | pass — `PURE MODE OK`, exit 0, no traceback, in `~\PycharmProjects\eventlog-pure-smoke` |
| `log_event_safe` failure logging | logged at `ERROR` with `exc_info`, event identified, payload redacted | pass — verified against the captured record, not by eye |
| `python manage.py check` | `System check identified no issues` | pass, after adding `django.template.context_processors.request` — see below |
| `python manage.py migrate` | applies `eventlog_pro.0001_initial` and `0002_add_indexes` | pass on both Django versions |
| ORM write | prints a pk and the class name `EventLog` | pass — `pk=1`, `EventLog`, confirming the documented asymmetry |
| ORM read | count is `1`, and `data` round-trips as a dict, not a string | pass — `{'x': 1}`, type `dict` |
| Admin list page | row visible, date hierarchy works, **no add button** | pass — driven through Django's test client in `smoke_admin.py`, see below |
| Step 5b real PostgreSQL | all nine checks pass against a live server | pass — `POSTGRES OK` against **PostgreSQL 18.3**, a version CI does not cover (`ci.yml` uses `postgres:16`) |
| `EventLog._meta.db_table` | `eventlog_eventlog` | pass — the name plan 003's `--fake-initial` adoption depends on |

Three things worth carrying forward:

- **Both Django versions were exercised.** The `[django]` extra is `Django>=4.2`,
  so a fresh install resolved to **6.1** — a version CI does not cover — and
  everything passed. The suite was then re-run pinned to **5.2.17**, which is
  what `pel-automation` production runs, and everything passed there too. This
  is the Deferred item in plan 002 about the dev environment resolving to 6.1:
  it is now known to work, not merely untested.
- **The admin was verified programmatically**, not just by eye. `smoke_admin.py`
  logs in as a superuser and asserts through the test client: changelist 200
  with the row present, `has_add_permission() is False` and
  `has_delete_permission() is True` (exactly the `ADMIN_READONLY` contract),
  no "Add event log" button in the HTML, `data` present in `search_fields`
  (`ADMIN_SEARCH_DATA`), the `created_at__year` drill-down 200 with the row, and
  the change form 200. Step 6 is now confirmation by eye, not the only evidence.
- **PostgreSQL is now verified end to end from the artefact.** Step 5b ran
  against PostgreSQL **18.3** — CI uses `postgres:16`, so this adds a version
  rather than repeating one. The DDL, the identity column and `jsonb` all behave
  identically. Combined with CI's 16 coverage and the MySQL 8 job, the only
  untested combination left is the wheel against a live **MySQL** server, which
  no machine here has.
- **The base install genuinely stands alone.** Step 4b's venv contains
  `eventlog-pro` and `pip`, nothing else — `pip show` lists no `Requires:` — and
  the full pure-mode surface works there, including the two error paths a
  consumer is most likely to hit first: a missing driver, and an unknown scheme.
  Both messages name the fix.
- **`admin.W411` was this plan's bug, not the package's.** The `settings.py`
  template above originally omitted
  `django.template.context_processors.request`, which the admin sidebar
  requires. Fixed in the template above; nothing in `eventlog_pro` changed.

## Risks

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| `import eventlog_pro` resolves to the repository's `src/` rather than the installed package, so the test proves nothing | **high — this happened on 2026-08-14** | high | the projects live outside the repository, but that is not enough: an already-activated venv survives `cd`, so always invoke `.\.venv\Scripts\python.exe` by path. Step 3 prints the import path, and `smoke_pure.py` exits with `WRONG INTERPRETER` rather than a bare `AssertionError` |
| A cached pip git clone serves an older revision | medium | medium | `--no-cache-dir`, and pin to a SHA rather than `main` |
| The repository is private and `git+https://` fails or hangs on a credential prompt | medium | low | question 1, answered before step 2 |
| SQLite passes while PostgreSQL would not | low | medium | CI covers the SQL behaviour against real containers; step 3b covers the extras, which CI does not; running servers here stays out of scope by choice |
| The smoke project is committed to git by accident | low | low | it lives outside the repository, so there is nothing to ignore |
| Time is spent here that a `pip install` from TestPyPI would also have caught | medium | low | accepted: this runs before any account exists, and catches packaging faults a rebuild would not |

## Rollout Order

1. Answer question 1; answer questions 2 and 3 as you reach them.
2. Steps 1–3: install and verify the artefact.
3. Step 3b: the `[postgres]` and `[mysql]` extras — after step 3, never before.
4. Step 4: pure mode.
4. Steps 5–6: Django mode and the admin.
5. Step 7: record the outcome, then plan 002.

## Rollback

Nothing in `eventlog-pro` is modified by this plan, and nothing is published, so
there is nothing to undo. Discard the whole experiment with:

```powershell
Remove-Item -Recurse -Force "$env:USERPROFILE\PycharmProjects\eventlog-consumer-smoke"
```
