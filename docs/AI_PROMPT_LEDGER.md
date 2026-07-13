# AI Prompt Ledger — MSSP Control Plane

Location: `/opt/mssp-control/docs/AI_PROMPT_LEDGER.md`

This is a running log of significant AI-assisted prompts and changes made to this repository. It exists so anyone (including a future AI agent) can see what was asked, what was actually changed, whether it was validated, and which commit it ended up in.

## How to use this ledger

- Add one row per significant AI-assisted change (a KB module, a bug fix, a meaningful refactor). Small, purely exploratory questions that made no file changes do not need a row.
- Fill in "Commit ID" only after the human has reviewed and committed the change. Use `pending` until then.
- Use the "Validation Result" column to record whether validation passed, failed, or was not yet run — do not leave it blank.
- Keep entries in chronological order (oldest first).

---

## Ledger

| Date | KB Module | Prompt Summary | Files Changed | Validation Result | Commit ID |
|---|---|---|---|---|---|
| 2026-07-13 | KB-009A | Create permanent AI development context/rule files for Cursor, Claude, and future coding agents (AGENTS.md, CLAUDE.md, Cursor rule, KB-009 workflow doc, prompt templates, this ledger). Documentation only, no runtime/code changes. | `AGENTS.md`, `CLAUDE.md`, `.cursor/rules/mssp-control-plane.mdc`, `docs/KB009_AI_DEVELOPMENT_WORKFLOW.md`, `docs/PROMPT_TEMPLATES.md`, `docs/AI_PROMPT_LEDGER.md` | Not yet run (documentation-only change; existing validation commands unaffected — to be confirmed by user) | pending |

---

## Template Row (copy this for new entries)

| Date | KB Module | Prompt Summary | Files Changed | Validation Result | Commit ID |
|---|---|---|---|---|---|
| YYYY-MM-DD | KB-0NN | [One or two sentence summary of what was asked] | `path/to/file1`, `path/to/file2` | [Passed / Failed — reason / Not yet run] | [commit hash or `pending`] |
