# CONTEXT.md — MSSP Control Plane Current Snapshot

Status: Living context file for AI agents and humans. Recreated/refreshed in **KB-032** (AI Context and Documentation Sync).  
Project path: `/opt/mssp-control`  
VM: `mssp-control`

**How to use this file:** Read it at the start of every session together with `AGENTS.md` and `CLAUDE.md`. It summarizes *where the lab is now*. It is not a substitute for inspecting live source or git.

**Source of truth hierarchy (highest wins):**

1. Live git commits / tags / `git status`
2. Validation-script PASS/FAIL output
3. Inspected source files (`customer.py`, `frontend-customer`, schema, etc.)
4. This `CONTEXT.md` / `AGENTS.md` / ledger (must be updated when they drift)

If documentation disagrees with git, **trust git** and fix the docs (that is what KB-032 exists for).

---

## 1. Latest validated feature baseline

| Item | Value |
|---|---|
| Latest validated feature KB | **KB-031 — Customer Report Detail UI** |
| Commit | **`d27bdea`** |
| Tag | **`kb031-customer-report-detail-validated`** |
| Docs-sync KB in progress | **KB-032** on branch `kb032-ai-context-doc-sync` (documentation only) |

Recent customer-portal tags (newest first):

- `kb031-customer-report-detail-validated` → `d27bdea`
- `kb030-customer-asset-detail-validated` → `f85a72b`
- `kb029-customer-alert-detail-validated` → `3633a03`
- `kb028-customer-dashboard-v2-validated` → `5823909`
- `kb027-customer-recommendation-detail-validated` → `1dccfb7`
- `kb026-customer-recommendations-validated` → `4ad25b0`
- `kb025-incident-detail-validated` → `d4eeb7e`
- `kb024-customer-reports-validated` → `377c0a6`
- `kb023-customer-assets-validated` → `1aab85a`
- `kb022-customer-alerts-validated` → `b34f818`
- `kb021-customer-frontend-validated` → `b0798b2`

Older foundation tags still matter (examples): `kb020-production-bootstrap-demo-separation-validated`, `kb018-admin-frontend-foundation-validated`, `kb017-…`, `kb011-protected-apis-validated`, `kb010-auth-rbac-phase1-validated`, `kb008-validated-foundation`.

---

## 2. Running services

Typical Docker Compose services on this VM:

| Container | Role |
|---|---|
| `mssp-postgres` | PostgreSQL |
| `mssp-redis` | Redis |
| `mssp-backend-api` | FastAPI API on port **8000** |
| `mssp-frontend-admin` | Admin/SOC UI on port **3000** |
| `mssp-frontend-customer` | Customer portal on port **3001** |

Health check:

```bash
curl -fsS http://localhost:8000/health | jq .
```

Expect `api`, `database`, and `redis` all `"ok"`.

---

## 3. Customer portal — what works today (through KB-031)

Location: `frontend-customer/` (browser: `http://localhost:3001`).

### Shell / auth (KB-021)

- Login, JWT session, branded layout, account page.
- Demo customer example: `customer.viewer@demo.local` (password never stored in docs; use env or interactive prompt in scripts).

### Dashboard v2 (KB-028)

- Composes incidents, alerts, recommendations, assets, and reports via customer APIs (`getCustomerDashboardV2` / `Promise.all`).
- KPI cards, recent lists, latest report card, appliance health snippet.
- Links into detail pages where they exist (incidents, recommendations, alerts, reports).

### Lists + detail pages

| Domain | List | Detail | Notes |
|---|---|---|---|
| Alerts | KB-022 | KB-029 `/alerts/:alertId` | `customer_visible = true` only |
| Incidents | earlier customer incidents API | KB-025 `/incidents/:incidentNumber` | Customer-visible timeline + related visible alerts; no comments |
| Assets | KB-023 appliances + protected assets | KB-030 `/assets/:assetId` | **Protected asset** detail only; appliance rows are **not** detail-linked |
| Reports | KB-024 | KB-031 `/reports/:reportId` | **Customer report detail**; published/archived only; drafts → 404 |
| Recommendations | KB-026 | KB-027 `/recommendations/:recommendationId` | `customer_visible = true` |

### Customer backend surface (`backend-api/app/api/routes/customer.py`)

Representative routes (all under `/customer`, auth + tenant match):

- `GET /customer/dashboard/{short_code}` (legacy composition still present; Dashboard v2 prefers composed list APIs)
- `GET /customer/incidents/{short_code}` and `.../{incident_number}`
- `GET /customer/alerts/{short_code}` and `.../{alert_id}`
- `GET /customer/assets/{short_code}` and `.../{asset_id}`
- `GET /customer/reports/{short_code}` and `.../{report_id}`
- `GET /customer/recommendations/{short_code}` and `.../{recommendation_id}`

Frontend helpers live in `frontend-customer/src/api/customer.ts`. Routes wired in `frontend-customer/src/App.tsx`.

### Explicit non-goals already deferred

- Customer **appliance detail** page (deferred from KB-030)
- PDF / `report_file_path` download and raw **metrics** charts (deferred from KB-031)
- Customer write workflows (acknowledge/close alerts, edit assets, accept recommendations, etc.)
- Customer **notifications** history UI
- Calling `/admin` from the customer portal — **forbidden forever**

---

## 4. Admin / platform (brief)

