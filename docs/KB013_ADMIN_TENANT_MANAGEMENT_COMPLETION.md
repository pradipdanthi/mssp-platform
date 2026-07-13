# KB-013 Admin Tenant Management API Foundation — Completion Summary

## 1. Module name and purpose

**KB-013: Admin Tenant Management API Foundation.**

Purpose: give `platform_admin`, `soc_manager`, and `soc_analyst` a proper API-based way to view a single tenant's full detail, and give `platform_admin` a way to create new tenant records and update existing ones through the backend API — instead of relying only on SQL seed scripts for tenant lifecycle changes. This is a foundation module: it adds new endpoints alongside the existing tenant list endpoint, with no schema, infrastructure, or auth-model changes.

## 2. Starting point

- Previous validated commit: `d2b1663`
- Previous tag: `kb012-route-modularization-validated`
- Branch worked on: `kb013-admin-tenant-management`

## 3. Scope of KB-013

- Added three new endpoints under `/admin/tenants/*`:
  - `GET /admin/tenants/{tenant_id}` — single tenant detail (with appliance/protected-asset/incident counts).
  - `POST /admin/tenants` — create a new tenant.
  - `PATCH /admin/tenants/{tenant_id}` — update one or more fields on an existing tenant (partial update).
- Added Pydantic request/response models for these endpoints (`backend-api/app/schemas/tenants.py`).
- Added one minimal database helper, `fetch_one_write()`, to `backend-api/app/db/session.py` for `INSERT`/`UPDATE ... RETURNING ...` statements.
- Wired the new router into `backend-api/app/main.py` with exactly one import line and one `app.include_router(...)` line.
- Added `scripts/kb013_validate_admin_tenant_management.sh`, which validates the new endpoints end-to-end and then reruns `scripts/kb012_validate_route_modularization.sh` unmodified as a full regression gate (which in turn reruns `scripts/kb011_validate_protected_apis.sh` unmodified).

## 4. What was intentionally not included

- **No frontend.** No admin or customer dashboard UI work was done or scaffolded.
- **No database schema change.** The existing `tenants` table (from `postgres/init/001_mssp_core_schema.sql`) already had every field KB-013 needed (`name`, `short_code`, `status`, `sla_level`, `business_criticality`, `timezone`, `notes`), including CHECK constraints whose allowed values are mirrored exactly by the new Pydantic enums.
- **No `docker-compose.yml` change.** No new services, environment variables, or container config were added.
- **No `DELETE /admin/tenants/{tenant_id}` endpoint.** See section 12 for why.
- **No `.env` changes.** No new secrets, tokens, or environment variables were introduced, and `.env` was never read or printed during this module.

## 5. Files created

- `backend-api/app/schemas/tenants.py` — `TenantCreateRequest`, `TenantUpdateRequest`, `TenantDetail` Pydantic models.
- `backend-api/app/api/routes/tenant_management.py` — the new `/admin/tenants/*` router (`GET /{tenant_id}`, `POST ""`, `PATCH /{tenant_id}`).
- `scripts/kb013_validate_admin_tenant_management.sh` — KB-013 validation script.
- `docs/KB013_ADMIN_TENANT_MANAGEMENT_COMPLETION.md` — this file.

## 6. Files modified

- `backend-api/app/main.py` — one new import (`from app.api.routes.tenant_management import router as tenant_management_router`) and one new line (`app.include_router(tenant_management_router)`). No other line was touched; the existing 4 `include_router` calls from KB-012 are unchanged.
- `backend-api/app/db/session.py` — one new helper function, `fetch_one_write()`, appended below the existing `execute()` function. `db_conn()`, `fetch_all()`, `fetch_one()`, `execute()`, and `redis_client()` are all unchanged.
- `docs/AI_PROMPT_LEDGER.md` — new KB-013 row added (see section 17/ledger update below).

## 7. Protected files that were intentionally not touched

- `backend-api/app/api/routes/admin.py` — the existing `GET /admin/tenants` list endpoint and all other `/admin/*` endpoints are untouched, byte-for-byte.
- `backend-api/app/api/routes/customer.py`
- `backend-api/app/api/routes/auth.py`
- `backend-api/app/api/dependencies.py` — `get_current_user`, `require_roles`, `require_tenant_match` are reused as-is, not modified.
- `backend-api/app/api/routes/health.py`
- `docker-compose.yml`
- `.env`
- `postgres/init/001_mssp_core_schema.sql`
- `postgres/init/002_kb010_auth_rbac.sql`
- `scripts/kb008_validate_backend_api_foundation.sh`, `scripts/kb010_validate_auth_rbac.sh`, `scripts/kb011_validate_protected_apis.sh`, `scripts/kb011_seed_rbac_fixtures.sh`, `scripts/kb012_validate_route_modularization.sh`
- `backend-api/requirements.txt` — no new dependencies were needed; `psycopg` (already a dependency) provides the `UniqueViolation` error class used for the duplicate `short_code` backstop.

