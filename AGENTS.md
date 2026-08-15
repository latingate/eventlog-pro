# AGENTS.md — Guidance for AI coding agents

Owner: Gal Sarig ~ Last updated: 15/08/2026

**Purpose:** Quickly orient an AI coding agent to be productive in this repository (Django project). Focused, actionable
facts and file references drawn from the code.

## Planning (REQUIRED)

- Before ANY implementation follow .claude/rules/planning-rules.md
- Do NOT use Claude Code's internal plan system as a substitute
- This is mandatory, not optional

## Feature workflow

When adding or changing one or more features:

- Feature docs live in `docs/features/<feature-name>.md` — one file per feature, kebab-case. Never combine multiple
  features into one doc.
- The doc describes current behavior, not history. Git holds the history.
- Before writing code, list every feature the change touches, and read each of their docs first. Follow the conventions
  in them.
- Update every feature doc the change touches, in the same commit as the code. Create any that don't exist. A change
  spanning three features updates three docs.
- If a change to one feature alters the behavior of another, update both docs — don't leave the second one stale.
- A feature is not done until docs and code agree.
- If a change alters a project-wide convention, update the `.claude/rules/` file that owns it (naming, style, testing,
  security, etc.) rather than restating it in the feature doc. If it alters architecture, glossary terms, or product
  scope, update the matching `docs/` file. Only update CLAUDE.md if the change affects which files get loaded or how the
  workflow itself operates.
