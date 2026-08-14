# Release `eventlog-pro` 0.1.0

Status: active
Owner: Gal Sarig
Last updated: 2026-08-14

Follows [001-2026-08-12-eventlog-pro-package-extraction.md](001-2026-08-12-eventlog-pro-package-extraction.md),
which is now `done`. This plan covers the release itself. The `pel-automation`
cutover was split out on 2026-08-14 into
[003-2026-08-14-pel-automation-cutover.md](003-2026-08-14-pel-automation-cutover.md),
because it is work in another repository and nothing in it is checkable from
here; this plan is a prerequisite for that one.

## Goal

Get `eventlog-pro` 0.1.0 published and installable.

## Scope

**In scope**

- Publishing 0.1.0 (TestPyPI → PyPI, trusted publishing setup, tag).

**Out of scope**

- The `pel-automation` cutover — plan 003.
- Any 0.2 feature work. Candidates are listed under Deferred, not planned.

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
- Publishing to PyPI under the name `eventlog-pro` is intended. The name was
  free on 2026-08-14: `https://pypi.org/pypi/eventlog-pro/json` returned HTTP
  404, which also covers `eventlog_pro` (PyPI normalises both to one name).
  Availability is not a reservation — it is only certain at upload.

## Open Questions

Both are answered; neither blocks anything already built. The cutover questions
moved to plan 003. Reply with the number of the option you want.

**Question 1.** Publish to public PyPI, or keep it private? The package carries
no PEL-specific logic, so public is defensible, but it also carries no business
benefit. **Decision needed before step 1.**
1. Public PyPI.
2. A private index.
3. A git dependency (`pip install git+https://github.com/latingate/eventlog-pro@v0.1.0`).
4. Other. Enter your own answer or follow up question.
- **Recommendation:** 1 — public PyPI. The trusted-publishing workflow is already
  written for it, and a git dependency makes the `~=0.1.0` pin meaningless.
- **Answer:** 1

**Question 2.** Keep the name `eventlog-pro`, or rename before anyone installs
it? Renaming later is a `name =` change plus new URLs — cheap now, expensive
afterwards. **Decision needed before step 1.**
1. Keep `eventlog-pro`, after confirming <https://pypi.org/project/eventlog-pro/> is free.
2. Rename — supply the new name.
3. Other. Enter your own answer or follow up question.
- **Recommendation:** 1 — keep it, but check the URL before tagging rather than
  after.
- **Answer:** 1

## Steps

1. **Decide questions 1 and 2.** If not public PyPI, stop here and use a git
   tag or private index instead; the rest of this section does not apply.
2. **Set up trusted publishing.** The project does not exist on PyPI yet, so
   there is no project *Publishing* tab to use — it has to be a **pending
   publisher**: PyPI → *Your account* → *Publishing* → *Add a new pending
   publisher*, with project name `eventlog-pro`, owner `latingate`, repository
   `eventlog-pro`, workflow `publish.yml`, environment `pypi`. It converts into
   a normal publisher on the first successful upload. Also create the `pypi`
   environment in the GitHub repository settings — `publish.yml:65` names it,
   and the job fails without it. **No API token is created for PyPI, ever.**
3. **Rehearse on TestPyPI.** This runs from a laptop, not from the workflow, so
   it does need a TestPyPI API token — a throwaway credential on a throwaway
   index, and the one exception to the no-token rule above. TestPyPI is a
   separate site with its own account. Store the token in `~/.pypirc` under a
   `[testpypi]` section with `username = __token__`, or export
   `TWINE_USERNAME=__token__` and `TWINE_PASSWORD=<token>` for the session and
   write nothing to disk. Never inside the repository.
   ```bash
   rm -rf dist                      # never upload stale artefacts
   python -m build                  # -> dist/*.whl and dist/*.tar.gz
   python -m twine check dist/*     # metadata and README rendering
   python -m twine upload --repository testpypi dist/*
   ```
   Then install it back, in a throwaway venv:
   ```bash
   pip install --index-url https://test.pypi.org/simple/ \
               --extra-index-url https://pypi.org/simple/ \
               "eventlog-pro[django]"
   ```
   `--extra-index-url` is **required**, not optional: `--index-url` replaces
   PyPI outright, and Django is not mirrored on TestPyPI, so without it the
   install fails to resolve the dependency and the rehearsal proves nothing.

   On Windows use `.\.venv\Scripts\python.exe -m …`; bare `twine` is not on
   `PATH`, and a backtick continues the line instead of a backslash.
4. **Tag and let CI publish.**
   ```bash
   git tag v0.1.0 && git push --tags
   ```
   The workflow asserts the tag matches `__about__.py` and that the wheel
   contains both migrations and `py.typed` before it uploads.

## Validation

**Step 3 executed 2026-08-14 against `dce2354`. Passed.**

| Check | Result |
|---|---|
| `twine check dist/*` | PASSED for both the wheel and the sdist |
| Upload to TestPyPI | both files accepted; <https://test.pypi.org/project/eventlog-pro/0.1.0/> |
| Published wheel size | 51,078 bytes — no bloat. The `71.6 kB` twine prints is the multipart upload body, not the file |
| Wheel contents | 36 entries, `eventlog_pro/**` and `dist-info` only; no plans, tests or stray files |
| `py.typed` and both migrations | present in the published artefact |
| Metadata | `Description-Content-Type: text/markdown`, `Requires-Python: >=3.10`, all five extras (`all`, `dev`, `django`, `mysql`, `postgres`) declared |
| Install from TestPyPI | succeeded with `--extra-index-url`, resolving Django 6.1 from PyPI |
| Write + read back from the installed package | `(1, 'testpypi', 'FROM_TESTPYPI', '{"ok": true}')` |
| README rendering on the project page | confirmed by eye — formatted, not raw text |

Step 2 is also done: PyPI account, pending publisher, and the `pypi` environment
in the GitHub repository all exist. Step 4 is unblocked.

After step 4:

```bash
pip download eventlog-pro==0.1.0 --no-deps -d /tmp/check   # it is really on PyPI
python -m zipfile -l /tmp/check/*.whl | grep -E "migrations|py.typed"
```

## Risks

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| The PyPI name is taken | low | medium | question 2, checked before tagging |
| A bad 0.1.0 reaches PyPI, where releases cannot be replaced | low | medium | rehearse on TestPyPI first (step 3); yank and fix forward as 0.1.1 |
| Step 3 burns the version number on TestPyPI too, so the same rehearsal cannot be repeated | medium | low | rehearse once, deliberately; a second attempt needs `0.1.0.post1` or a bumped version |

## Rollout Order

1. Questions 1 and 2: both answered.
2. [004-2026-08-14-consumer-smoke-test-from-git.md](004-2026-08-14-consumer-smoke-test-from-git.md)
   — prove the package works installed from git, before anything is published.
3. Create the PyPI account and the pending publisher.
4. Trusted publishing setup → TestPyPI → tag `v0.1.0` → PyPI.
5. Then plan 003, the `pel-automation` cutover.

## Rollback

A bad release is yanked on PyPI, not deleted; `0.1.1` fixes forward. Nothing in
`pel-automation` changes under this plan, so there is nothing else to undo.

## Deferred — 0.2 candidates, not planned

Moved on 2026-08-14 to [`TODO.md`](../../TODO.md) at the repository root, so the
list outlives this plan and is visible to anyone reading the repository rather
than buried in a plan that gets marked `done` after the release. Keep it there;
do not re-add items here, or the two lists will drift.

Added at the same time: a read API, a CLI and a pure-mode dashboard — 0.1.0 is
write-only outside Django, which is a deliberate omission rather than a defect.
