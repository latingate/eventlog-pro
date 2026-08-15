# Releasing a new version of `eventlog-pro`

Status: active
Owner: Gal Sarig
Last updated: 2026-08-15

A standing checklist, not a one-off. Plan 002 released 0.1.0 and is `done`; this
generalises what worked there so the next release does not have to rediscover
it. Follow it for every version from 0.1.1 onwards.

## Goal

Ship a new version to PyPI with the same confidence as 0.1.0: nothing broken
reaches users, and if something does, it is recoverable.

## Scope

**In scope**

- Local development against unreleased code, without touching PyPI.
- Choosing the version number.
- Pre-release verification, the tag, and the post-release check.

**Out of scope**

- What goes *into* a release. That is [`TODO.md`](../../TODO.md) and whatever
  plan covers the specific feature.
- The `pel-automation` cutover — plan 003.

## Assumptions

- Trusted publishing is already configured; the pending publisher converted to a
  real one when 0.1.0 uploaded, so nothing needs re-doing on PyPI.
- The `pypi` environment exists in the GitHub repository.
- `main` is the release branch, and `publish.yml` triggers on `v*` tags.

## Open Questions

- **Question 1.** Should every release be rehearsed on TestPyPI, or only ones
  that change packaging?
1. Only when packaging changes — `pyproject.toml`, the build backend, included files, or the README.
2. Every release, without exception.
3. Other. Enter your own answer or follow up question.
- **Recommendation:** 1 — the rehearsal exists to catch packaging faults, and a
  pure code change with green CI cannot introduce one. Uploading to TestPyPI
  also burns the version number there, which makes a re-rehearsal awkward.
- **Answer:** 1

- **Question 2.** Where should day-to-day development happen?
1. Feature branches off `main`, merged by PR.
2. Straight to `main`.
3. Other. Enter your own answer or follow up question.
- **Recommendation:** 1 — CI runs on every push, and a branch keeps `main`
  always taggable.
- **Answer:** 1

## Working on the package without releasing it

Nothing here touches PyPI. This is the answer to "how do I test a fix before
publishing it".

1. **Develop against an editable install.** In this repository:
   ```powershell
   .\.venv\Scripts\python.exe -m pip install -e ".[dev]"
   ```
   `-e` links the venv to `src/`, so edits take effect with no reinstall. The
   `[dev]` extra brings pytest, ruff, mypy, build and twine.

2. **Run the suite locally.**
   ```powershell
   .\.venv\Scripts\python.exe -m pytest -q
   .\.venv\Scripts\python.exe -m ruff check .
   .\.venv\Scripts\python.exe -m mypy --strict src
   ```
   The PostgreSQL and MySQL integration tests skip unless their DSNs are set:
   ```powershell
   $env:EVENTLOG_TEST_POSTGRES_DSN = "postgresql://user:pw@localhost:5432/scratch"
   .\.venv\Scripts\python.exe -m pytest tests/test_backend_postgres.py -v
   ```

3. **Try it from a consumer's point of view, still without PyPI.** Any of these
   installs unreleased code into another project:
   ```powershell
   pip install -e C:\Users\gal20\PycharmProjects\eventlog-pro   # editable, tracks your edits
   pip install C:\Users\gal20\PycharmProjects\eventlog-pro      # a real build of the working tree
   pip install "eventlog-pro @ git+https://github.com/latingate/eventlog-pro@<branch-or-sha>"
   ```
   The git form is the one to use when someone else needs to try your branch —
   it needs no upload and no account, and it builds the same wheel PyPI would.
   Plan 004 is the worked example.

4. **Open a PR.** `ci.yml` triggers on `pull_request` and on pushes to `main` —
   **not** on pushes to a feature branch, so a branch push alone runs nothing.
   The PR is what starts the full matrix: Python 3.10–3.13, Django 4.2 and 5.2,
   real PostgreSQL and MySQL containers, with no release involved. This is where
   cross-version problems surface, and it is the only place the PostgreSQL and
   MySQL tests run at all — they skip locally unless their DSNs are set.

## Where old versions live

- **PyPI keeps every released version forever.** `pip install eventlog-pro==0.1.0`
  will still work years from now. You do not archive wheels yourself, and you
  should not commit `dist/` — it is gitignored for that reason.
- **A release can be yanked, never replaced or deleted.** Yanking hides it from
  new resolutions while leaving exact pins working. A version number is spent
  the moment it uploads, on PyPI and on TestPyPI alike.
- **Git keeps the source history**, and the tag is the link between the two:
  `v0.1.0` marks the commit PyPI built from. Check out any release with
  `git checkout v0.1.0`.
- **Your working copy keeps nothing.** `dist/` is scratch space; delete it
  freely.

## Steps

1. **Merge the work to `main` by PR and confirm CI is green on the merge
   commit.** Development happens on feature branches off `main` (question 2), so
   there is always a PR to merge; `main` stays taggable between releases. Never
   tag a red build.

