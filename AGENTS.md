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
- A platform that uses an **enterprise open-source SOC stack** (Wazuh, Suricata, Zeek, TheHive, Shuffle, MISP, Greenbone, Velociraptor, etc. — see KB-036 roadmap) as **backend adapters and data sources**, never as the customer-facing UI.

### Product goal

Deliver a full MSSP platform where:
- Our own backend (FastAPI) is the system of record and the only thing customers and SOC staff interact with directly.
- Detection tools like Wazuh feed alerts into our backend through adapters (future KB modules — **not deployed yet**).
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
- **Admin / SOC dashboard frontend** — `frontend-admin/` (port 3000; KB-018+)
- **Customer dashboard frontend** — `frontend-customer/` (port 3001; KB-021–KB-035)
- **Wazuh and other open-source tools** — backend detection engines/adapters only

### Hard architecture rules

- Do **not** convert the main product into Streamlit. Streamlit may only be used later for quick internal prototypes or SOC demo screens — it is never the customer-facing production platform.
- Wazuh is a detection engine/adapter source, not the customer-facing product UI. Customers must never be given direct Wazuh logins. SOC/admin users work through our own platform dashboard; Wazuh data is normalized into our backend database.
- **KB-036 approved enterprise SOC stack (roadmap):** Wazuh (Manager, Indexer/OpenSearch, Dashboard, Agents), Suricata, Zeek, TheHive (+ Cortex if needed), Shuffle, MISP, Greenbone/OpenVAS, Velociraptor (+ optional osquery), Ansible/Compose deployment automation, Prometheus/Grafana observability. OpenCTI and Kubernetes are **future optional** — not immediate scope. Tools are **not deployed yet** until their KB modules run.
- All tools follow the same adapter pattern: external engine → normalize → PostgreSQL → admin API vs customer-safe API.
- Any AI agent proposing to change this architecture (e.g. "let's just use Streamlit for everything" or "let's expose Wazuh directly to customers") must stop and explain the proposed change in plain language and get explicit user approval before making it. This counts as a "large architectural change" under section 8.

---

## 3. Current Validated Baseline

**Source of truth:** Git commits, tags, and validation-script output beat stale prose in this file, `CLAUDE.md`, the Cursor rule, or the prompt ledger. Always `git log` / `git tag` / `git status` and inspect live files before planning.

- **VM name:** mssp-control (VM 100, `192.168.0.201`)
- **Project path:** `/opt/mssp-control`
- **Latest validated feature KB:** **KB-035** (Customer Appliance Detail UI)
- **Latest validated feature commit:** `1ac1df3`
- **Latest validated feature tag:** `kb035-customer-appliance-detail-validated`
- **Architecture roadmap doc:** `docs/KB036_MSSP_PLATFORM_ARCHITECTURE_ROADMAP.md` (KB-036 — enterprise MSSP/SOC/MDR/XDR roadmap, documentation only)
- **Known-good early baseline tag:** `kb008-validated-foundation` (commit `c52bca1`)
- **AI development rules tag:** `kb009a-ai-development-rules`
- **KB-010 Phase 1 validated tag:** `kb010-auth-rbac-phase1-validated` (commit `7fbb3d2`)
- **KB-011 validated tag:** `kb011-protected-apis-validated` (commit `30ef305`)
- **Critical limitation:** Enterprise SOC stack (Wazuh, Suricata, Zeek, TheHive, Shuffle, MISP, Greenbone, Velociraptor, etc.) **not deployed yet** — no live ingestion adapters

### Current services (Docker Compose)

| Container | Purpose |
|---|---|
| `mssp-postgres` | PostgreSQL database |
| `mssp-redis` | Redis cache/queue |
| `mssp-backend-api` | FastAPI backend (port 8000) |
| `mssp-frontend-admin` | Admin/SOC UI (port 3000) |
| `mssp-frontend-customer` | Customer portal UI (port 3001) |

### Current backend

- FastAPI backend lives in `backend-api/`.
- `backend-api/app/main.py` is app wiring only (KB-012+): metadata, `FastAPI` object, router includes.
- Route logic lives under `backend-api/app/api/routes/` (auth, health, admin, customer, plus later admin/appliance modules).
- `/health` reports API, database, and Redis status.
- Customer tenant isolation: `get_current_user` + resolve tenant by `short_code` + `require_tenant_match` → **404** (not 403) on mismatch.
- Customer APIs (non-exhaustive; see `customer.py` and OpenAPI): dashboard, incidents (+ detail), alerts (+ detail), assets (+ protected-asset detail), appliances (+ detail), reports (+ detail), recommendations (+ detail), notifications.

### Current customer portal (`frontend-customer/`, port 3001)

Working through KB-035 (list + detail where noted):

| Area | Routes / behavior |
|---|---|
| Auth / shell | Login, branded layout, account page (KB-021) |
| Dashboard v2 | KPIs + recent lists + latest report (KB-028) |
| Alerts | List (KB-022) + detail `/alerts/:alertId` (KB-029) |
| Incidents | List + detail `/incidents/:incidentNumber` (KB-025) |
| Assets | Appliances + protected assets list (KB-023) + protected-asset detail `/assets/:assetId` (KB-030) + appliance detail `/appliances/:applianceId` (KB-035) |
| Reports | List (KB-024) + detail `/reports/:reportId` (KB-031); published/archived only; no PDF/metrics |
| Recommendations | List (KB-026) + detail `/recommendations/:recommendationId` (KB-027) |
| Notifications | History list (KB-033) |
| Account | Profile + change password (KB-034) |

