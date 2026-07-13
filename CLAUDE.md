# CLAUDE.md — Claude / Cursor Operating Instructions

Status: Permanent reference document. Created in KB-009A.
Audience: Claude (in Cursor or Claude Code), and any other AI coding agent that reads a `CLAUDE.md` convention file.

This file tells you, the AI agent, exactly how to operate in this repository. `AGENTS.md` is the full rulebook (project overview, architecture, security, tenant isolation, coding standards). This file is the shorter "how to behave right now" companion — read both.

---

## 1. Files to Read First (every session)

Before doing anything in this repository, read, in this order:

1. `/opt/mssp-control/AGENTS.md` — full project rules, architecture, security, tenant isolation, coding standards.
2. `/opt/mssp-control/.cursor/rules/mssp-control-plane.mdc` — condensed always-applied rule set (Cursor will usually inject this automatically).
3. `/opt/mssp-control/docs/KB009_AI_DEVELOPMENT_WORKFLOW.md` — how ChatGPT/Cursor/Claude are meant to work together on this project, and the branch/validation workflow.
4. The specific files relevant to the current task (e.g. `backend-api/app/main.py`, `postgres/init/001_mssp_core_schema.sql`, `docker-compose.yml`) — always read a file before editing it.
5. `docs/AI_PROMPT_LEDGER.md` — to see what previous AI-assisted changes were made, so you don't repeat or contradict them.

If any of these files are missing or seem out of date compared to the real state of the repository, say so before proceeding — do not silently assume.

---

## 2. Behavior Rules

- **Inspect before acting:** check the project tree, current Git branch, and `git status` before making any change.
- **Plan before editing:** give a short, plain-language plan and the exact file list before touching files.
- **Minimal, targeted changes:** only make the changes requested for the current KB module/task. Do not refactor, rename, or "clean up" unrelated code.
- **Complete output only:** every file you write must be complete and production-ready. No `# TODO`, no `// implement later`, no `...rest of code...`, no placeholders of any kind.
- **Respect the do-not-touch list** from `AGENTS.md` section 4 unless the current task explicitly names that file.
- **Never restart Docker containers** unless explicitly instructed.
- **Never commit.** Never run `git add .`. Never run `git commit` unless the user's message explicitly asks for a commit in that same request.
- **Stop and ask** when instructions are ambiguous, contradict `AGENTS.md`, or would require a large architectural change (framework swap, database engine change, tenant isolation model change, etc.).
- **Security first:** never print `.env` values, never hardcode secrets, never let tenant data leak across tenants, never return password hashes, always use parameterized SQL.

---

## 3. Output Style (this user is not a programmer)

- Explain what you're doing in plain English before and after doing it.
- Always name the exact file being created/edited, with its full path from `/opt/mssp-control/`.
- Give complete file contents or complete, unambiguous edits — never partial snippets requiring the user to fill anything in.
- Give exact, copy-pasteable commands, including the working directory.
- Show the expected output of each command so the user can tell success from failure at a glance.
- After making changes, always show `git status --short` so the user can see exactly what changed.
- Always end a change-making task with: a short summary, the exact file list touched, `git status --short` output, and validation commands to run — then stop and wait. Do not commit.

---

## 4. What to Avoid

- Do not use pseudo-code in production files.
- Do not say "add the rest yourself" or leave a function body empty/half-written.
- Do not hide a failed command's output — always show it and explain what went wrong.
- Do not touch `backend-api/app/main.py`, `docker-compose.yml`, or `postgres/init/001_mssp_core_schema.sql` unless the task explicitly instructs it.
- Do not convert the product to Streamlit. Streamlit is prototype/demo-only, never the production dashboard.
- Do not expose Wazuh directly to customers or assume Wazuh credentials/URLs that were not given to you.
- Do not invent tenant data, customer data, or credentials — use clearly-fake placeholder values if an example is needed.
- Do not run `docker compose down`, `docker compose restart`, or similar unless explicitly instructed.
- Do not create frontend scaffolding before a frontend module is explicitly started.

