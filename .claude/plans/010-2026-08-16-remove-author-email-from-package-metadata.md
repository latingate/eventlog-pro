# Remove the author email from the published package metadata

Status: active
Owner: Gal Sarig
Last updated: 2026-08-16

The PyPI project page shows `dev@peltransport.com` in its Meta panel, sourced
from `authors` in `pyproject.toml`. This removes it. Release mechanics are
[005-2026-08-14-releasing-a-new-version.md](005-2026-08-14-releasing-a-new-version.md).

## Goal

Stop publishing a personal email address as package metadata, without losing
the author attribution itself.

## Scope

**In scope**

- `pyproject.toml:13` — the `authors` table.
- `CHANGELOG.md` — an entry under `[Unreleased]`.

**Out of scope**

- **Cutting a release for this alone.** Two entries already sit under
  `[Unreleased]`; this rides along with them into the next version.
- **The already-published 0.2.2 and earlier.** PyPI metadata is immutable per
  release — see Risks.
- **The PyPI account email.** Separate from package metadata, and never shown
  publicly.
- **Substituting another address.** Considered — a GitHub noreply address and a
  role alias — and rejected in favour of omitting the field entirely.

## Assumptions

- Omitting `email` from an `authors` entry is valid PEP 621, and hatchling emits
  the core-metadata `Author:` field rather than `Author-email:`. **Verified, not
  assumed** — see Validation.
- Packaging metadata is not a caller-facing change, so it does not by itself
  drive the version bump; whatever the next release bumps to is fine.
- Nothing in the repository or in `pel-automation` reads the author email.
  Grepped: `dev@peltransport.com` appears nowhere outside `pyproject.toml`.

## Open Questions

**Question:** What replaces the address?
(1) Omit `email` entirely — `authors = [{ name = "Gal Sarig" }]`.
(2) A GitHub noreply address, `<id>+<username>@users.noreply.github.com`.
(3) A role alias such as `eventlog-pro@latingate.com`.

- **Recommendation:** 1 — nothing needs an address there. The repository's
  Issues URL is already in `[project.urls]` and is the contact channel that
  actually gets read.

- **Answer:** 1


## Steps

1. **Edit `pyproject.toml:13`** to `authors = [{ name = "Gal Sarig" }]`.

2. **Add a `### Changed` entry under `CHANGELOG.md`'s `[Unreleased]`**, noting —
   as the JSONL-summary entry above it already does — that the correction only
   reaches PyPI when a version uploads.

3. **Ship it with the next release** per plan 005. No separate tag.

## Validation

The build is what proves the assumption, so run it rather than reasoning about
it:

```powershell
Remove-Item -Recurse -Force dist -ErrorAction SilentlyContinue
.\.venv\Scripts\python.exe -m build
.\.venv\Scripts\python.exe -m twine check dist/*
```

Then read the built metadata back and confirm `Author: Gal Sarig` is present and
no `Author-email:` line exists:

```powershell
.\.venv\Scripts\python.exe -c "import zipfile; z=zipfile.ZipFile('dist/eventlog_pro-0.2.2-py3-none-any.whl'); n=[x for x in z.namelist() if x.endswith('METADATA')][0]; print(z.read(n).decode('utf-8')[:800])"
```

After the next release uploads, confirm the Meta panel on the live PyPI project
page shows the name with no address.

**This release now warrants a TestPyPI rehearsal.** Plan 005 step 5 triggers on
a `pyproject.toml` edit, and unlike the last two releases this is a genuine
packaging-input change rather than a README edit — so the justification used in
plan 008 and [009](009-2026-08-16-loose-ends-0-2-2.md) does not apply here. The
rule stands and should be followed literally for whichever version ships this.

## Risks

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| The address stays visible on 0.2.2 and earlier forever | certain | low | accepted; PyPI metadata is immutable per release, and deleting old releases to purge it would break existing pins for a cosmetic gain |
| The address is already cached by mirrors, search engines and libraries.io | high | low | accepted; out of anyone's control once published |
| Author attribution disappears from some third-party renderer that reads only `Author-email` | low | low | cosmetic and confined to non-PyPI mirrors; PyPI itself renders `Author:` correctly |
| The edit is forgotten and never reaches PyPI, because metadata only ships on upload | medium | low | the changelog entry under `[Unreleased]` is the reminder, and it states the constraint explicitly |

## Rollout Order

1. Step 1 — the `pyproject.toml` edit.
2. Step 2 — the changelog entry, same commit.
3. Validation above.
4. Step 3 — carried into the next release by plan 005, with the TestPyPI
   rehearsal that plan 005 step 5 now mandates.

## Rollback

Restore the `email` key in `pyproject.toml`. Nothing outside the repository
changes until a release uploads, so there is nothing else to undo.
