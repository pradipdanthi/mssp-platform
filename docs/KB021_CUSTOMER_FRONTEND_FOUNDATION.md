# KB-021 — Customer Frontend Foundation

**Status:** Implemented (ready for validation)  
**Branch:** `kb021-customer-frontend-foundation`

## Purpose and scope

Deliver a separate, branded **customer portal** for Kestrel Cyber Control Plane by Keroxsys (legal entity: Cicilia Consultancy). This is a **foundation** only: read-only pages, existing customer APIs, Docker/Vite runtime — not a full production UI.

## Customer portal vs admin portal

| Portal | Path | Host port | Audience |
|---|---|---|---|
| Admin | `frontend-admin/` | **3000** | SOC / platform operators |
| Customer | `frontend-customer/` | **3001** | `customer_admin` / `customer_viewer` |

Customers never use Wazuh or admin tools. The customer app **must not** call `/admin` APIs.

URLs:

- `http://localhost:3001`
- `http://192.168.0.201:3001`

## Routes / pages

| Route | Behavior |
|---|---|
| `/login` | Customer-focused sign-in |
| `/dashboard` | `GET /customer/dashboard/{tenant_short_code}` |
| `/incidents` | `GET /customer/incidents/{tenant_short_code}` |
| `/assets` | Appliance health from dashboard payload |
| `/reports` | Monthly reports from dashboard payload |
| `/alerts` | Foundation message (no dedicated customer alerts API yet; no admin calls) |
| `/account` | Read-only user + tenant fields from `/auth/me` |
| `/` | Redirect to `/dashboard` or `/login` |

Entire KB-021 UI is **read-only**.

## Backend APIs used

- `POST /auth/login`
- `GET /auth/me`
- `GET /customer/dashboard/{short_code}`
- `GET /customer/incidents/{short_code}`

JWT is stored only in **sessionStorage** (never localStorage).

## `/auth/me` gap-fill (KB-021)

Backend now returns optional:

- `tenant_short_code`
- `tenant_name`

(null for users without a tenant, e.g. platform/SOC accounts).

**Files touched:**

- `backend-api/app/schemas/auth.py` — `UserPublic` fields
- `backend-api/app/services/auth_service.py` — `LEFT JOIN tenants` in user lookups + `to_public_user()`

No login/RBAC weakening; no password hashes or secrets exposed.

**Ops note:** rebuild/restart `backend-api` so the running container picks up these changes before customer login can receive `tenant_short_code`.

## Security / RBAC / tenant isolation

- Customer frontend only uses auth + `/customer/*` helpers.
- Path `short_code` comes from `/auth/me` (`tenant_short_code`), not from free-typed admin IDs.
- Backend continues to enforce `require_tenant_match` (404 on mismatch for customer roles).
- No activation tokens, appliance API keys, credential rotation, tenant/user management, or admin pages.

## Intentionally deferred

- Dedicated customer alerts / assets / reports list APIs
- Write actions, notifications, WhatsApp, customer recommendations workflows
- Production nginx static build / reverse proxy / HTTPS
- Shared UI package between admin and customer apps

## Validation

```bash
cd /opt/mssp-control
chmod +x scripts/kb021_validate_customer_frontend_foundation.sh
# Ensure backend-api is rebuilt if auth_service/schema changed:
# docker compose build backend-api && docker compose up -d backend-api
./scripts/kb021_validate_customer_frontend_foundation.sh
```

Expected final line:

```text
KB-021 CUSTOMER FRONTEND FOUNDATION VALIDATION PASSED
```

## Manual browser checklist

1. Open `http://192.168.0.201:3001` (or localhost:3001).
2. Confirm customer branding / logo (Customer Portal title).
3. Sign in as `customer.viewer@demo.local` (interactive password; not stored in this doc).
4. Dashboard shows DEMO tenant-scoped summary.
5. Incidents / Assets / Reports load from customer APIs/dashboard data.
6. Alerts page shows foundation message (no admin API).
7. Account shows user + tenant_short_code.
8. Confirm admin portal on port **3000** still works separately.
9. Logout clears session.