## 8. API endpoints added

- `GET /admin/tenants/{tenant_id}` — returns one tenant's full detail (including `appliances`, `protected_assets`, `incidents` counts). Requires `platform_admin`, `soc_manager`, or `soc_analyst`.
- `POST /admin/tenants` — creates a new tenant. Requires `platform_admin`. Returns `201` with the created tenant's detail.
- `PATCH /admin/tenants/{tenant_id}` — updates one or more fields on an existing tenant (partial update; `short_code` cannot be changed). Requires `platform_admin`. Returns `200` with the updated tenant's detail.

## 9. Existing endpoint preserved

- `GET /admin/tenants` (the tenant list endpoint in `backend-api/app/api/routes/admin.py`) is completely unchanged — same file, same code, same response shape, same role requirement (`ADMIN_SOC_ROLES`: `platform_admin`, `soc_manager`, `soc_analyst`). KB-013 only imports the existing `ADMIN_SOC_ROLES` constant from `admin.py` for reuse on the new `GET /admin/tenants/{tenant_id}` endpoint — it does not modify `admin.py` in any way.

## 10. RBAC behavior

| Role | `GET /admin/tenants/{id}` | `POST /admin/tenants` | `PATCH /admin/tenants/{id}` |
|---|---|---|---|
| `platform_admin` | Allowed | Allowed | Allowed |
| `soc_manager` | Allowed (read-only) | Denied — 403 | Denied — 403 |
| `soc_analyst` | Allowed (read-only) | Denied — 403 | Denied — 403 |
| `customer_admin` | Denied — 403 | Denied — 403 | Denied — 403 |
| `customer_viewer` | Denied — 403 | Denied — 403 | Denied — 403 |
| No token / garbage token | Denied — 401 | Denied — 401 | Denied — 401 |

This matches approved Decision 1A: only `platform_admin` can create or update tenants; `soc_manager` and `soc_analyst` are read-only for tenant management, same read tier as the existing tenant list.

## 11. Tenant data validation

- **UUID `tenant_id` path parameter.** `tenant_id` is typed as `UUID` on both `GET /admin/tenants/{tenant_id}` and `PATCH /admin/tenants/{tenant_id}`. FastAPI/Pydantic reject a malformed ID (e.g. `not-a-uuid`) with a clean `422` before any database call is made — an invalid UUID can never produce a raw database error.
- **`short_code` normalization and uniqueness.** `short_code` is trimmed and upper-cased on create, restricted to 2–20 characters matching `^[A-Za-z0-9_-]+$`. Uniqueness is enforced two ways: a pre-check `SELECT` before insert (fast path, returns a clean `409`), and a `psycopg.errors.UniqueViolation` catch around the `INSERT` itself (backstop for a race between two near-simultaneous create requests, also returns a clean `409`). `short_code` cannot be changed via `PATCH` in this module.
- **Enum validation.** `status`, `sla_level`, and `business_criticality` are Pydantic `Literal` types whose allowed values are an exact match of the existing `tenants` table's `CHECK` constraints (`status`: `onboarding`/`active`/`inactive`/`suspended`; `sla_level`: `standard`/`business`/`premium`/`24x7`; `business_criticality`: `low`/`medium`/`high`/`critical`). Any other value is rejected with a clean `422` by Pydantic before it reaches SQL.
- **Invalid payload → `422`.** Missing required fields (e.g. `name` on create), bad `short_code` format, invalid enum values, and an empty `PATCH` body (no fields at all) all return `422` with FastAPI's standard validation error body — never a raw exception or stack trace.
- **Duplicate `short_code` → `409`.** Covered above.

## 12. Soft-delete decision

- **No `DELETE /admin/tenants/{tenant_id}` endpoint was added, by design.** Nearly every other table in the schema — `appliances`, `protected_assets`, `security_alerts`, `incidents`, `notification_events`, `customer_recommendations`, `monthly_reports`, and more — has a foreign key back to `tenants` with `ON DELETE CASCADE`. A real `DELETE` on a tenant row would silently and irreversibly destroy that tenant's entire history (every alert, incident, report, and appliance record) in one call, with no way to recover it short of a full backup restore.
- **`status = 'inactive'` or `status = 'suspended'` is used instead**, via the existing `PATCH` endpoint (e.g. `PATCH /admin/tenants/{id}` with body `{"status": "inactive"}`). This deactivates a tenant while keeping 100% of its historical data intact, reversible by simply patching `status` back to `active`. Both values were already valid under the existing `tenants_status_check` constraint before KB-013 — no schema change was needed to support this.

