# Remaining work and open decisions after building `eventlog-pro` 0.1.0

Status: active
Owner: Gal Sarig
Last updated: 2026-08-12

Follows [001-2026-08-12-eventlog-pro-package-extraction.md](001-2026-08-12-eventlog-pro-package-extraction.md),
which is now `done`. This plan covers what that one deliberately left out: the
release itself, and the `pel-automation` cutover.

## Goal

Get `eventlog-pro` 0.1.0 published, then move `pel-automation` off its in-repo
`eventlog/` app onto the package, without losing a row or a minute of webhook
availability.

## Scope

**In scope**

- Publishing 0.1.0 (TestPyPI → PyPI, trusted publishing setup, tag).
- The `pel-automation` cutover: dependency, `INSTALLED_APPS`, imports, the
  `_checks/` allowlists, docs, and the fake-migration sequence.
- The staging rehearsal against a copy of production.

**Out of scope**

- Any 0.2 feature work. Candidates are listed under Deferred, not planned.
- Rewriting the 16 call sites beyond the import line, except the optional
  `log_event_safe` switch in step 6.

## What is already done

The package repository is complete and verified. Nothing below is outstanding.

| Area | State |
|---|---|
| Package | `src/eventlog_pro/` — core, seven backends, Django app, migrations, admin |
| Tests | 228 passed / 19 skipped offline; 247 passed with Postgres + MySQL; 96% coverage |
| Quality | `ruff check`, `ruff format --check`, `mypy --strict` all clean |
| Build | wheel + sdist build, `twine check` passes, migrations and `py.typed` verified inside the wheel |
| Smoke test | wheel installed in a clean venv, base install only, writes and reads back a row |
| CI | `.github/workflows/ci.yml` — core (3.10–3.13), Django (3× py × 2× Django), Postgres, MySQL, lint, package |
| Publish | `.github/workflows/publish.yml` — tag-triggered, trusted publishing, no token secret |
| Docs | `README.md`, `CHANGELOG.md`, `LICENSE`, plus the two guides in `pel-automation/.docs/` |

Verified end to end, not just by unit test: DDL parity with Django's own
migration (character for character on SQLite), a row written by the core backend
read back through the ORM with an identical timestamp, `--fake-initial` adopting
a pre-existing table, and both integration suites against real PostgreSQL 16 and
MySQL 8 containers.

## Assumptions

- The GitHub repository is `latingate/eventlog-pro`; project URLs point there.
- Publishing to PyPI under the name `eventlog-pro` is intended and the name is
  free. **Not yet checked** — see Open Questions.
- `pel-automation` production is PostgreSQL, Python 3.12, Django 5.2.
- The `eventlog_eventlog` table keeps its name, so no data moves.
- A staging environment exists that can be pointed at a restored copy of the
  production database.

## Open Questions

Each has a recommended answer. Nothing below blocks anything already built.

1. **Publish to public PyPI, or keep it private?**
   The package carries no PEL-specific logic, so public is defensible, but it
   also carries no business benefit. Options: public PyPI, a private index, or a
   git dependency (`pip install git+https://github.com/latingate/eventlog-pro@v0.1.0`).
   *Recommended:* **public PyPI.** The trusted-publishing workflow is already
   written for it, and a git dependency makes the `~=0.1.0` pin meaningless.
   → **Decision needed before step 1.**

2. **Is the name `eventlog-pro` free on PyPI, and is it the name you want?**
   *Recommended:* check <https://pypi.org/project/eventlog-pro/> before tagging.
   If taken, renaming later is a `name =` change plus new URLs — cheap now,
   expensive after anyone installs it.
   → **Decision needed before step 1.**

3. **Switch the 16 webhook call sites to `log_event_safe`?**
   They sit on the Zoho webhook path with no exception guard today, so a logging
   failure can turn a good webhook into a 500. `from eventlog_pro import
   log_event_safe as log_event` is a one-line diff at `pel/views.py:50`.
   *Recommended:* **yes**, but as a separate commit after the cutover is green,
   so a rollback of one is not a rollback of the other.
   → Decide during step 6.

