# AGENTS.md — MSSP Control Plane AI Agent Rules

Status: Permanent reference document. Created in KB-009A.
Applies to: any AI coding agent working in this repository (Cursor, Claude Code, ChatGPT-assisted changes, or any future agent).

This file is the single source of truth for how an AI agent must behave in this repository. If any instruction from a user prompt conflicts with the safety rules in this file, the AI agent must stop and ask for confirmation instead of silently overriding this file.

---

## 1. Project Overview

We are building a **branded, web-based, AI-assisted MSSP / SOC control plane**.

This is **not**:
- A re-skinned Wazuh dashboard.
- A Streamlit prototype pretending to be the product.
- A single-tenant tool.

This **is**:
- A multi-tenant Managed Security Service Provider (MSSP) platform.
- A product where the SOC/admin team and paying customers each get their own branded dashboard.
- A platform that uses open-source security engines (Wazuh, Suricata, MISP, TheHive/Cortex, Shuffle/n8n, Prometheus/Grafana, etc.) as **backend adapters and data sources**, never as the customer-facing UI.

### Product goal

Deliver a full MSSP platform where:
- Our own backend (FastAPI) is the system of record and the only thing customers and SOC staff interact with directly.
- Detection tools like Wazuh and Suricata feed alerts into our backend through adapters.
- AI is used to translate raw technical alerts into plain-English summaries, business impact statements, and recommended actions for customers.
- SOC staff triage, investigate, and manage incidents through our own dashboard, not through third-party tool UIs.

### 1.1 SOC / Admin dashboard must support

- Customer/tenant onboarding
- Appliance activation token generation
- Appliance health monitoring
- Protected asset visibility
- Alert triage
- Incident management
- SOC analyst assignment
- Customer recommendation management
- Notification tracking
- Monthly reporting
- Audit/compliance visibility

### 1.2 Customer dashboard must support

- Customer security summary
- Customer appliance health
- Customer-visible incidents
- Plain-English alert/incident summaries
- Business impact explanation
- Customer action items
- Monthly reports
- Notification history

### 1.3 Backend platform services must support

- Authentication/login
- Role-based access control (RBAC)
- Tenant isolation
- Wazuh alert ingestion
- Suricata alert ingestion
- Appliance registration
- Appliance heartbeat API
- AI alert analysis worker
- WhatsApp notification worker
- Report generation

---

## 2. Architecture Decision (must not be silently changed)

The core product architecture is fixed as follows:

- **FastAPI** — backend API framework
- **PostgreSQL** — primary relational database
- **Redis** — cache / queue for background work
- **Docker Compose** — local/VM runtime orchestration
- **Future admin dashboard frontend** — not yet built
- **Future customer dashboard frontend** — not yet built
- **Wazuh and other open-source tools** — backend detection engines/adapters only

### Hard architecture rules

- Do **not** convert the main product into Streamlit. Streamlit may only be used later for quick internal prototypes or SOC demo screens — it is never the customer-facing production platform.
- Wazuh is a detection engine/adapter source, not the customer-facing product UI. Customers must never be given direct Wazuh logins. SOC/admin users work through our own platform dashboard; Wazuh data is normalized into our backend database.
- Suricata and other future tools (MISP, TheHive/Cortex, Shuffle/n8n, Prometheus/Grafana) follow the same adapter pattern: external tool → adapter/ingestion code → our own database → our own API → our own dashboards.
- Any AI agent proposing to change this architecture (e.g. "let's just use Streamlit for everything" or "let's expose Wazuh directly to customers") must stop and explain the proposed change in plain language and get explicit user approval before making it. This counts as a "large architectural change" under section 8.

---

## 3. Current Validated Baseline

- **VM name:** mssp-control
- **Project path:** `/opt/mssp-control`
- **Active Git branch:** `kb011-protect-admin-customer-apis`
- **Known-good baseline tag:** `kb008-validated-foundation`
- **Known-good baseline commit:** `c52bca1`
- **AI development rules tag:** `kb009a-ai-development-rules`
- **KB-010 Phase 1 validated tag:** `kb010-auth-rbac-phase1-validated` (commit `7fbb3d2`)
- **KB-011 status:** implemented and **VALIDATED** (`KB-011 PROTECTED APIS VALIDATION PASSED`) — not yet committed.

### Current services (Docker Compose)

| Container | Purpose |
|---|---|
| `mssp-postgres` | PostgreSQL database |
| `mssp-redis` | Redis cache/queue |
| `mssp-backend-api` | FastAPI backend |

### Current backend