**Hard rule:** `frontend-customer` must **never** call `/admin` APIs.

### Current database

- Schema file: `postgres/init/001_mssp_core_schema.sql` (+ later additive migrations such as KB-010/KB-016 under `postgres/init/`).
- **Do not delete, recreate, or replace the schema** unless explicitly instructed.
- Core tables include: `tenants`, `platform_users`, `appliances`, `protected_assets`, `security_alerts`, `incidents`, `customer_recommendations`, `monthly_reports`, `notification_events`, `audit_logs`, and related join/timeline tables.

### Completed KB modules (high level)

- **KB-001–KB-009A:** Infra/foundation + AI agent rules docs.
- **KB-010–KB-017:** Auth/RBAC, protected APIs, route modularization, admin tenant/user/appliance APIs, appliance registration/heartbeat, credential visibility/rotation.
- **KB-018–KB-020:** Admin frontend foundation, activation-token UI, production bootstrap / demo separation.
- **KB-021:** Customer frontend foundation.
- **KB-022–KB-024:** Customer alerts / assets / reports list APIs + UI.
- **KB-025–KB-027:** Incident detail; recommendations list + detail.
- **KB-028:** Customer Dashboard v2.
- **KB-029–KB-035:** Alert detail; protected-asset detail; report detail; notifications; account hardening; appliance detail — through `kb035-customer-appliance-detail-validated` (`1ac1df3`).
- **KB-032:** AI context / documentation sync — docs only.
- **KB-036:** Enterprise platform architecture and deployment model roadmap — docs only (cloud/on-prem/hybrid, full capability stack, VM 100–111, KB-037–060).

### Next module (after KB-036 docs sync is validated/committed)

Do **not** install SOC tools, create VMs 101–111, or build integration adapters until the relevant future KB is explicitly planned and approved. See `docs/KB036_MSSP_PLATFORM_ARCHITECTURE_ROADMAP.md` for KB-037 through KB-060 (cluster registry, deployment automation, Wazuh, Suricata/Zeek, TheHive/Shuffle, MISP, Greenbone, Velociraptor, live integration, on-prem appliance, ops runbooks).

Do **not** implement a feature KB until a planning pass is reviewed and approved.

### Safe KB workflow (mandatory)

Remember the short form: **planning before implementation**, **no .env**, customer UI has **no /admin**, and **validation before commit**.

1. Confirm branch + clean tree (`git branch`, `git status`).
2. **Inspect** live files, git tags, and prior KB docs — do not trust memory or stale summaries alone.
3. **Plan only** first; stop for approval before implementing.
4. Implement only approved scope.
5. Run the module **validation script** and fix until it passes.
6. **Then** (only if the user asks): commit → tag → Proxmox snapshot.
7. Never commit before validation. Never invent secrets. Never edit `.env` / `docker-compose.yml` / `postgres/init/` / `frontend-admin/` unless the task explicitly allows it.

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
- `postgres/init/` schema/migration files (must not be deleted/recreated/replaced without explicit instruction)
- `.env` (never read its values back to the user, never edit blindly, never commit)
- `frontend-admin/` (unless the task is explicitly an admin-frontend module)
- Any running container (no restarts unless explicitly instructed)

One-time historical exceptions (KB-010/011/012/`docker-compose` JWT line, etc.) do **not** create standing permission to edit those files.

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
- Customer API responses must omit forbidden fields such as: `password` / `password_hash`, `token` / `token_hash`, `api_key` / appliance key hashes/hints, activation tokens, `raw_event` / `raw_json` / `details` / `metrics` / `health_snapshot` / `report_file_path`, IPs (`source_ip`, `destination_ip`, `local_ip`, `ip_address`, `last_source_ip`), `internal_notes` / `admin_notes`, `mitre_mapping`, technical AI internals not approved for customers, and stack traces.

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

- **Admin frontend** exists at `frontend-admin/` (port 3000).
- **Customer frontend** exists at `frontend-customer/` (port 3001) through KB-035 list/detail coverage above.
- Streamlit may be used later purely for internal prototypes or SOC demo screens — never as the production customer-facing product.
- Customer UI must call only `/api/customer/...` (and auth) paths — **never** `/admin`.
- Do not scaffold unrelated frontend frameworks or rewrite the existing portals without an explicit approved module.

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
./scripts/kb011_validate_protected_apis.sh
./scripts/kb035_validate_customer_appliance_detail_ui.sh
./scripts/kb036_validate_mssp_platform_architecture_roadmap.sh
```

Older scripts (`kb008`, `kb010`, `kb012`, …) remain historical/regression tools. Prefer the newest module script for the area you changed. After KB-011, unauthenticated `/admin`/`/customer` checks in older scripts may fail by design.

**Important:** Git tags and validation-script PASS lines are the source of truth for “what is validated.” If `AGENTS.md` or the ledger disagrees with `git tag` / `git log`, trust git and update the docs (as KB-032 does).

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
