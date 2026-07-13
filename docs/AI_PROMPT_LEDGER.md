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
| 2026-07-13 | KB-010 (Phase 1) | Implement Authentication/Login + Role-Based Access Control foundation: bcrypt password hashing, JWT access tokens, `POST /auth/login`, `GET /auth/me`, `GET /auth/roles`, `require_roles`/`require_tenant_match` RBAC dependencies, `platform_users.password_hash` migration, role rename `super_admin` → `platform_admin`, demo users seeded (`soc.manager@example.local`, `customer.viewer@demo.local`). Existing `/admin/*`/`/customer/*` preview endpoints intentionally left unprotected (Phase 2 deferred). | `backend-api/app/core/config.py`, `backend-api/app/core/security.py`, `backend-api/app/db/session.py`, `backend-api/app/api/dependencies.py`, `backend-api/app/api/routes/auth.py`, `backend-api/app/schemas/auth.py`, `backend-api/app/services/auth_service.py`, `backend-api/app/main.py`, `backend-api/requirements.txt`, `docker-compose.yml`, `postgres/init/002_kb010_auth_rbac.sql`, `scripts/kb010_create_auth_rbac.sh`, `scripts/kb010_validate_auth_rbac.sh`, `AGENTS.md`, `CLAUDE.md`, `.cursor/rules/mssp-control-plane.mdc`, `docs/KB009_AI_DEVELOPMENT_WORKFLOW.md`, `docs/PROMPT_TEMPLATES.md` | Not yet run by the agent (shell execution was unavailable this session) — user must run `scripts/kb010_create_auth_rbac.sh` then `scripts/kb010_validate_auth_rbac.sh` and confirm result | pending |

---

## Template Row (copy this for new entries)

| Date | KB Module | Prompt Summary | Files Changed | Validation Result | Commit ID |
|---|---|---|---|---|---|
| YYYY-MM-DD | KB-0NN | [One or two sentence summary of what was asked] | `path/to/file1`, `path/to/file2` | [Passed / Failed — reason / Not yet run] | [commit hash or `pending`] |