- FastAPI backend lives in `backend-api/`.
- Current main backend file: `backend-api/app/main.py`.
- `/health` endpoint works and reports API, database, and Redis status.
- PostgreSQL connectivity works.
- Redis connectivity works.
- Admin/customer API endpoints exist and are now protected (KB-011), validated by `scripts/kb011_validate_protected_apis.sh`:
  - `GET /admin/dashboard` — `platform_admin`, `soc_manager`, `soc_analyst` only
  - `GET /admin/tenants` — `platform_admin`, `soc_manager`, `soc_analyst` only
  - `GET /admin/appliances` — `platform_admin`, `soc_manager`, `soc_analyst` only
  - `GET /admin/alerts` — `platform_admin`, `soc_manager`, `soc_analyst` only
  - `GET /admin/incidents` — `platform_admin`, `soc_manager`, `soc_analyst` only
  - `GET /customer/dashboard/{short_code}` — any authenticated role; `customer_admin`/`customer_viewer` limited to their own tenant (404 on mismatch)
  - `GET /customer/incidents/{short_code}` — same as above

### Current database

- PostgreSQL schema already exists.
- Schema file: `postgres/init/001_mssp_core_schema.sql`.
- **Do not delete, recreate, or replace the schema** unless explicitly instructed later.

Existing product tables:

```
tenants
platform_users
tenant_contacts
appliance_activation_tokens
appliances
protected_assets
appliance_heartbeats
security_alerts
incidents
incident_alerts
incident_timeline
incident_comments
notification_events
customer_recommendations
monthly_reports
audit_logs
```

### Completed KB modules

