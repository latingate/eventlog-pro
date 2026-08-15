# Planning Rules

Owner: Gal Sarig ~ Last updated: 15/08/2026

## Purpose

- Define how plans are created, reviewed, and executed in this repository.

## Plan Location and Lifecycle

- Treat `.claude/plans/` at the repository root as the source of truth for plans.
- For any plan-related request, fir3st read existing `.claude/plans/*.md` plans, even when no specific plan file is
  referenced.
- Save every new or updated implementation plan as a Markdown file in `.claude/plans/`.
- If `.claude/plans/` does not exist, create it before writing plan files.

## File Naming

- Use this filename format for new plans: `001-YYYY-MM-DD-<topic>.md`.
- Use sequential numeric prefixes: `001`, `002`, `003`, and so on.

## Collaboration Rules

- Ask all plan questions directly in the plan file.
- Make questions easy to respond to, and include a recommended answer when possible.
- After answers are provided, update the plan accordingly.
- Request approval before executing the plan.

## Content Rules

- Use repository-relative paths in plan content.
- Do not use machine-specific absolute paths.

## Required Plan Metadata

- Include these fields near the top of each plan:
    - `Status:` `draft|active|done|superseded`
    - `Owner:`
    - `Last updated:` `YYYY-MM-DD`

## Required Plan Sections

- Every plan must include:
    - `Goal`
    - `Scope`
    - `Assumptions`
    - `Open Questions`
    - `Steps`
    - `Validation`
    - `Risks`
    - `Rollout Order`
    - `Rollback`

### Open Questions section

- Use this format sub-sections for each question:
    - `**Question:** <question>` - if question is not an open question and have multiple answers to choose from, put
      every answer in a separate line, starting with a number in this format `(1) <answer>`  `(2) <answer>` and the user
      can simply reply with that number. You can also add another answer such as "Other. Enter your own answer or follow
      up question."
    - `**Recommendation:** <recommendation>`
    - `**Answer:** <answer>` - if there is no answer yet – put one space instead of <answer> so that the answer the user
      types will not be right after the `**`. Do not put `_pending_` or any other text or symbol instead
    - Put a line break between these sub-sections. Do not put empty lines between them.
    - Start `Recommendation:` and `Answer:` with `- `, or Markdown merges them into the last numbered answer. Indent
      wrapped lines by two spaces to keep them in the bullet.
    - Insert 2 line breaks between the questions.

## Supersession Rule

- If a plan is replaced, mark the old plan `Status: superseded` and add a link to the replacing plan.
