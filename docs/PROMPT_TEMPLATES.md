# AI Prompt Templates — MSSP Control Plane

Location: `/opt/mssp-control/docs/PROMPT_TEMPLATES.md`

These are reusable prompt templates for working with Cursor, Claude, or ChatGPT on this project. Copy a template, fill in the bracketed parts, and send it as your message to the AI agent. Every template assumes the agent has already read `AGENTS.md`, `CLAUDE.md`, and `.cursor/rules/mssp-control-plane.mdc`.

---

## 1. Planning Prompt Template

Use this when you want to think through an approach **before** any code is written.

```
You are working inside /opt/mssp-control on branch [BRANCH NAME].
This is KB-[MODULE NUMBER]: [short module name].

Do not write or edit any code yet. This is a planning-only request.

Goal:
[Describe in plain language what you want this module to achieve.]

Context to consider:
- Current validated baseline: kb008-validated-foundation (commit c52bca1)
- Existing schema: postgres/init/001_mssp_core_schema.sql
- Existing backend: backend-api/app/main.py
- Rules: AGENTS.md, CLAUDE.md, .cursor/rules/mssp-control-plane.mdc

Please:
1. Inspect the relevant parts of the project (tree, current branch, git status, relevant files).
2. Propose a short, plain-language plan for how to implement this.
3. List the exact files you would create or edit.
4. Call out any security or tenant-isolation implications.
5. Call out anything that would count as a "large architectural change" and needs explicit approval.
6. Do NOT make any file changes yet. Stop after presenting the plan and wait for my approval.
```

---

## 2. Implementation Prompt Template

Use this once a plan has been approved and you want the AI agent to actually write the code.

```
You are working inside /opt/mssp-control on branch [BRANCH NAME].
This is KB-[MODULE NUMBER]: [short module name].

Approved plan:
[Paste the approved plan here, or reference the prior message.]

Do:
- [Exact task 1]
- [Exact task 2]
- [Exact task 3]

Do not:
- Modify [file/files not part of this task]
- Restart Docker containers
- Commit anything
- Make architectural changes beyond what was approved

Follow AGENTS.md and CLAUDE.md rules exactly, including:
- Complete, production-ready file contents (no placeholders, no TODOs)
- Modular backend structure (core/, db/, api/routes/, schemas/, services/)
- Tenant isolation on every tenant-owned table/endpoint
- No hardcoded secrets; secrets only via environment variables
- Parameterized SQL only

When done:
1. Show git status --short.
2. Give me the exact validation commands to run, with expected output.
3. Stop and wait. Do not commit.
```

---

## 3. Debugging Prompt Template

Use this when something is broken and you need the AI agent to investigate and fix it, without guessing blindly.

```
You are working inside /opt/mssp-control on branch [BRANCH NAME].

Something is broken. Here is what I observed:

Command I ran:
[Paste exact command]

Output I got:
[Paste exact output, including errors/stack traces]

What I expected instead:
[Describe expected behavior/output]

Please:
1. Confirm current git branch and git status first.
2. Read the relevant files involved (name them) before proposing a fix.
3. Explain, in plain language, what you think is causing the problem.
4. Propose the smallest possible fix that resolves it without touching unrelated code.
5. Do not restart Docker containers unless you explain why it's needed and I confirm.
6. Do not modify backend-api/app/main.py, docker-compose.yml, or the schema file unless the fix requires it — if it does, say so explicitly before doing it.
7. After the fix, show git status --short and give me exact validation commands with expected output.
8. Stop and wait. Do not commit.
```

---

## 4. Code Review Prompt Template

Use this to have an AI agent review changes (its own or a human's) before committing.

```
You are working inside /opt/mssp-control on branch [BRANCH NAME].

Please review the following changes (do not modify anything yet):
[Paste git diff, or say "review the current uncommitted changes via git status/git diff"]

Review checklist:
1. Does this change enforce tenant isolation on every tenant-owned table/endpoint it touches?
2. Does this change avoid hardcoded secrets, and read all config from environment variables?
3. Does this change use parameterized SQL (no string-built queries)?
4. Does this change return password hashes or other sensitive data anywhere in API responses? (It must not.)
5. Does this change handle errors safely (no stack traces exposed to customers, useful logs for SOC/admin)?
6. Does this change follow the modular backend structure in AGENTS.md, rather than piling logic into main.py?
7. Are there any placeholders, TODOs, or incomplete code blocks that must not ship?
8. Does this change touch any do-not-touch file without explicit instruction?

Please report:
- Any issues found, with file and line references.
- Whether this change is safe to commit as-is, or what must be fixed first.
- Do not make edits yourself unless I explicitly ask you to fix the issues you found.
```

---

## 5. KB-010 Initial Prompt

This is the prompt to use to actually start KB-010 (Authentication/Login + Role-Based Access Control) when ready. Do not use this until KB-009A is reviewed and you are ready to begin real backend work again.

```
You are working inside /opt/mssp-control on branch kb010-auth-rbac (create this branch from the current validated branch if it does not exist yet — confirm with me first).

This is KB-010: Authentication/Login + Role-Based Access Control (RBAC).

Follow AGENTS.md, CLAUDE.md, and .cursor/rules/mssp-control-plane.mdc exactly.

Goal:
Add secure authentication and role-based access control to the FastAPI backend, using the existing platform_users table (postgres/init/001_mssp_core_schema.sql), without changing the database schema unless you explain why and I approve it first.

Required behavior:
1. A login endpoint that accepts email + password and returns a JWT (or equivalent) access token on success, and a safe generic error on failure (no indication of whether the email or password was wrong).
2. Passwords must be verified against a securely hashed value (bcrypt or argon2). Explain how existing platform_users rows will get a hashed password if none exists yet.
3. A reusable dependency/middleware that verifies the token on protected endpoints and exposes the caller's user id, tenant_id (if any), and role to the route.
4. Role-based access control matching platform_users.role values: super_admin, soc_manager, soc_analyst, customer_admin, customer_viewer.
5. Tenant scoping: customer_admin and customer_viewer tokens must only ever be able to access their own tenant_id's data.
6. New code must be organized under backend-api/app/core/security.py, backend-api/app/api/routes/auth.py, backend-api/app/schemas/, and backend-api/app/services/ — not added directly into the existing main.py logic (main.py may only be edited to wire in the new router).
7. Never log or return plaintext passwords or password hashes anywhere.

Before writing code:
1. Inspect current project tree, git branch, and git status.
2. Read backend-api/app/main.py and the platform_users table definition in the schema file.
3. Propose a short plan and exact file list, and wait for my approval before editing anything.

After implementation:
1. Show git status --short.
2. Provide a new validation script scripts/kb010_validate_auth_rbac.sh following the kb008 script pattern, plus the exact curl/jq commands to test login success, login failure, and at least one role-protected endpoint.
3. Stop and wait. Do not commit.
```
