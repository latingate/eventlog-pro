# Rename the default SQLite file to `eventlog-pro.db`

Status: done — shipped in 0.2.0 on 2026-08-15
Owner: Gal Sarig
Last updated: 2026-08-15

Carries out the `TODO.md` item under "Defaults and messages". Shipping in the
same release as the read and delete APIs — see
[005-2026-08-14-releasing-a-new-version.md](005-2026-08-14-releasing-a-new-version.md)
for the release mechanics and [006-2026-08-14-read-and-delete-api.md](006-2026-08-14-read-and-delete-api.md)
for the other half of the release.

## Goal

Change the default SQLite filename from `events.db` to `eventlog-pro.db`, so the
file a user gets without configuring anything is named after the package instead
of a generic word that collides with other tools in the same directory.

## Scope

**In scope**

- `DEFAULT_DSN` in `src/eventlog_pro/config.py:30`.
- The fallback filename in `src/eventlog_pro/config.py:191`.
- Documentation that states the default: `README.md:81, 144, 280, 293`,
  `src/eventlog_pro/__init__.py:8`, `src/eventlog_pro/backends/sqlite.py:3`,
  `src/eventlog_pro/dsn.py:9-10, 100, 148`.
- Tests asserting the default: `tests/test_config.py:99, 106, 109`.
- The `CHANGELOG.md` note, which is what makes this survivable for users.

**Out of scope**

- Any *migration* of an existing `events.db`. Nothing moves, copies, or opens a
  user's old file — see the risks table.
- The separate `TODO.md` item about the fallback warning claiming it "will
  create" a file that already exists. Adjacent code, different bug; doing both
  at once muddles the changelog entry. Note the overlap: question 1 adds an
  existence check to the same function, so that fix gets cheaper afterwards —
  but it also means the warning will still say "will create `eventlog-pro.db`"
  on a second run. Worth doing next, not here.
- Occurrences of `events.db` that are just an arbitrary filename rather than the
  default: `tests/conftest.py:54`, `tests/test_backend_sqlite.py:76, 83`,
  `tests/test_dsn.py:14-16`, `.github/workflows/ci.yml:184`. These pass an
  explicit path and would behave identically if named `x.db`. Renaming them is
  churn that makes the diff harder to review.
- Plans 001–004, which record what was true when written.

## Assumptions

- The package is `0.x`, so a behaviour change ships as a minor bump — `0.2.0`,
  the same release as the read and delete APIs.
- Anyone running in production has set `EVENTLOG_DSN` or called `configure()`,
  and is therefore unaffected. The default is a getting-started convenience; the
  fallback already emits a warning saying so.
- No consumer pins the literal string `"sqlite:///./events.db"`. `pel-automation`
  configures its DSN explicitly (plan 003).

## Open Questions

- **Question 1.** What should happen when the new default resolves and an old
  `./events.db` is sitting right there — almost certainly this package's own
  file from a previous version?
1. Warn once, naming both files, and carry on with the new one. The user moves the file if they want the history.
2. Say nothing. New default, new file, clean break.
3. Reuse the existing `./events.db` when it exists and no `eventlog-pro.db` does, so nobody loses data.
- **Recommendation:** 1 — silence loses an audit log to a rename, which is the
  one thing an audit log must not do, and 3 makes the default DSN depend on
  directory contents, so two machines running the same code use different files.
  A warning is honest and costs one line.
- **Answer:** 1


- **Question 2.** `AGENTS.md` requires a feature doc per feature touched, and
  there is no doc that owns configuration or the default DSN — only
  `docs/features/read-api.md` and `delete-api.md` exist.
1. Create `docs/features/configuration.md` covering the DSN, the settings, the environment variables, and the default-file fallback.
2. Create a narrow `docs/features/default-dsn.md` about the default and its fallback only.
3. Skip the doc this time and note it in `TODO.md`.
- **Recommendation:** 1 — the doc is owed regardless of this rename, and a
  narrow file about one constant would be absorbed into a configuration doc
  within a release or two. It is the larger write-up, so say if you would rather
  keep this release small.
- **Answer:** 1


- **Question 3.** Should the rename land as its own commit on the feature
  branch, or as part of the release commit?