- **KB-001 to KB-007:** Proxmox host preparation, Ubuntu VM creation, Docker installation, PostgreSQL and Redis foundation, MSSP schema creation, demo tenant/appliance/alert/incident data, final foundation validation.
- **KB-008:** FastAPI backend foundation, PostgreSQL connectivity, Redis connectivity, `/health` endpoint, read-only admin/customer preview endpoints, validation script passed.
- **KB-009A:** AI development rules and prompt framework — documentation only, no runtime changes.
- **KB-010 (Phase 1):** Authentication/Login + Role-Based Access Control foundation. Added `platform_users.password_hash`, renamed the top role from `super_admin` to `platform_admin`, added `POST /auth/login`, `GET /auth/me`, `GET /auth/roles`, JWT access tokens, and reusable `require_roles`/`require_tenant_match` RBAC/tenant-isolation dependencies. The existing `/admin/*` and `/customer/*` preview endpoints were intentionally left unauthenticated in this phase — KB-008 validation still passed unchanged at the time. Validated, committed (`7fbb3d2`), and tagged `kb010-auth-rbac-phase1-validated`.
- **KB-011:** Protected the existing `/admin/*` and `/customer/*` preview endpoints using the KB-010 auth foundation (`require_roles`, `get_current_user`, `require_tenant_match` — no changes were needed to those dependencies themselves). `platform_admin`/`soc_manager`/`soc_analyst` can access all `/admin/*` endpoints and read any tenant's `/customer/*` data for support/troubleshooting; `customer_admin`/`customer_viewer` can only reach their own tenant's `/customer/*` data (404, not 403, on a tenant mismatch, to avoid confirming another tenant's existence). Added a permanent second demo tenant (`DEMO2`) and demo accounts for the 3 previously-missing roles (`platform_admin`, `soc_analyst`, `customer_admin`). Validated by `scripts/kb011_validate_protected_apis.sh` — result: `KB-011 PROTECTED APIS VALIDATION PASSED`. See `docs/KB011_PROTECTED_APIS_COMPLETION.md` for the full completion summary. **Not yet committed.**

### Next module

- **KB-012 (or next real feature module):** to be defined once KB-011 is committed.

---

## 4. Strict AI-Agent Rules

Every AI agent (Cursor, Claude, ChatGPT-assisted edits, or any future agent) working in this repository must follow these rules on every task, not just this one:

1. **Inspect before acting.** Look at the current project tree and read the relevant existing files before proposing or making changes.
2. **Confirm state before acting.** Confirm the current Git branch and `git status` before making changes.
3. **Explain before acting.** Give a short, plain-language plan of what will change and why, before editing files.
4. **List the exact files** that will be created or edited before doing it.
5. **Make only the requested changes.** Do not "improve" unrelated code, rename things, reformat whole files, or refactor without being asked.
6. **Show `git status --short`** after making changes so the user can see exactly what changed.
7. **Provide validation commands** for every change — something the user can run to confirm the change worked.
8. **Never commit automatically.** Only the human user decides when to commit. Never run `git add .`. Never run `git commit` unless explicitly instructed in that specific message.
9. **Never restart or modify running Docker containers** unless explicitly instructed.
10. **Never make large architectural changes** (e.g. swapping frameworks, changing the database engine, changing how tenants are isolated) without first explaining the change in plain language and getting explicit approval.
11. **Stop and ask** if a request is ambiguous, conflicts with this file, or would require touching a "do-not-touch" file (see below) — do not guess.

### Do-not-touch without explicit instruction

- `backend-api/app/main.py` (unless the current task explicitly says to edit it)
- `docker-compose.yml` (unless the current task explicitly says to edit it)
- `postgres/init/001_mssp_core_schema.sql` (schema must not be deleted/recreated/replaced without explicit instruction)
- `.env` (never read its values back to the user, never edit blindly, never commit)
- Any running container (no restarts unless explicitly instructed)

Note: KB-010 was granted a specific, explicit one-time exception to add a single `JWT_SECRET` line to `docker-compose.yml` and a 2-line router-registration edit to `main.py`. KB-011 was separately granted an explicit one-time exception to add `Depends()` authentication/RBAC checks to the 7 existing `/admin/*` and `/customer/*` endpoints in `main.py` — no `docker-compose.yml` change was needed for KB-011. Neither exception creates a standing exception — future edits to these files still require explicit instruction in that task.

---

## 5. Security Rules

This is a multi-tenant MSSP platform handling other companies' security data. Security is mandatory, not optional.

- Never commit `.env`.
- Never print `.env` values in chat, logs, or generated files.
- Never expose secrets (API keys, tokens, passwords) in code, comments, commit messages, or documentation.
- Never hardcode passwords, API keys, JWT secrets, Wazuh credentials, or customer tokens anywhere in source code.
- Never expose customer data across tenants.
- Every customer-facing API must enforce tenant isolation.
- Customer A must never be able to see Customer B's data, under any circumstance, including via IDs guessed in a URL.
- SOC/platform roles may see cross-tenant data only when their role explicitly allows it (role-based, not "trust the frontend").
- Never return password hashes (or any credential material) in API responses.
- Use secure password hashing (e.g. bcrypt/argon2 — never plain MD5/SHA1, never plaintext).
- Use JWT or an equivalent secure token approach for authentication.
- Use role-based access control (RBAC) — every protected endpoint must check the caller's role and tenant.
- Handle Wazuh/API timeouts safely (timeouts, retries with backoff where sensible, never hang indefinitely).
- Handle malformed security alerts safely (validate/normalize input, never let a bad alert crash the ingestion path).
- Do not expose stack traces or internal error detail to customers.
- Log useful errors for admin/SOC troubleshooting (server-side logs may be detailed; customer-facing responses must not be).
- Prefer safe failure behavior over silent failure — if something fails, it should fail loudly in logs/monitoring, not disappear silently.

---

## 6. Tenant Isolation Rules

- Every table that holds customer data has a `tenant_id` column tying it to `tenants.id`. Every query touching that data must filter by `tenant_id`.
- Customer-facing endpoints must derive `tenant_id` from the authenticated user's session/token — never from a client-supplied parameter that isn't cross-checked against the caller's own tenant.
- SOC/admin endpoints that intentionally span tenants must be clearly separated (e.g. under `/admin/...`) and must require an admin/SOC role, not a customer role.
- Any new table that stores tenant-specific data must include a `tenant_id UUID NOT NULL REFERENCES tenants(id)` column and a supporting index, following the existing schema pattern in `postgres/init/001_mssp_core_schema.sql`.
- Any new query or endpoint must be reviewed against the question: "Could this let Tenant A see or affect Tenant B's data?" If the answer is "maybe", it must not ship as-is.

---

## 7. Backend Coding Standards

Future backend code must be modular. Do not keep adding everything into one huge `main.py`.

Preferred structure going forward:

```
backend-api/app/main.py            # app wiring only — routers, startup, middleware
backend-api/app/core/config.py     # settings/env loading
backend-api/app/core/security.py   # password hashing, JWT creation/verification, RBAC helpers
backend-api/app/db/session.py      # database connection/session management
backend-api/app/api/routes/        # one router module per feature area (e.g. auth.py, tenants.py, alerts.py)
backend-api/app/schemas/           # Pydantic request/response models
backend-api/app/services/          # business logic, called by routes, testable independently
```

Additional standards:

- New modules should follow this structure starting with KB-010 (Auth/RBAC). Existing code in `main.py` may be incrementally migrated into this structure as part of future KB modules — this is not required to happen in one large rewrite.
- All new dependencies must be added to `backend-api/requirements.txt` with pinned versions (matching the existing style, e.g. `fastapi==0.115.6`).
- All database access should continue to use parameterized queries (no string-formatted SQL) to prevent SQL injection, consistent with the current `main.py` pattern.
- All new endpoints must have explicit success and error response shapes — no bare `except Exception: pass`.
- Config values (hosts, ports, secrets, feature flags) come from environment variables, never hardcoded, consistent with the current `_env()` helper pattern in `main.py`.

---

## 8. Frontend Direction

- No frontend exists yet. It is planned as two separate frontends: an **admin/SOC dashboard** and a **customer dashboard**, both consuming the FastAPI backend over HTTP APIs.
- Streamlit may be used later purely for internal prototypes or SOC demo screens — never as the production customer-facing product.
- The eventual production frontend technology choice has not been made yet and must be explicitly discussed and approved before implementation begins — this counts as a "large architectural change."
- Until a frontend module is explicitly started, AI agents should not scaffold frontend frameworks, add frontend dependencies, or create frontend directories.

---

## 9. Wazuh & Security Engine Adapter Direction

Wazuh integration is planned as a **backend adapter/source**, not a UI.

- Do not assume Wazuh URL, username, password, API token, or exact customer values unless explicitly provided by the user.
- Wazuh integration should eventually support:
  - Safe API connection
  - Timeout handling
  - Authentication failure handling
  - Alert normalization
  - Duplicate alert protection
  - Mapping Wazuh alerts to the `security_alerts` table
  - Optional incident creation workflow
  - Tenant association (every ingested alert must be tied to the correct `tenant_id`)
  - Customer-safe summary generation (plain-English, no raw technical noise, no data leakage between tenants)
- Suricata and other tools (MISP, TheHive/Cortex, Shuffle/n8n, Prometheus/Grafana) are expected to follow the same adapter pattern once implemented.
- None of this is implemented yet as of KB-009A. It is documented here so future modules build toward the same design.

---

## 10. Validation Commands to Preserve

These commands must continue to work after any change. If a change breaks one of these, the change is not complete.

```bash
cd /opt/mssp-control
git branch --show-current
git status --short
docker compose ps
curl -fsS http://localhost:8000/health | jq .
./scripts/kb008_validate_backend_api_foundation.sh
./scripts/kb010_validate_auth_rbac.sh
./scripts/kb011_validate_protected_apis.sh
```

**Important — KB-011 changed the meaning of the above list.** As of KB-011, `/admin/*` and `/customer/*` require a valid token, so `scripts/kb008_validate_backend_api_foundation.sh` (which calls those endpoints with no token and expects `200`) and `scripts/kb010_validate_auth_rbac.sh` (which internally re-runs the KB-008 script) are expected to **fail** on those specific checks if run after KB-011 ships. This is intentional and correct, not a defect. Both scripts are kept unmodified as historical records of pre-KB-011 behavior. `scripts/kb011_validate_protected_apis.sh` is the current must-pass gate for those 7 endpoints going forward.

Any AI agent making backend changes should re-run (or ask the user to re-run) the currently-relevant commands and report the result before considering a task complete.

---

## 11. Git Rules

- Do not use `git add .`. Stage only the specific files that were intentionally created or edited for the current task.
- Do not commit automatically. Only commit when the user explicitly asks for a commit in that message.
- Do not push, rebase, force-push, or rewrite history unless explicitly instructed.
- Do not create or switch branches unless explicitly instructed.
- Always show `git status --short` after making file changes so the user can see the diff surface before deciding whether to commit.
- Never commit `.env` or any file containing real secrets.

---

## 12. Documentation Rules

- Every KB module should have a clear, plain-language record of what was done, in `docs/` where appropriate (see `docs/KB009_AI_DEVELOPMENT_WORKFLOW.md` for the KB-009A workflow doc).
- Documentation must never contain real secrets, real customer data, or real credentials — use placeholders like `<REDACTED>` or generic example values only.
- When a new KB module changes the architecture, database schema, or security rules, this `AGENTS.md` file must be updated in the same change set so it never goes stale.
- `docs/AI_PROMPT_LEDGER.md` should be updated whenever a significant AI-assisted change is made, recording what was asked, what changed, and the validation result (see that file for the exact format).

---

## 13. Non-Coder User Requirements (how AI agents must communicate)

The user of this repository is not a programmer. Every AI agent must:

- Explain changes in simple, non-jargon language.
- Always say which file is being edited.
- Always give the full path of the file (e.g. `/opt/mssp-control/backend-api/app/main.py`, not just `main.py`).
- Provide complete file content or complete edits — never partial snippets that require the user to "fill in the rest."
- Provide exact commands to run, copy-pasteable, with the working directory stated.
- Provide the expected output of those commands so the user can tell success from failure.
- Never give pseudo-code for production modules.
- Never say "add the rest yourself."
- Never leave incomplete code blocks.
- Never hide failed commands — if something fails, show the failure and explain it.
- Never make large architectural changes without explaining them first in plain language and getting explicit approval.

---

This file is intended to be read by every AI agent at the start of every session in this repository, alongside `CLAUDE.md` and `.cursor/rules/mssp-control-plane.mdc`.
