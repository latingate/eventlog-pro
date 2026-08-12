# Planning Rules

## Purpose
- Define how plans are created, reviewed, and executed in this repository.

## Plan Location and Lifecycle
- Treat `.claude/plans/` at the repository root as the source of truth for plans.
- For any plan-related request, fir3st read existing `.claude/plans/*.md` plans, even when no specific plan file is referenced.
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

## Supersession Rule
- If a plan is replaced, mark the old plan `Status: superseded` and add a link to the replacing plan.
