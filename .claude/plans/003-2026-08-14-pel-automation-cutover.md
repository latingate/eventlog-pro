# Cut `pel-automation` over to the `eventlog-pro` package

Status: draft
Owner: Gal Sarig
Last updated: 2026-08-14

Split out of [002-2026-08-12-remaining-work-and-decisions.md](002-2026-08-12-remaining-work-and-decisions.md)
on 2026-08-14, which now covers only the package release. Everything here happens
in the **`pel-automation` repository**, not in `eventlog-pro`; this file is kept
here because it was written alongside the extraction, and because the extraction
plans are the only record of why the cutover looks the way it does. Consider
moving it to `pel-automation/.claude/plans/` when the work starts — see Risks.

## Goal

Move `pel-automation` off its in-repo `eventlog/` app onto the published
`eventlog-pro` package, without losing a row or a minute of webhook
availability.

## Scope

**In scope**

- The dependency, `INSTALLED_APPS`, the two import lines, the `_checks/`
  allowlists and the docs.
- The fake-migration sequence that adopts the existing `eventlog_eventlog`
  table.
- The staging rehearsal against a restored copy of production, the production
  deploy, and the later deletion of `pel-automation/eventlog/`.

**Out of scope**

- Publishing the package — that is plan 002, and it is a prerequisite here.
- Any 0.2 feature work on the package; candidates are listed in plan 002 under
  Deferred.
- Rewriting the 16 call sites beyond the import line, except the optional
  `log_event_safe` switch in step 2.

## Assumptions

- Plan 002 is finished: `eventlog-pro` 0.1.0 is installable from wherever the
  release decision landed.
- `pel-automation` production is PostgreSQL, Python 3.12, Django 5.2.
- The `eventlog_eventlog` table keeps its name, so no data moves.
- A staging environment exists that can be pointed at a restored copy of the
  production database.
- **Every path and line number below was read on 2026-08-12 and has not been
  re-verified since.** No test or CI job in either repository checks them, so
  treat them as pointers, not as facts — confirm each one before editing.

## Open Questions

Each carries a recommendation. Reply with the number of the option you want.

**Question 1.** Switch the 16 webhook call sites to `log_event_safe`? They sit
on the Zoho webhook path with no exception guard today, so a logging failure can
turn a good webhook into a 500. `from eventlog_pro import log_event_safe as
log_event` is a one-line diff at `pel/views.py:50`. Note the return annotation
differs (`Event` vs `Event | None`, `src/eventlog_pro/api.py:137` and `:164`),
so any call site that uses the return value may need a type-checker fix. Decide
during step 2.
1. Yes, as its own commit after the cutover is green.
2. Yes, in the same commit as the cutover.
3. No, leave the call sites as they are.
4. Other. Enter your own answer or follow up question.
**Recommendation:** 1 — separate commit, so a rollback of one is not a rollback
of the other.
**Answer:** 

**Question 2.** Keep `ADMIN_READONLY = True`? This is the one behaviour change
users will notice: the admin can no longer add or edit event rows (delete still
works). Decide during step 1.
1. Keep it — `True`.
2. Set `"ADMIN_READONLY": False` in `EVENTLOG_PRO`.
3. Other. Enter your own answer or follow up question.
**Recommendation:** 1 — keep it, unless someone actually edits event rows by
hand.
**Answer:** 

**Question 3.** Keep `ADMIN_SEARCH_DATA = True`? Searching the JSON `data`
column is a full-table `LIKE` scan on PostgreSQL. Decide during step 1.
1. Keep it — `True` — for now.
2. Set it to `False` at cutover.
3. Other. Enter your own answer or follow up question.
**Recommendation:** 1, but check `SELECT count(*) FROM eventlog_eventlog` first;
if the table is already past a few hundred thousand rows, choose 2 instead of
waiting for the first timeout.
**Answer:** 

**Question 4.** Delete `pel-automation/eventlog/` in the same release, or later?
Decide during step 5.
1. Later — leave it on disk, out of `INSTALLED_APPS`, for at least one release.
2. In the same release as the cutover.
3. Other. Enter your own answer or follow up question.
**Recommendation:** 1 — deleting it is a separate, trivial commit once
production has been stable.
**Answer:** 

**Question 5.** Should the `pel-automation` docs changes go via a PR rather than
straight to `main`? The two new files are additive, but `main` is shared.
**Decision needed now** (the branch is waiting).
1. Merge the pushed branch `docs/eventlog-pro-guides` however the team normally does.
2. Push the two files straight to `main`.
3. Other. Enter your own answer or follow up question.
**Recommendation:** 1 — the branch has been pushed for exactly this reason.
**Answer:** 

## Steps

Do **not** start before plan 002 is finished and the package is installable.
Every path below is repository-relative to `pel-automation/`.

1. **Prepare the change on a branch.** Decide questions 2 and 3 while writing
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

2. **Optionally switch to `log_event_safe`** (question 1), as its own commit.

3. **Rehearse the migration against a restored copy of production.** This is the
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

4. **Deploy to production**, after a backup, running the same three commands.
   If the table is large, create the three indexes by hand with
   `CREATE INDEX CONCURRENTLY` first and `migrate eventlog_pro 0002 --fake`.

5. **Delete `pel-automation/eventlog/`** once production has been stable
   (question 4).

## Validation

After steps 3 and 4, the six-command checklist in
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
| Production schema has drifted from the model, and `--fake-initial` hides it | low | high | step 3's rehearsal against a restored copy is the only way to see it |
| `CREATE INDEX` locks a large table during deploy | medium | medium | `CREATE INDEX CONCURRENTLY` by hand, then fake 0002 |
| The admin URL changed (`/admin/eventlog/` → `/admin/eventlog_pro/`) and someone has it bookmarked | high | low | mention it in the release note |
| `ADMIN_READONLY` surprises someone who edited rows by hand | low | low | question 2; one setting reverts it |
| Someone deletes `eventlog/` before production is stable | low | high | question 4: it is a separate, later commit |
| This plan is invisible to whoever does the work, because it lives in the other repository | medium | medium | copy it into `pel-automation/.claude/plans/` when the work starts, and mark this copy `superseded` |
| The file paths and line numbers above have drifted since 2026-08-12 | medium | low | they are unverifiable from this repository; confirm each before editing |

## Rollout Order

1. Decide question 5; plan 002 finished.
2. `pel-automation` branch with the step-1 changes; CI green.
3. Staging: deploy, run the three migration commands, run the validation
   checklist, exercise a real webhook.
4. Production: back up, deploy, same three commands, same checklist.
5. Watch for one release cycle.
6. Optional `log_event_safe` commit; then delete `eventlog/`.

## Rollback

**The table is never dropped, in either direction.** Rows are safe throughout.

```bash
python manage.py migrate eventlog_pro zero --fake   # forget the new history
# restore settings.py:199 and the pel/views.py:50 import
python manage.py migrate eventlog --fake            # restore the old history
```

The three indexes stay behind; they are invisible to the old app and can be
dropped by hand for a byte-exact revert.

*Fastest possible mitigation, no deploy:* set `EVENTLOG_DSN=null://` to stop
recording events entirely, or `EVENTLOG_SILENT=1` to make failures non-fatal.