4. **Keep `ADMIN_READONLY = True`?**
   This is the one behaviour change users will notice: the admin can no longer
   add or edit event rows (delete still works).
   *Recommended:* **keep it.** Set `"ADMIN_READONLY": False` in `EVENTLOG_PRO`
   if anyone actually edits event rows by hand.
   → Decide during step 5.

5. **Keep `ADMIN_SEARCH_DATA = True`?**
   Searching the JSON `data` column is a full-table `LIKE` scan on PostgreSQL.
   *Recommended:* **keep it for now** — check `SELECT count(*) FROM
   eventlog_eventlog` first; if the table is already past a few hundred thousand
   rows, set it to `False` at cutover instead of waiting for the first timeout.
   → Decide during step 5.

6. **Delete `pel-automation/eventlog/` in the same release, or later?**
   *Recommended:* **later.** Leave it on disk, out of `INSTALLED_APPS`, for at
   least one release; deleting it is a separate, trivial commit once production
   has been stable.
   → Decide during step 9.

7. **Should `pel-automation` docs changes go via a PR rather than straight to
   `main`?** The two new files are additive, but `main` is shared.
   *Recommended:* the branch `docs/eventlog-pro-guides` has been pushed for
   exactly this reason; merge it however the team normally does.
   → **Decision needed now** (the branch is waiting).

## Steps

### Release the package

1. **Decide questions 1 and 2.** If not public PyPI, stop here and use a git
   tag or private index instead; the rest of this section does not apply.
2. **Set up trusted publishing.** On PyPI: the project's *Publishing* tab → add
   a GitHub publisher with repository `latingate/eventlog-pro`, workflow
   `publish.yml`, environment `pypi`. Create the `pypi` environment in the
   repository settings. **No API token is created, ever.**
3. **Rehearse on TestPyPI.**
   ```bash
   python -m build
   twine check dist/*
   twine upload --repository testpypi dist/*
   pip install --index-url https://test.pypi.org/simple/ "eventlog-pro[django]"
   ```
4. **Tag and let CI publish.**
   ```bash
   git tag v0.1.0 && git push --tags
   ```
   The workflow asserts the tag matches `__about__.py` and that the wheel
   contains both migrations and `py.typed` before it uploads.

### Cut `pel-automation` over

Do **not** start before the package is installable and the release decision is
made. Every path below is repository-relative to `pel-automation/`.

5. **Prepare the change on a branch.** Decide questions 4 and 5 while writing
   the settings block.

   | File | Line | Change |
   |---|---|---|
   | `requirements.txt` | — | add `eventlog-pro[django]~=0.1.0` |
   | `pel_automation/settings.py` | 199 | `'eventlog.apps.EventlogConfig'` → `'eventlog_pro.contrib.django'` |
   | `pel_automation/settings.py` | — | add the `EVENTLOG_PRO` block (see the setup guide, §4 step 3) |
   | `pel/views.py` | 50 | import from `eventlog_pro` |
   | `pel/views_20260809.py` | 50 | same, in the dated copy |
   | `_checks/third_party_imports.py` | 15 | drop `"eventlog"` from `LOCAL` |
   | `_checks/file_list_diff.py` | 24 | drop `"eventlog/"` from `KEEP_PREFIXES` |
   | `README.md` | 41 | update the app table |
   | `CLAUDE.md` | 15, 98 | update the app lists |

   No other edit is needed: all 16 `log_event()` call sites keep working, the
   signature is identical.

6. **Optionally switch to `log_event_safe`** (question 3), as its own commit.

7. **Rehearse the migration against a restored copy of production.** This is the
   step that cannot be skipped: `--fake-initial` matches on table existence
   only, never on columns, so any drift between production and the model will
   fake successfully and leave a broken model with no error.
   ```bash
   python manage.py migrate eventlog zero --fake
   python manage.py migrate eventlog_pro --fake-initial
   python manage.py migrate eventlog_pro
   ```
   Note `pel_automation/settings.py:271-282` swaps to SQLite when `"test"` is in
   `sys.argv`, so **`manage.py test` never exercises this path** — a green test
   run proves nothing here.

