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
| 2026-07-13 | KB-010 (Phase 1) | Implement Authentication/Login + Role-Based Access Control foundation: bcrypt password hashing, JWT access tokens, `POST /auth/login`, `GET /auth/me`, `GET /auth/roles`, `require_roles`/`require_tenant_match` RBAC dependencies, `platform_users.password_hash` migration, role rename `super_admin` → `platform_admin`, demo users seeded (`soc.manager@example.local`, `customer.viewer@demo.local`). Existing `/admin/*`/`/customer/*` preview endpoints intentionally left unprotected (Phase 2 deferred). | `backend-api/app/core/config.py`, `backend-api/app/core/security.py`, `backend-api/app/db/session.py`, `backend-api/app/api/dependencies.py`, `backend-api/app/api/routes/auth.py`, `backend-api/app/schemas/auth.py`, `backend-api/app/services/auth_service.py`, `backend-api/app/main.py`, `backend-api/requirements.txt`, `docker-compose.yml`, `postgres/init/002_kb010_auth_rbac.sql`, `scripts/kb010_create_auth_rbac.sh`, `scripts/kb010_validate_auth_rbac.sh`, `AGENTS.md`, `CLAUDE.md`, `.cursor/rules/mssp-control-plane.mdc`, `docs/KB009_AI_DEVELOPMENT_WORKFLOW.md`, `docs/PROMPT_TEMPLATES.md` | Passed — validated on branch `kb010-auth-rbac`, committed as `7fbb3d2`, tagged `kb010-auth-rbac-phase1-validated` | 7fbb3d2 |
| 2026-07-13 | KB-011 | Protect existing `/admin/*` and `/customer/*` preview endpoints with the KB-010 auth foundation: `Depends(require_roles(*ADMIN_SOC_ROLES))` on all 5 `/admin/*` endpoints, `Depends(get_current_user)` + `require_tenant_match(...)` on both `/customer/*` endpoints (404, not 403, on tenant mismatch — anti-enumeration). Added a permanent second demo tenant (`DEMO2`) and demo accounts for the 3 previously-missing roles (`platform_admin`, `soc_analyst`, `customer_admin`). No changes to `dependencies.py`, `auth.py`, the database schema, or `docker-compose.yml`. | `backend-api/app/main.py`, `scripts/kb011_seed_rbac_fixtures.sh` (new), `scripts/kb011_validate_protected_apis.sh` (new), `docs/KB011_DECISION_QUESTIONS.md` (new), `docs/KB011_IMPLEMENTATION_PLAN.md` (new), `docs/KB011_PROTECTED_APIS_COMPLETION.md` (new), `AGENTS.md`, `CLAUDE.md`, `.cursor/rules/mssp-control-plane.mdc` | **Passed** — user ran `scripts/kb011_seed_rbac_fixtures.sh` then `scripts/kb011_validate_protected_apis.sh` and confirmed result: `KB-011 PROTECTED APIS VALIDATION PASSED`. Committed as `30ef305`, tagged `kb011-protected-apis-validated`. | 30ef305 |
| 2026-07-13 | KB-012 | Backend API Route Modularization Foundation (structure-only, no behavior change): moved the 5 `/admin/*` endpoints into `backend-api/app/api/routes/admin.py`, the 2 `/customer/*` endpoints into `customer.py`, and `GET /`/`GET /health` into `health.py` — all moved unchanged (same paths, methods, SQL, response shapes, `Depends(...)` signatures). `backend-api/app/main.py` reduced to app wiring only (metadata, `FastAPI` object, 4 `include_router` calls). Added `redis_client()` to `backend-api/app/db/session.py`, moved unchanged from `main.py`, consolidating all DB/Redis helpers into one shared module. No changes to `dependencies.py`, `auth.py`, the database schema, or `docker-compose.yml`. | `backend-api/app/main.py`, `backend-api/app/db/session.py`, `backend-api/app/api/routes/health.py` (new), `backend-api/app/api/routes/admin.py` (new), `backend-api/app/api/routes/customer.py` (new), `scripts/kb012_validate_route_modularization.sh` (new), `docs/KB012_ROUTE_MODULARIZATION_COMPLETION.md` (new), `AGENTS.md`, `CLAUDE.md`, `.cursor/rules/mssp-control-plane.mdc` | **Passed** — user ran `scripts/kb012_validate_route_modularization.sh` (which reruns `scripts/kb011_validate_protected_apis.sh` unmodified as its behavior-regression gate) and confirmed result: `KB-012 ROUTE MODULARIZATION VALIDATION PASSED`. Not yet committed. | pending |

---

## Template Row (copy this for new entries)

| Date | KB Module | Prompt Summary | Files Changed | Validation Result | Commit ID |
|---|---|---|---|---|---|
| YYYY-MM-DD | KB-0NN | [One or two sentence summary of what was asked] | `path/to/file1`, `path/to/file2` | [Passed / Failed — reason / Not yet run] | [commit hash or `pending`] |