---

## 5. Validation Discipline

Every code change must come with a way to verify it worked. At minimum, these commands must still succeed after any backend/infra change:

```bash
cd /opt/mssp-control
git branch --show-current
git status --short
docker compose ps
curl -fsS http://localhost:8000/health | jq .
./scripts/kb008_validate_backend_api_foundation.sh
```

For a new module (e.g. KB-010 auth), also provide a new validation script or explicit `curl`/`jq` commands specific to that module's new endpoints, following the pattern in `scripts/kb008_validate_backend_api_foundation.sh` (clear section headers, explicit pass/fail checks, non-zero exit on failure).

Rules:
- Never claim a change works without showing the command and its actual/expected output.
- If a validation command fails, show the failure verbatim and propose a fix — do not paper over it.
- Do not mark a KB module "done" until its validation script or command set passes.

---

## 6. Current Module: KB-011 (implemented and VALIDATED)

**KB-010 Phase 1 — Authentication / Login + Role-Based Access Control foundation — validated, committed (`7fbb3d2`), tagged `kb010-auth-rbac-phase1-validated`:**
- `platform_users.password_hash` column added (nullable, bcrypt hashes only).
- The top admin role was renamed from `super_admin` to `platform_admin`.
- Endpoints: `POST /auth/login`, `GET /auth/me`, `GET /auth/roles`.
- JWT (PyJWT) access tokens; `get_current_user` re-checks the live database on every request (not just the token payload).
- `require_roles(*roles)` and `require_tenant_match(...)` dependencies in `backend-api/app/api/dependencies.py`.
- Demo users: `soc.manager@example.local` (`soc_manager`), `customer.viewer@demo.local` (`customer_viewer`).

**KB-011 — Protect existing `/admin/*` and `/customer/*` endpoints — implemented and VALIDATED:**
- `backend-api/app/main.py` edited: 5 `/admin/*` endpoints now use `Depends(require_roles("platform_admin", "soc_manager", "soc_analyst"))`; both `/customer/*` endpoints now use `Depends(get_current_user)` plus a `require_tenant_match(tenant["id"], current_user)` call. No changes to `dependencies.py`, `auth.py`, or the database schema.
- Tenant-mismatch on `/customer/*` returns **404** (not 403) to avoid confirming another tenant's existence — this reuses the existing KB-010 `require_tenant_match` behavior unchanged.
- New fixture data (via new script, not a schema migration): tenant `DEMO2`, and demo users `platform.admin@example.local` (`platform_admin`), `soc.analyst@example.local` (`soc_analyst`), `customer.admin@demo2.local` (`customer_admin`, tenant `DEMO2`).
- New scripts: `scripts/kb011_seed_rbac_fixtures.sh` (creates the fixtures above; hidden password prompts, bcrypt hashes only) and `scripts/kb011_validate_protected_apis.sh` (full 401/403/404/200 coverage across all 5 roles and all 7 protected endpoints).
- Full plan: `docs/KB011_IMPLEMENTATION_PLAN.md`. Decisions: `docs/KB011_DECISION_QUESTIONS.md` (all approved as recommended: 1A, 2A, 3A, 4A). Completion summary: `docs/KB011_PROTECTED_APIS_COMPLETION.md`.

**Status: implementation complete, validation PASSED.** Result: `KB-011 PROTECTED APIS VALIDATION PASSED`. **Not yet committed** — the user decides when to commit.

**Known, intentional side effect:** `scripts/kb008_validate_backend_api_foundation.sh` and `scripts/kb010_validate_auth_rbac.sh` (which internally re-runs the KB-008 script) now fail on their unauthenticated `/admin/*`/`/customer/*` checks, because those endpoints now correctly require a token. Both scripts are left unmodified as historical records; `scripts/kb011_validate_protected_apis.sh` is the current must-pass gate for those endpoints.

Do not start a KB-012 module until the user explicitly kicks it off in a new prompt.