## 13. Validation commands run

```bash
cd /opt/mssp-control
git branch --show-current
git status --short
docker compose build backend-api
docker compose up -d backend-api
docker compose ps
curl -fsS http://localhost:8000/health | jq .
./scripts/kb013_validate_admin_tenant_management.sh
```

`scripts/kb013_validate_admin_tenant_management.sh` internally reruns `./scripts/kb012_validate_route_modularization.sh` (which itself reruns `./scripts/kb011_validate_protected_apis.sh`) as its behavior-regression gate.

## 14. Validation results

Reported by the user after running `./scripts/kb013_validate_admin_tenant_management.sh`:

```
KB-013 ADMIN TENANT MANAGEMENT VALIDATION PASSED
```

Confirmed by that run:

- `/health`, `/auth/roles`, `/docs` remain public.
- `GET`/`POST`/`PATCH /admin/tenants/*` all require a valid token (`401` enforced with no/garbage token).
- Customer roles (`customer_admin`, `customer_viewer`) are denied with `403` on all 3 new endpoints.
- `soc_manager` and `soc_analyst` can read tenant detail but cannot create or update tenants (`403` on `POST`/`PATCH`).
- `platform_admin` can create, read, and update tenants.
- An invalid (non-UUID) `tenant_id` returns a clean `422`.
- Invalid payloads (missing fields, bad enum values, empty `PATCH` body) return a clean `422`.
- A duplicate `short_code` returns a clean `409`.
- Soft-delete style deactivation via `PATCH {"status": "inactive"}` / `{"status": "suspended"}` works correctly.
- The `KBTEST13` validation tenant created during the run was cleaned up successfully — no leftover test data.
- `./scripts/kb012_validate_route_modularization.sh` passed unmodified inside the KB-013 run — no observable regression to route structure.
- `./scripts/kb011_validate_protected_apis.sh` passed unmodified inside the KB-012 run inside the KB-013 run — no observable regression to auth, RBAC, or tenant isolation.

## 15. Post-validation verification results

- Docker services (`mssp-postgres`, `mssp-redis`, `mssp-backend-api`) all running/healthy.
- `GET /health` returned API, database, and Redis all `ok`.
- `/openapi.json` now includes the two new paths:
  - `/admin/tenants/{tenant_id}`
  - `/admin/tenants` (in addition to the pre-existing `GET /admin/tenants` list path already present since KB-008)
- A follow-up cleanup query for the `KBTEST13` short_code returned **0 rows**, confirming no leftover validation data remains in the `tenants` table.

## 16. Final known-good state before commit

- Branch: `kb013-admin-tenant-management`
- Working tree changes (not yet committed):
  - Modified: `backend-api/app/main.py`, `backend-api/app/db/session.py`
  - New: `backend-api/app/schemas/tenants.py`, `backend-api/app/api/routes/tenant_management.py`, `scripts/kb013_validate_admin_tenant_management.sh`, `docs/KB013_ADMIN_TENANT_MANAGEMENT_COMPLETION.md`, and the `docs/AI_PROMPT_LEDGER.md` update from this same documentation pass.
- All KB-013 validation passed, and the KB-012/KB-011 regression gates passed unmodified underneath it.
- Nothing has been staged or committed as part of this module. Committing remains a manual, explicit decision for the user.

## 17. Rollback plan

- **Git rollback:** if KB-013 needs to be undone, roll back to the last known-good state — tag `kb012-route-modularization-validated` (commit `d2b1663`) — e.g.:
  ```bash
  git checkout kb012-route-modularization-validated -- backend-api/app/main.py backend-api/app/db/session.py
  rm -f backend-api/app/api/routes/tenant_management.py backend-api/app/schemas/tenants.py
  docker compose build backend-api
  docker compose up -d backend-api
  ```
- **Full VM rollback:** restore the Proxmox snapshot taken at the `kb012-route-modularization-validated` state, if one exists.
- **Data layer:** no schema or fixture-data changes were part of KB-013, so there is nothing to roll back at the database layer. The only data KB-013 ever wrote (the `KBTEST13` validation tenant) was created and deleted entirely within the validation script's own run — nothing persists from it.

## 18. Next recommended KB module

A reasonable next step is **KB-014: extend the same create/read/update pattern to another management area** — for example, admin-managed `appliance_activation_tokens` (so `platform_admin`/`soc_manager` can generate/revoke onboarding tokens through the API instead of SQL), or `platform_users` management (creating SOC/admin accounts through the API instead of seed scripts). Either would reuse the same RBAC pattern, validation style, and soft-delete-via-status approach established in KB-013. This is a recommendation only — the next module should be explicitly defined and approved by the user before any planning or implementation begins.