Admin UI exists (`frontend-admin/`). Backend includes auth/RBAC (KB-010/011), modular routes (KB-012+), tenant/user/appliance admin APIs, appliance registration/heartbeat, credential rotation, and related validation scripts. Customer modules must not casually edit admin frontend or admin-only APIs unless the KB is explicitly an admin module.

---

## 5. Safety rules that must not be broken

### Secrets and config

- **No `.env`** edits, prints, or commits.
- **No `docker-compose.yml`** changes unless the task explicitly approves them.
- **No `postgres/init/`** schema/migration edits unless explicitly approved.
- Never hardcode passwords, API keys, JWT secrets, tokens, or Wazuh credentials in source or docs.

### Tenant isolation

- Customer APIs: `get_current_user` → resolve tenant by `short_code` → `require_tenant_match`.
- Wrong tenant / missing / draft / non-visible → **HTTP 404**, not 403.
- Always filter by `tenant_id` on tenant-owned tables.

### Customer data hygiene

Do not expose forbidden fields to customers, including (non-exhaustive):

- `password`, `password_hash`
- `token`, `token_hash`, `api_key`, appliance API key hash/hint, activation token material
- `raw_event`, `raw_json`, `details`, `metrics`, `health_snapshot`, `report_file_path`
- IP fields (`ip_address`, `source_ip`, `destination_ip`, `local_ip`, `last_source_ip`)
- `internal_notes`, `admin_notes`, stack traces, backend internals
- Unapproved technical AI / MITRE internals

Safe list/detail field sets are documented per KB (KB-022…KB-031). Prefer those approved shapes.

### Frontend boundary

- `frontend-customer` must contain **no `/admin`** API usage.
- Prefer `/customer/*` only for customer data.

### Git / delivery

- Planning before implementation.
- Inspect current files before planning.
- Do not implement before planning is reviewed (unless implement scope already approved).
- **Validation before commit.**
- Do not stage/commit/tag unless the user asks.
- Preferred delivery cadence after PASS: validation → commit → tag → Proxmox snapshot (each step user-driven).

---

## 6. Safe KB workflow (checklist)

1. `git branch --show-current` and `git status --short` (expect clean unless you are mid-module).
2. Read `CONTEXT.md`, `AGENTS.md`, ledger, and the prior KB doc for the area.
3. Inspect the real files you will touch (routes, pages, schema columns).
4. Produce a **planning-only** proposal; stop for approval.
5. Implement only the approved file list.
6. Run `./scripts/kb0NN_validate_....sh` until the exact PASS line prints.
7. Show `git status --short`; wait.
8. Only if asked: commit specific files → tag → snapshot.

KB-032 validation success line:

```text
KB-032 AI CONTEXT DOC SYNC VALIDATION PASSED
```

KB-031 feature validation success line (regression reference):

```text
KB-031 CUSTOMER REPORT DETAIL UI VALIDATION PASSED
```

---

## 7. Next recommended feature KBs (after KB-032)

These are **candidates**, not started modules. The user must kick one off explicitly:

1. **Customer notifications history** — product checklist still calls for notification history; table `notification_events` exists.
2. **Customer appliance detail** — deferred from KB-030; assets page still shows appliances as plain text rows.
3. **Account / profile hardening** — strengthen customer account page / session UX without leaking secrets.

Do not start KB-033+ feature work until KB-032 docs sync is validated (and preferably committed/tagged) and a new planning prompt is approved.

---

## 8. Key paths cheat sheet

| Path | Why it matters |
|---|---|
| `AGENTS.md` | Full agent rulebook |
| `CLAUDE.md` | Short operating instructions |
| `.cursor/rules/mssp-control-plane.mdc` | Always-applied Cursor rules |
| `CONTEXT.md` | This snapshot |
| `docs/AI_PROMPT_LEDGER.md` | AI change ledger |
| `docs/KB021_…` … `docs/KB031_…` | Customer portal module docs |
| `docs/KB032_AI_CONTEXT_DOC_SYNC.md` | This docs-sync module record |
| `backend-api/app/api/routes/customer.py` | Customer API routes |
| `frontend-customer/src/api/customer.ts` | Customer API client |
| `frontend-customer/src/App.tsx` | Customer routes |
| `scripts/kb031_validate_customer_report_detail_ui.sh` | Latest feature gate example |
| `scripts/kb032_validate_ai_context_doc_sync.sh` | Docs-sync gate |

---

## 9. What KB-032 changes (and what it must not)

**Changes:** documentation/context files only — `AGENTS.md`, `CLAUDE.md`, `.cursor/rules/mssp-control-plane.mdc`, `CONTEXT.md`, `docs/AI_PROMPT_LEDGER.md`, `docs/KB032_AI_CONTEXT_DOC_SYNC.md`, `scripts/kb032_validate_ai_context_doc_sync.sh`.

**Must not change:** backend runtime code, frontend runtime code, database schema, `docker-compose.yml`, `.env`.

---

## 10. Quick commands

```bash
cd /opt/mssp-control
git branch --show-current
git status --short
git log --oneline --decorate -12
git tag --sort=-creatordate | head -15
curl -fsS http://localhost:8000/health | jq .
./scripts/kb032_validate_ai_context_doc_sync.sh
```

Remember: **no .env**, **no /admin** from customer UI, **planning before implementation**, **validation before commit**. Latest feature pointer remains KB-031 customer report detail (`d27bdea`, `kb031-customer-report-detail-validated`).