8. **Deploy to production**, after a backup, running the same three commands.
   If the table is large, create the three indexes by hand with
   `CREATE INDEX CONCURRENTLY` first and `migrate eventlog_pro 0002 --fake`.

9. **Delete `pel-automation/eventlog/`** once production has been stable
   (question 6).

## Validation

After step 4:

```bash
pip download eventlog-pro==0.1.0 --no-deps -d /tmp/check   # it is really on PyPI
python -m zipfile -l /tmp/check/*.whl | grep -E "migrations|py.typed"
```

After steps 7 and 8, the six-command checklist in
`pel-automation/.docs/eventlog_setup.md` §6, plus the row count on both sides of
the migration:

```bash
# before
python manage.py shell -c "from eventlog.models import EventLog; print(EventLog.objects.count())"
# after — the same number
python manage.py shell -c "from eventlog_pro.contrib.django.models import EventLog; print(EventLog.objects.count())"
```

Then, in the browser: `/admin/eventlog_pro/eventlog/` lists rows, the date
hierarchy drills down, and the entity link resolves. Finally, exercise one real
Zoho webhook in staging and confirm the event row appears.

## Risks

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Production schema has drifted from the model, and `--fake-initial` hides it | low | high | step 7's rehearsal against a restored copy is the only way to see it |
| `CREATE INDEX` locks a large table during deploy | medium | medium | `CREATE INDEX CONCURRENTLY` by hand, then fake 0002 |
| The admin URL changed (`/admin/eventlog/` → `/admin/eventlog_pro/`) and someone has it bookmarked | high | low | mention it in the release note |
| `ADMIN_READONLY` surprises someone who edited rows by hand | low | low | question 4; one setting reverts it |
| The PyPI name is taken | low | medium | question 2, checked before tagging |
| Someone deletes `eventlog/` before production is stable | low | high | question 6: it is a separate, later commit |

## Rollout Order

1. Decide questions 1, 2 and 7.
2. Trusted publishing setup → TestPyPI → tag `v0.1.0` → PyPI.
3. `pel-automation` branch with the step-5 changes; CI green.
4. Staging: deploy, run the three migration commands, run the validation
   checklist, exercise a real webhook.
5. Production: back up, deploy, same three commands, same checklist.
6. Watch for one release cycle.
7. Optional `log_event_safe` commit; then delete `eventlog/`.

## Rollback

**The table is never dropped, in either direction.** Rows are safe throughout.

- *Package:* a bad release is yanked on PyPI, not deleted; `0.1.1` fixes
  forward. Nothing in `pel-automation` changes until step 5.
- *Cutover:*
  ```bash
  python manage.py migrate eventlog_pro zero --fake   # forget the new history
  # restore settings.py:199 and the pel/views.py:50 import
  python manage.py migrate eventlog --fake            # restore the old history
  ```
  The three indexes stay behind; they are invisible to the old app and can be
  dropped by hand for a byte-exact revert.
- *Fastest possible mitigation, no deploy:* set `EVENTLOG_DSN=null://` to stop
  recording events entirely, or `EVENTLOG_SILENT=1` to make failures non-fatal.

## Deferred — 0.2 candidates, not planned

Recorded so they are not rediscovered later. None is a defect.

- `event_type` casing is inconsistent: recognised values render upper-cased,
  unrecognised ones keep their original casing. Preserved verbatim from the
  source app.
- No `choices` or enum on `event_type`, no validation on `app`.
- No connection pooling, batching or async.
- `jsonl://` leaves `id` as `None`.
- Changing `EVENTLOG_PRO["TABLE"]` after import neither moves the table nor
  generates a rename; the `eventlog_pro.W001` check reports the drift.
- `contrib/flask/` is possible with the current layout; nobody has asked.
- Local development installs Django 6.1 (the extra is `Django>=4.2`), while CI
  covers 4.2 and 5.2. Pinning the dev environment to 5.2 would match production
  more closely.
