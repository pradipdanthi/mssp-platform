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

## 6. Next Module: KB-010

The next real software module after this documentation module (KB-009A) is:

**KB-010 — Authentication / Login + Role-Based Access Control (RBAC)**

Expected shape of that work (for context, not to be started now):
- Secure password hashing for `platform_users`.
- Login endpoint issuing JWT (or equivalent) tokens.
- Middleware/dependency to verify tokens and extract the caller's `tenant_id` and `role`.
- Role checks for `super_admin`, `soc_manager`, `soc_analyst`, `customer_admin`, `customer_viewer` (matching the `platform_users.role` check constraint already in the schema).
- Tenant-scoping enforcement on customer-role endpoints.
- New code organized under `backend-api/app/core/security.py`, `backend-api/app/api/routes/auth.py`, and related `schemas`/`services` modules per the structure in `AGENTS.md` section 7 — not dumped into `main.py`.
- A new validation script, e.g. `scripts/kb010_validate_auth_rbac.sh`, following the KB-008 script pattern.

Do not start KB-010 implementation until the user explicitly kicks it off in a new prompt.