1. Its own commit on a branch off `main`, PR'd like anything else (question 2 of plan 005).
2. Folded into the release commit that bumps the version.
- **Recommendation:** 1 — it is a behaviour change with its own tests and
  changelog entry, and `git log` should show it separately from a version bump.
- **Answer:** 2 - let it be part of the release commit of the current feature (read-and-delete)


## Steps

1. **Change `DEFAULT_DSN`** in `src/eventlog_pro/config.py:30` to
   `"sqlite:///./eventlog-pro.db"`.

2. **Change the fallback filename** in `src/eventlog_pro/config.py:191`, where
   `Path(parsed.database or "events.db").resolve()` builds the path named in the
   warning. It must agree with `DEFAULT_DSN` or the warning names a file the
   package will not create.

3. **Warn when an old `./events.db` is present** (question 1). In
   `_warn_if_default_dsn` (`config.py:180-192`), check whether `./events.db`
   exists at the point the fallback fires and, if it does, add a line naming
   both paths and saying the old file is untouched and how to keep using it.
   One warning per process, as now — the check is on the same code path, not a
   new one.

4. **Update the documentation of the default**: `README.md:81, 144, 280, 293`,
   the module docstrings in `src/eventlog_pro/__init__.py:8`,
   `src/eventlog_pro/backends/sqlite.py:3` and `src/eventlog_pro/dsn.py:9-10,
   100, 148`.

5. **Update the tests that assert the default**: `tests/test_config.py:99, 106,
   109`, where line 109 asserts the warning text contains `events.db`. Add a
   test that `DEFAULT_DSN` and the fallback path agree, so step 2 cannot regress
   silently, and a test for the question 1 behaviour.

6. **Write `docs/features/configuration.md`** (question 2): the DSN and its
   schemes, the `Settings` fields, the `EVENTLOG_*` environment variables and
   their precedence, `auto_create_table`, the `raise_on_error` kill switch, and
   the default-file fallback with its warning. Describes current behaviour only.
   Link it from `read-api.md` and `delete-api.md` where they mention which
   backend is configured.

7. **Add the `CHANGELOG.md` entry** under Changed, in the `0.2.0` section,
   stating the old name, the new name, who is affected (only callers relying on
   the default) and the one-line fix (`configure(dsn="sqlite:///./events.db")`
   keeps the old file).

## Validation

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m mypy --strict src
```

Then, in an empty scratch directory with no `EVENTLOG_DSN` set, confirm the
end-to-end default: one `log_event()` creates `eventlog-pro.db` and no
`events.db`, the warning names the file that actually appears, and
`event_query()` reads the row back.

```powershell
grep -rn "events.db" --include=*.py --include=*.md src README.md
```

should return only the deliberate mentions — the changelog entry and whatever
question 1 adds.

## Risks

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| A user on the default silently starts writing to a new empty file and thinks their history is gone | medium | medium | question 1's warning; the changelog entry says the old file is intact and how to keep using it |
| `DEFAULT_DSN` and the fallback filename drift apart, so the warning names the wrong file | low | medium | step 5's test that they agree |
| A stale `events.db` reference survives in the README and misleads a new user | medium | low | the `grep` in Validation |
| The rename is read as a bug fix and ships as a patch | low | medium | it is a behaviour change: `0.2.0`, per plan 005 step 2 |

## Rollout Order

Question 3 puts this on the existing `feat/read-and-delete-api` branch rather
than a branch of its own, so it ships in that branch's release commit. Plan
005's PR rule (question 2) still applies to the branch as a whole.

1. Steps 1–3 with their tests, on `feat/read-and-delete-api`.
2. Steps 4–6 — docs, in the same commit as the code.
3. Step 7 — changelog, under the `0.2.0` heading.
4. Bump `__about__.py` to `0.2.0`; commit as the release commit.
5. PR to `main`, green CI, merge.
6. Hand over to plan 005 from step 4 (build and `twine check`) for the release
   itself, stopping before the tag push.

## Rollback

- **Before release:** revert the commit. Nothing outside the repository has
  changed.
- **After release:** no rollback is needed on the user's side — the old file is
  untouched, and `configure(dsn="sqlite:///./events.db")` or
  `EVENTLOG_DSN=sqlite:///./events.db` restores the previous behaviour without a
  downgrade. If the rename itself proves wrong, reverting it is another minor
  bump, not a patch, because it changes behaviour again.
