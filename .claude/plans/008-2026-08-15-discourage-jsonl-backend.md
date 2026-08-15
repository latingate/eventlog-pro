# Document `jsonl://` as a niche, not-recommended backend

Status: done — merged to `main` on 2026-08-15 as `193d072` (PR #2), all 13 CI
checks green. The changelog entry waits under `[Unreleased]`; nothing reaches
PyPI until a version is cut per plan 005.
Owner: Gal Sarig
Last updated: 2026-08-15

Keeps the `jsonl://` backend exactly as it is and changes only what the
documentation claims about it: from a co-equal storage option listed beside
SQLite and PostgreSQL, to a narrow export/shipping format that is **not
recommended** for general use, with `sqlite://` named as the right answer
whenever the objection is "no database server".

## Goal

Stop a reader from picking `jsonl://` by accident.

Today the README's opening bullet reads "Writes to SQLite, PostgreSQL,
MySQL/MariaDB or JSONL" and the install line reads "SQLite + JSONL, no
dependencies", which presents JSONL as one of four peers and as half of what the
zero-dependency install buys. A reader who wants "a log without running a
database server" will plausibly land on `jsonl://` — and then discover, at
runtime, that `delete_events()` raises, `id` is always `None`, and every query is
a full file scan.

Every one of those is correct and deliberate behaviour. The defect is that the
documentation does not set the expectation *before* the user commits.

After this change: `sqlite://` is the documented no-server default, and
`jsonl://` is documented as the choice for one specific job — writing a file that
another system (Fluent Bit, Vector, Loki, S3 + Athena, a log collector) will pick
up and own.

## Scope

**In scope** — documentation and guidance only:

- `README.md:7` — the opening bullet listing JSONL beside three databases.
- `README.md:36` — "SQLite + JSONL, no dependencies" on the install line.
- `README.md:147` — the DSN table row.
- `README.md:267` — the `delete_events()` note.
- `README.md:411` — the Limitations bullet.
- `docs/features/configuration.md:76` — the DSN table row.
- `docs/features/read-api.md:111-112` — the two per-backend rows.
- `docs/features/delete-api.md:87` — the per-backend row, whose "deferred, not
  rejected" claim is reversed (question 3).
- A new `docs/features/jsonl-backend.md` (question 1) — the feature doc that owns
  this backend, which does not exist today.
- `TODO.md`, "Delete side" — the deferred `delete_events()` for `jsonl://` item,
  which is removed outright (question 3).
- `CHANGELOG.md` under `[Unreleased]`.
- Module docstrings in `src/eventlog_pro/backends/jsonl.py:1-8` and the scheme's
  mention in `src/eventlog_pro/dsn.py`, if they overstate the backend's
  generality (to be confirmed while editing; the `jsonl.py` docstring is already
  honest and may need nothing).

**Out of scope**

- **Any change to `src/eventlog_pro/backends/jsonl.py` behaviour.** No new
  warning, no deprecation, no removal (question 2). The code is correct; this
  plan disputes only the docs.
- **Removing the backend.** Considered and rejected in conversation on
  2026-08-15: it is a public DSN scheme shipped in 0.1.0, it is the only durable
  zero-dependency option that survives a restart (`memory://` does not,
  `null://` discards), and it serves the ship-to-a-collector case that no SQL
  backend serves.
- **Implementing `delete_events()` for `jsonl://`.** Question 3 settles it as
  rejected rather than deferred; nothing is built, and the roadmap item goes
  away.
- **The `id is None` behaviour.** Documented, deliberate, and explained in the
  module docstring. It gets described more prominently, not changed.
- Plans 001–007, which record what was true when written.

## Assumptions

- This is a documentation-only change and rides along with whatever ships next
  (question 4), so no version bump happens here and `__about__.py` is untouched.
- No consumer has to do anything. Existing `jsonl://` users keep working
  identically; they only read different guidance if they revisit the docs.
- `pel-automation` runs Django (plan 003) and is unaffected either way.
- The zero-dependency promise is unchanged and stays prominent — the fix is to
  attribute it to SQLite, which is stdlib, rather than to "SQLite + JSONL".

## Open Questions

**Question:** Where should the "not recommended, and here is when it *is* right"
guidance live?
(1) A new `docs/features/jsonl-backend.md` that owns the backend, with the short discouragement inline in the README and the other docs linking to it.
(2) Inline everywhere — expand the README and the three existing feature docs, create no new file.
(3) A general `docs/features/choosing-a-backend.md` covering all seven schemes, with JSONL as one section.

- **Recommendation:** 1 — `AGENTS.md` requires a feature doc per feature, and
  `jsonl://` has none today, so the doc is owed regardless. It also gives the
  README a single link to point at instead of repeating the caveats in four
  places. Option 3 is the better long-term shape but is a much larger write-up;
  it can absorb the JSONL doc later.

- **Answer:** 1


**Question:** Should `jsonl://` also emit a runtime warning (one per process, on
first use) saying it is not the recommended backend?
(1) No — documentation only, exactly as asked. The code stays untouched.
(2) Yes, a one-per-process `logging` warning naming `sqlite://` as the alternative.
(3) Yes, but only when the path is under the working directory, which suggests a dev machine rather than a deliberate shipping setup.

- **Recommendation:** 1 — you asked for docs, and a warning punishes the users
  who chose `jsonl://` correctly for the collector case. The unconfigured-default
  fallback already warns; this would be the second warning on a *configured*
  choice, which reads as noise. Say if you want 2 and it is a small addition.

- **Answer:** 1


**Question:** `docs/features/delete-api.md:87` says a `jsonl://` delete is
"deferred, not rejected", and `TODO.md` lists it under "Delete side" as
something still open. Does that stand?
(1) Flip both to rejected — say plainly that deleting rows from an append-only file is not a thing this package will do, and that rotation is the answer. Remove the `TODO.md` item.
(2) Leave both as deferred; this plan changes only the recommendation, not the roadmap.
(3) Flip the docs to rejected but keep a short `TODO.md` note recording *why*, so it is not rediscovered.

- **Recommendation:** 3 — holding it open contradicts the message this plan is
  sending, and a read-filter-rewrite is exactly the operation whose crash window
  makes it a bad fit. But `TODO.md` opens by saying its purpose is so decisions
  are "not rediscovered from scratch", so the reasoning is worth two lines even
  once the answer is no.

- **Answer:** 1


**Question:** How does this ship?
(1) Its own branch and PR, released as `0.2.1` when merged.
(2) Its own branch and PR, merged to `main` but left under `[Unreleased]` to ride along with whatever ships next.
(3) Straight to `main` — it is documentation only.

- **Recommendation:** 2 — the guidance costs nothing sitting on `main`, and
  cutting a release whose entire content is a docs clarification is more
  ceremony than it earns. Plan 005's PR rule applies either way, so 3 is out
  unless you say otherwise.

- **Answer:** 2


## Steps

1. **Write `docs/features/jsonl-backend.md`** (question 1). Describes current
   behaviour only, per `AGENTS.md`. Sections: what it writes (one
   `json.dumps` line per event, appended under a lock, `backends/jsonl.py:50-61`);
   **when to use it** (you are shipping the file to a collector that will own
   it, and that collector assigns identity); **when not to** (you intend to query
   or delete through this package — use `sqlite://`); the three consequences
   (`id` is `None`, reads are full scans with sort and `limit` applied in memory
   afterwards, `delete()` raises); and retention by rotation rather than by
   `delete_events()`.

2. **Fix the README's framing.** Line 7 stops listing JSONL as a fourth database
   — the bullet becomes SQLite, PostgreSQL and MySQL/MariaDB, with JSONL named
   separately as an export target. Line 36's install comment becomes SQLite-only,
   since that is what carries the zero-dependency claim.

3. **Annotate the two DSN tables** — `README.md:147` and
   `docs/features/configuration.md:76` — so the JSON Lines row carries a short
   "append-only; export/shipping only, not for querying — see
   [jsonl-backend.md]" note rather than sitting unqualified beside PostgreSQL.

4. **Add the recommendation where the objection actually arises.** Wherever the
   docs address "no database server", name `sqlite://` explicitly: it is stdlib,
   zero-dependency, needs no server, and supports the full read and delete API.
   That is the sentence that does most of the work in this plan.

5. **Strengthen the existing caveats** at `README.md:267`, `README.md:411`,
   `docs/features/read-api.md:111-112` and `docs/features/delete-api.md:87` —
   they are accurate today but read as footnotes. Each gets the link from step 1.

6. **Settle the deferred delete as rejected** (question 3). In
   `docs/features/delete-api.md:87`, drop "A read-filter-rewrite implementation
   is deferred, not rejected — see `TODO.md`" and say instead that deleting rows
   from an append-only file is not something this package will do, and that
   rotation is the answer. In `TODO.md`, remove the "**`delete_events()` for
   `jsonl://`**" bullet under "Delete side" entirely. The *reasoning* is not lost
   by removing it: the same crash-window explanation stays in
   `delete-api.md`, in the `delete()` docstring at `backends/jsonl.py:86-96`, and
   in the runtime error message — so a future reader still finds the why at the
   place they would look.

7. **Check the source docstrings** — `src/eventlog_pro/backends/jsonl.py:1-8`
   and the `jsonl` mentions in `src/eventlog_pro/dsn.py` — and align any that
   present the backend as general-purpose. Expected to be a small or empty diff.

8. **Add the `CHANGELOG.md` entry** under `[Unreleased]`, in a `Documentation`
   (or `Changed`) subsection: `jsonl://` is documented as export-only and not
   recommended for general use; `sqlite://` is the recommended
   no-database-server backend; **no behaviour changed and no DSN was removed**.
   That last clause is the point of the entry — a reader scanning the changelog
   must not think their `jsonl://` deployment is being taken away.

## Validation

Docs-only, so the test suite is a regression check rather than the proof:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m ruff format --check .
.\.venv\Scripts\python.exe -m mypy --strict src
```

`ruff format --check` is the one CI runs and the one this plan originally
omitted — `ruff check` passes on code the formatter would still rewrite, so
running only the former misses a red `lint` job. It caught a pre-existing
failure in `gs_tests/check_event_log.py` inherited from `b7c22d7`, fixed on this
branch so `main` is taggable again.

All three must be unchanged from before the plan — if `pytest` output moves,
step 7 changed behaviour and should not have.

```powershell
grep -rn "jsonl" --include=*.md README.md CHANGELOG.md TODO.md docs
```

Every remaining mention should either carry the caveat or link to
`docs/features/jsonl-backend.md`. No mention should list JSONL as a peer of the
SQL backends without qualification.

Then read `README.md` top to bottom as a new user: the answer to "I do not want
to run a database server" must be `sqlite://`, reachable without reading the DSN
table closely.

## Risks

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| An existing `jsonl://` user reads the changelog as a deprecation and migrates under pressure | medium | medium | step 8 states explicitly that nothing changed and nothing was removed; question 2's answer keeps the runtime silent |
| The docs over-correct and nobody finds the backend for the collector case it is genuinely good at | medium | low | step 1's doc leads with **when to use it**, not with the caveats |
| A caveat is strengthened in one file and left stale in another | medium | low | the `grep` in Validation; step 5 lists all four sites |
| Step 7 quietly changes behaviour while editing docstrings | low | medium | the unchanged-`pytest` check in Validation |
| The new feature doc drifts from the code as the backend changes | low | low | `AGENTS.md` already requires docs and code to move together |

## Rollout Order

1. Branch from `main` (question 4).
2. Step 1 — the new feature doc, which the rest links to.
3. Steps 2–5 — README and the three existing feature docs, one commit.
4. Steps 6–7 — `TODO.md` and the source docstrings.
5. Step 8 — the changelog entry under `[Unreleased]`.
6. PR to `main`, green CI, merge. **No release and no version bump** (question
   4) — the entry stays under `[Unreleased]` until the next release picks it up,
   at which point plan 005 owns the mechanics.

## Rollback

Revert the commit. Nothing outside the repository changes, no published
behaviour depends on any of it, and no user action is required at any point —
which is the whole argument for doing this with documentation rather than with a
deprecation or a removal.