2. **Choose the version and update `__about__.py`.** It is the single source of
   truth — `pyproject.toml` reads it dynamically, and `publish.yml:29-39`
   asserts the tag matches it.

   | Change | Bump | Example |
   |---|---|---|
   | Bug fix, no behaviour change | patch | `0.1.0` → `0.1.1` |
   | New feature, backwards compatible | minor | `0.1.1` → `0.2.0` |
   | Anything that breaks a caller, including a changed default | minor while 0.x | `0.2.0` → `0.3.0` |

   While the package is `0.x`, treat minor as the breaking-change bump. The
   `events.db` rename — [plan 007](007-2026-08-15-default-sqlite-filename-rename.md)
   — is exactly this case.

3. **Update `CHANGELOG.md`.** Users read this to decide whether to upgrade.

   Entries accumulate under `## [Unreleased]` as work merges, so at release
   time the job is usually **renaming that heading**, not writing it from
   scratch:

   - Change `## [Unreleased]` to `## [<version>] - YYYY-MM-DD`.
   - Add a fresh, empty `## [Unreleased]` above it for the next cycle.
   - Check the groupings are Added / Changed / Fixed / Documentation.

   Nothing automates this. `publish.yml` never reads `CHANGELOG.md`, so a
   forgotten rename ships a released version whose notes are headed
   "Unreleased" — cosmetic, but permanent, because the upload cannot be
   replaced.

   To see what is waiting:
   ```powershell
   git log --oneline "$(git describe --tags --abbrev=0)..HEAD"
   ```

4. **Verify the build before tagging.**
   ```powershell
   Remove-Item -Recurse -Force dist -ErrorAction SilentlyContinue
   .\.venv\Scripts\python.exe -m build
   .\.venv\Scripts\python.exe -m twine check dist/*
   ```

5. **Rehearse on TestPyPI — only when packaging changed** (question 1):
   `pyproject.toml`, the build backend, the included files, or the README. New
   modules under `src/eventlog_pro/` are not a packaging change; the wheel takes
   the whole package directory, so they ship without any config edit. Skip this
   step for a pure code release with green CI.

   Do not decide this from memory — ask git, since `README.md` is the easiest
   one to change without thinking of it as packaging:
   ```powershell
   git diff --stat "$(git describe --tags --abbrev=0)..HEAD" -- pyproject.toml README.md
   ```
   Any output means this release warrants a rehearsal.

   ```powershell
   .\.venv\Scripts\python.exe -m twine upload --repository testpypi dist/*
   ```
   Then install it back into a throwaway venv. `--extra-index-url` is required:
   `--index-url` replaces PyPI outright, and Django is not mirrored on TestPyPI.
   ```powershell
   pip install --index-url https://test.pypi.org/simple/ `
               --extra-index-url https://pypi.org/simple/ `
               "eventlog-pro[django]"
   ```

6. **Commit, push, tag, push the tag.**
   ```powershell
   git commit -am "release: 0.1.1"
   git push
   git tag v0.1.1
   git push origin v0.1.1
   ```
   The tag must be exactly `v` + the version in `__about__.py`.

7. **Watch the workflow** at <https://github.com/latingate/eventlog-pro/actions>.
   It builds, runs `twine check`, asserts the tag matches `__about__.py` and
   that the wheel ships both migrations and `py.typed`, then uploads by OIDC.
   No token is involved.

## Validation

After the workflow finishes, in a throwaway venv:

```powershell
pip install --no-cache-dir "eventlog-pro[django]==<version>"
python -c "import eventlog_pro; print(eventlog_pro.__version__)"
python -c "import eventlog_pro, pathlib; r=pathlib.Path(eventlog_pro.__file__).parent; print(all((r/f).exists() for f in ['py.typed','contrib/django/migrations/0001_initial.py','contrib/django/migrations/0002_add_indexes.py']))"
```

Then write and read back one row, as plan 004 step 4 does. If the release
changes the schema, the Django path in plan 004 step 5 too.

## Risks

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| A broken version reaches PyPI, where it cannot be replaced | low | high | steps 4–5; yank and fix forward with the next patch |
| The tag does not match `__about__.py` | medium | low | `publish.yml` fails the build before uploading; delete the tag, fix, re-tag |
| Tagging a commit that is not what was tested | medium | medium | tag only after CI is green on that exact commit |
| A breaking change ships as a patch bump | medium | medium | step 2's table; while 0.x, breaking means a minor bump |
| `dist/` holds stale artefacts from a previous build | medium | medium | step 4 deletes it first |
| The version number is silently spent on TestPyPI | medium | low | rehearse deliberately, once — question 1 |

## Rollout Order

1. Merge and confirm CI green.
2. Bump `__about__.py`, update `CHANGELOG.md`.
3. Build and `twine check`; rehearse on TestPyPI if this release warrants it.
4. Commit, push, tag, push the tag.
5. Watch the workflow; run the validation above.
6. Tell `pel-automation` if the pin needs moving.

## Rollback

- **Before the upload:** delete and re-push the tag.
  ```powershell
  git push --delete origin v0.1.1
  git tag -d v0.1.1
  ```
- **After the upload:** the version is permanent. Yank it on PyPI — *Manage →
  Releases → Yank* — which hides it from new installs while leaving exact pins
  working, then fix forward with the next patch version. Never try to reuse a
  version number.
- **For a consumer in trouble right now:** pin the previous version
  (`eventlog-pro==0.1.0`), or use the runtime kill switches — `EVENTLOG_DSN=null://`
  to stop recording, `EVENTLOG_SILENT=1` to make failures non-fatal. Neither
  needs a release.
