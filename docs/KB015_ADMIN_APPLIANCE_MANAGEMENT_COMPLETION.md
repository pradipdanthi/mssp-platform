# KB-015 Admin Appliance Management API Foundation — Completion Summary

## 1. Module name and purpose

**KB-015: Admin Appliance Management API Foundation.**

Purpose: give `platform_admin` (and, for read access, `soc_manager`/`soc_analyst`) a proper API-based way to view appliance detail, update safe appliance metadata/status, and create/list/revoke appliance activation tokens for a tenant — instead of relying on manual SQL. This is an **admin-side only** foundation module: it does not touch how an appliance itself registers, authenticates, or reports health, which is a deliberately separate concern deferred to KB-016 (see section 3).

- Branch: `kb015-admin-appliance-management`
- Previous validated commit: `57a26ad` ("KB-014 add admin user management APIs")
- Previous tag: `kb014-admin-user-management-validated`
- Previous module: KB-014 Admin User Management API Foundation

## 2. Scope included

- `GET /admin/appliances/{appliance_id}` — single appliance detail, extending the existing `GET /admin/appliances` list.
- `PATCH /admin/appliances/{appliance_id}` — update `appliance_name`/`site_name`/`status` only.
- `POST /admin/tenants/{tenant_id}/appliance-activation-tokens` — create a new activation token for a tenant.
- `GET /admin/tenants/{tenant_id}/appliance-activation-tokens` — list a tenant's activation-token metadata.
- `PATCH /admin/appliance-activation-tokens/{token_id}/revoke` — revoke a still-`pending` token.
- New Pydantic request/response models (`backend-api/app/schemas/appliances.py`) that structurally exclude `token_hash` and the raw token from every model except the one-time creation response.
- New validation script `scripts/kb015_validate_admin_appliance_management.sh`, which validates the new endpoints end-to-end and then reruns `scripts/kb014_validate_admin_user_management.sh` unmodified as a regression gate (which itself cascades through KB-013 → KB-012 → KB-011).
- `backend-api/app/db/session.py` needed **zero changes** — the existing `fetch_one_write()` (added in KB-013) already covered every write KB-015 needed.
- `backend-api/app/core/error_handlers.py` needed **zero changes** — the global `RequestValidationError` sanitizer added in KB-014 already applies to every route in the app, including these five new ones, with no extra registration required.

## 3. Scope deferred to KB-016

The following are **agent-facing** (an appliance calling in from a customer site), not **admin-facing**, and were explicitly out of scope for KB-015:

- **Appliance self-registration** — an appliance presenting an activation token to obtain its own identity/credential.
- **Activation token redemption** — marking a token `used`, stamping `used_at`, and creating the corresponding `appliances` row.
- **Appliance heartbeat receiver** — an appliance periodically reporting health/status data.
- **Appliance-authentication model** — the caller here is not a `platform_users` row with a JWT; it needs its own credential/authentication scheme entirely.
- **Long-lived appliance credential design** — whatever an appliance uses to authenticate every heartbeat *after* the one-time activation token has been redeemed.

These require enough new, distinct design surface (a non-JWT caller identity, token-redemption state transitions, and untrusted-input handling for heartbeat data) that they were deliberately scoped into their own module rather than folded into this admin-CRUD foundation.

## 4. Files created

- `backend-api/app/schemas/appliances.py` — `ApplianceUpdateRequest`, `ApplianceDetail`, `ActivationTokenCreateRequest`, `ActivationTokenMetadata`, `ActivationTokenCreateResponse`, `ActivationTokensListResponse`.
- `backend-api/app/api/routes/appliance_management.py` — the five new endpoints, `ADMIN_APPLIANCE_WRITE_ROLES = ("platform_admin",)`, SHA-256 token generation/hashing.
- `scripts/kb015_validate_admin_appliance_management.sh` — KB-015 validation script.
- `docs/KB015_ADMIN_APPLIANCE_MANAGEMENT_COMPLETION.md` — this file.

## 5. Files modified

- `backend-api/app/main.py` — one new import line (`appliance_management_router`) and one new `app.include_router(appliance_management_router)` line. No other line was touched; the existing 6 `include_router` calls and the KB-014 exception-handler registration are unchanged.
- `docs/AI_PROMPT_LEDGER.md` — new KB-015 row added (see the ledger update in this same documentation pass).

## 6. Files not touched (protected)

- `backend-api/app/api/routes/admin.py`, `tenant_management.py`, `user_management.py`, `auth.py`, `customer.py`, `health.py`
- `backend-api/app/api/dependencies.py`
- `backend-api/app/core/security.py`, `core/config.py`, `core/error_handlers.py`
- `backend-api/app/services/auth_service.py`
- `backend-api/app/schemas/auth.py`, `schemas/tenants.py`, `schemas/users.py`
- `backend-api/app/db/session.py`
- `backend-api/requirements.txt` — no new dependency was needed (`secrets`/`hashlib` are standard library).
- `docker-compose.yml`, `.env`
- `postgres/init/001_mssp_core_schema.sql`, `postgres/init/002_kb010_auth_rbac.sql` — no schema change was needed; the existing `appliances` and `appliance_activation_tokens` tables already had every column KB-015 needed.
- `scripts/kb008_validate_backend_api_foundation.sh`, `kb010_validate_auth_rbac.sh`, `kb011_validate_protected_apis.sh`, `kb011_seed_rbac_fixtures.sh`, `kb012_validate_route_modularization.sh`, `kb013_validate_admin_tenant_management.sh`, `kb014_validate_admin_user_management.sh`

## 7. API endpoints added

| Endpoint | Description | Success | Errors |
|---|---|---|---|
| `GET /admin/appliances/{appliance_id}` | Single appliance detail (tenant name/short_code, protected-asset count, latest heartbeat) | `200` | `401`/`403`/`404`/`422` |
| `PATCH /admin/appliances/{appliance_id}` | Update `appliance_name`/`site_name`/`status` only | `200` | `401`/`403`/`404`/`409`/`422` |
| `POST /admin/tenants/{tenant_id}/appliance-activation-tokens` | Create an activation token for a tenant | `201` | `401`/`403`/`404`/`422` |
| `GET /admin/tenants/{tenant_id}/appliance-activation-tokens` | List a tenant's activation-token metadata | `200` | `401`/`403`/`404`/`422` |
| `PATCH /admin/appliance-activation-tokens/{token_id}/revoke` | Revoke a `pending` token | `200` | `401`/`403`/`404`/`409`/`422` |

## 8. Existing endpoint preserved

`GET /admin/appliances` (the list endpoint) remained in `backend-api/app/api/routes/admin.py` and **was not modified in any way** — same path, same SQL, same response shape, same `ADMIN_SOC_ROLES` RBAC gate it had before KB-015. The validation script explicitly re-checks that this endpoint still returns `401` with no token, as a direct regression check on the pre-existing behavior.

## 9. RBAC matrix

| Role | `GET` appliance detail | `PATCH` appliance | `POST` create token | `GET` list tokens | `PATCH` revoke token |
|---|---|---|---|---|---|
| `platform_admin` | Allowed | Allowed | Allowed | Allowed | Allowed |
| `soc_manager` | Allowed (read-only) | Denied — `403` | Denied — `403` | Allowed (read-only) | Denied — `403` |
| `soc_analyst` | Allowed (read-only) | Denied — `403` | Denied — `403` | Allowed (read-only) | Denied — `403` |
| `customer_admin` | Denied — `403` | Denied — `403` | Denied — `403` | Denied — `403` | Denied — `403` |
| `customer_viewer` | Denied — `403` | Denied — `403` | Denied — `403` | Denied — `403` | Denied — `403` |
| No token / garbage token | Denied — `401` | Denied — `401` | Denied — `401` | Denied — `401` | Denied — `401` |

Read access uses `ADMIN_SOC_ROLES`, imported unchanged from `admin.py`. Write access uses a new, local `ADMIN_APPLIANCE_WRITE_ROLES = ("platform_admin",)` — the same read/write split KB-013 and KB-014 already established for tenant and user management.

## 10. Appliance update rules

- **UUID path parameters** for `appliance_id`/`tenant_id`/`token_id`. FastAPI/Pydantic reject a malformed UUID with a clean `422` before any database call; a well-formed but unknown UUID returns a clean `404`.
- **`PATCH /admin/appliances/{appliance_id}` is limited to exactly three fields:**
  - `appliance_name`
  - `site_name`
  - `status`
- **Admin cannot update any agent-reported field**, by design — these are only ever meant to be written by the appliance's own heartbeat process (KB-016, not yet built), and letting an admin freely overwrite them would let the API lie about an appliance's real observed state:
  - `appliance_uuid`, `agent_version`, `config_version`, `git_commit`, `update_status`, `local_ip`, `last_source_ip`, `last_seen_at`, `health_snapshot`
- **At least one field is required** on `PATCH` (empty body → clean `422`), enforced both by `ApplianceUpdateRequest`'s `model_validator` and, defensively, again in the route handler.
- **`status` accepts the full existing database enum** — `registered`, `online`, `offline`, `maintenance`, `retired` — any other value is rejected with a clean `422` before reaching SQL.
- **Duplicate `appliance_name` within the same tenant → clean `409`.** The `appliances` table's `UNIQUE (tenant_id, appliance_name)` constraint is caught via `psycopg.errors.UniqueViolation` and turned into a `409 Conflict`, never a raw database error — the same defensive pattern KB-013/KB-014 used for `short_code`/`email`.

## 11. Activation token security model

- **Generation:** `secrets.token_urlsafe(32)` — Python's `secrets` module, cryptographically secure, unpredictable; 32 bytes = 256 bits of entropy.
- **Storage:** only `hashlib.sha256(raw_token).hexdigest()` is written to `token_hash`. The raw token is **never stored anywhere** and never written to logs.
- **One-time exposure:** the raw token is returned **exactly once**, in the `token` field of the `POST .../appliance-activation-tokens` `201` response, alongside `metadata` (the durable, re-fetchable record). No other endpoint — the list endpoint, the revoke endpoint, or any future `GET` — ever returns it.
- **`token_hint`** stores only the last 6 characters of the raw token, purely so an admin can visually distinguish list entries — not reversible to the full token.
- **`token_hash` is never returned by any API response.** `ActivationTokenMetadata` has no such field at all, the same structural-impossibility principle `UserDetail` already uses for `password_hash`.
- **`created_by_user_id` is set automatically from the authenticated `platform_admin`'s own id** (`current_user["id"]`) — never a client-supplied value — giving every token a reliable audit trail of who issued it.
- **TTL:** `expires_in_hours` is optional on create, defaulting to `24`, with a hard minimum of `1` and maximum of `720` (30 days), enforced by Pydantic (`Field(default=24, ge=1, le=720)`) before it ever reaches SQL; `expires_at = now() + expires_in_hours hours` is computed server-side.
- **Revoke is only valid from `pending`.** `PATCH .../revoke` pre-checks the token's current status: not found → `404`; found but not `pending` (already `used`/`expired`/`revoked`) → clean `409`; otherwise `UPDATE ... SET status = 'revoked' WHERE id = %s AND status = 'pending'`.
- **No manual "expire" action was added.** Expiry is a consequence of comparing `expires_at` to the current time, not a discrete admin decision the way revoke is, and there is no scheduled worker in this codebase to flip `pending` → `expired` automatically. Whatever eventually redeems a token (KB-016) should check `expires_at` itself at redemption time, regardless of the stored `status` value.

## 12. No-delete / no-hard-delete reasoning

- **No `DELETE /admin/appliances/{appliance_id}`.** `appliance_heartbeats.appliance_id` is `ON DELETE CASCADE` — a hard delete would permanently destroy an appliance's entire heartbeat/health history. `protected_assets.appliance_id` is `ON DELETE SET NULL` — a hard delete would silently orphan any assets tied to it. `PATCH {"status": "retired"}` (already a valid enum value) achieves the same practical outcome — "this appliance is no longer in service" — reversibly, with zero historical data loss.
- **No `DELETE /admin/appliance-activation-tokens/{token_id}`.** `created_by_user_id` exists specifically to attribute who issued a token; a hard delete would erase that attribution. Revoke already covers the real operational need ("make this unused token unusable") without destroying the historical record of "a token was issued, by whom, for which tenant/site, and what ultimately happened to it" — valuable audit trail for an MSSP platform.
- **The validation script's own cleanup is a direct SQL `DELETE`, not the API.** `scripts/kb015_validate_admin_appliance_management.sh` removes its own throwaway fixtures (two fake appliance rows and one fake activation token, all named/labeled unambiguously as KB-015 validation data) with direct `DELETE` statements against the database, both at the end of a successful run and in its failure-cleanup trap. This is the validation script cleaning up its own disposable test data at the database layer — a different concern from the API intentionally not exposing `DELETE` endpoints to normal callers.

## 13. Validation steps performed

```bash
cd /opt/mssp-control
git branch --show-current
git status --short
docker compose up -d --build backend-api
docker compose ps
curl -fsS http://localhost:8000/health | jq .
./scripts/kb015_validate_admin_appliance_management.sh
```

`scripts/kb015_validate_admin_appliance_management.sh` internally reruns `./scripts/kb014_validate_admin_user_management.sh` (which itself reruns `kb013_validate_admin_tenant_management.sh`, which reruns `kb012_validate_route_modularization.sh`, which reruns `kb011_validate_protected_apis.sh`) as its behavior-regression gate.

Confirmed by the passing run:

- Public endpoints remain public: `/health`, `/auth/roles`, `/docs`.
- Existing `GET /admin/appliances` still requires a valid token (`401` with no token) — unmodified, direct regression check.
- All five new KB-015 endpoints require a valid token (`401` with no/garbage token).
- Customer roles (`customer_admin`, `customer_viewer`) are denied with `403` on all five new endpoints.
- `soc_manager`/`soc_analyst` can read (`GET` appliance detail, `GET` token list) but cannot write (`403` on `PATCH` appliance, `POST` token create, `PATCH` revoke).
- `platform_admin` can read and update appliance metadata/status.
- Invalid (non-UUID) `appliance_id`/`tenant_id`/`token_id` path parameters return a clean `422`.
- Unknown but well-formed UUIDs return a clean `404`.
- Duplicate `appliance_name` within the same tenant returns a clean `409`.
- Invalid activation-token creation payloads (missing `site_name`, `expires_in_hours` out of the `1`–`720` range) return `422`.
- `platform_admin` created a clearly fake activation token for the `DEMO` tenant; the raw token appeared **exactly once**, in the creation response.
- `token_hash` was never present in any response body.
- The raw activation token was never present in any response body outside its one creation response.
- Revoke worked for the pending token (`200`, `status` became `revoked`); revoking it a second time returned a clean `409`.
- All fake validation appliance/activation-token fixtures were cleaned up — 0 rows remaining afterward.
- `./scripts/kb014_validate_admin_user_management.sh` passed unmodified inside the KB-015 run — no observable regression to user management.
- `./scripts/kb013_validate_admin_tenant_management.sh` passed unmodified through KB-014 inside the KB-015 run — no observable regression to tenant management.
- `./scripts/kb012_validate_route_modularization.sh` passed unmodified through KB-013 inside the KB-015 run — no observable regression to route structure.
- `./scripts/kb011_validate_protected_apis.sh` passed unmodified through KB-012 inside the KB-015 run — no observable regression to auth, RBAC, or tenant isolation.

## 14. First validation failure and fix

**First run: failed in section 10** (creating the fake validation appliance fixtures), with a `422 uuid_parsing` error on a value that looked like `5320f6e9-0366-4010-9f07-e9bcd31d1468INSERT01`.

**Root cause: this was a validation-script bug, not an application/API bug.** The script captured a fake appliance's new id with:

```bash
docker compose exec -T postgres psql -tA -c "INSERT ... RETURNING id;" | tr -d '[:space:]'
```

For a non-`SELECT` statement, `psql` prints the `RETURNING` value on one line **and** a separate command-tag line (e.g. `INSERT 0 1`) on the next. `tr -d '[:space:]'` stripped *all* whitespace, including the newline separating those two lines, welding them into one corrupted string. The API correctly rejected that corrupted value with a clean `422` — exactly the behavior it should have.

**Fix, applied only to `scripts/kb015_validate_admin_appliance_management.sh` (no application/API code changes needed or made):**

- Added a `UUID_REGEX` constant (`^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$`).
- Added a `psql_scalar()` helper: runs a query via `psql -X -q -t -A -v ON_ERROR_STOP=1`, trims a trailing `\r` and drops blank lines **without ever merging separate non-blank lines together**, and requires the result be exactly one line — failing loudly instead of returning corrupted data.
- Added a `validate_uuid()` helper that checks a captured value against `UUID_REGEX` and fails immediately, before any API call is made with it.
- Rewrote both fixture-creation statements as `WITH inserted AS (INSERT ... RETURNING id::text) SELECT id FROM inserted;` — this makes the statement `psql` actually executes a `SELECT`, which never has a row-count command tag to begin with.
- Reviewed and switched the other direct-SQL captures in the script (the post-cleanup row-count checks) to the same `psql_scalar()` helper for consistency, even though a plain `SELECT count(*)` was less likely to hit this exact bug.
- Cleanup behavior was unaffected: `cleanup_fake_data()` deletes by static fake name/site-name string constants, not by any captured id, so it remained robust throughout.

**Second run: passed.**

## 15. Final validation result

```
KB-015 ADMIN APPLIANCE MANAGEMENT VALIDATION PASSED
```

Reported by the user after rerunning `./scripts/kb015_validate_admin_appliance_management.sh` following the validation-script fix in section 14.

## 16. Final post-validation safety result

- Docker services (`mssp-postgres`, `mssp-redis`, `mssp-backend-api`) all running/healthy.
- `GET /health` returned OK.
- `/openapi.json` includes all four new KB-015 paths:
  - `/admin/appliances/{appliance_id}`
  - `/admin/tenants/{tenant_id}/appliance-activation-tokens`
  - `/admin/appliance-activation-tokens/{token_id}/revoke`
  - (`/admin/appliances`, the pre-existing list endpoint, is unchanged and still present)
- A follow-up cleanup query for the fake KB-015 validation appliance fixtures returned **0 rows**.
- A follow-up cleanup query for the fake KB-015 validation activation-token fixture returned **0 rows**.
- Python syntax check (`py_compile`) passed for all new/changed Python files.
- Bash syntax check (`bash -n`) passed for the validation script.

## 17. Operational notes for future modules

- **The appliance-facing surface is still entirely unbuilt.** Nothing in this repository yet lets a real (or simulated) appliance register itself, redeem an activation token, or send a heartbeat — `POST/GET/PATCH` under `/admin/...` here are strictly for a human `platform_admin`/SOC user acting through the admin dashboard's future backend calls.
- **Token redemption will need its own authentication model.** An appliance is not a `platform_users` row and cannot get a JWT the way a human user does — KB-016 will need to design how an appliance proves possession of a raw activation token (hash-and-compare against `token_hash`, the same principle used here) and, likely, what long-lived credential it receives afterward for repeat heartbeat calls.
- **`appliances.status` is fully admin-writable today with no state-machine restrictions.** Until KB-016's heartbeat receiver exists, nothing else in this codebase writes to that column, so there is no real conflict risk yet — but once heartbeats exist, an admin-set `online`/`offline` value could be immediately overwritten by the next real heartbeat. This was a deliberate, approved choice (Decision D), not an oversight, and is worth keeping in mind when KB-016 is scoped.
- **Expiry is intentionally lazy.** No code anywhere flips a `pending` activation token to `expired` based on the passage of time — whatever consumes/redeems a token in KB-016 must check `expires_at` itself at redemption time, not trust the stored `status` value alone.
- **The regression-gate chain is now four scripts deep** (KB-015 → KB-014 → KB-013 → KB-012 → KB-011). Each new module's validation script continues to rerun the previous module's script unmodified, which is working well as a lightweight regression suite — this pattern should continue for KB-016 and beyond.

## 18. Next recommended module

**KB-016: Appliance Registration and Heartbeat Receiver Foundation.**

This is the natural next step: it would consume the activation tokens KB-015 now lets `platform_admin` create, and build the agent-facing side that was explicitly deferred here (see section 3) — an appliance-authentication model, activation-token redemption (turning a `pending` token into a real `appliances` row and marking it `used`), and a heartbeat-ingestion endpoint that safely accepts and stores the health/status data KB-015's `GET /admin/appliances/{appliance_id}` already knows how to display (`latest_health_status`, `latest_heartbeat_at`) but currently has no legitimate way to receive. This is a recommendation only — the next module should be explicitly defined and approved by the user before any planning or implementation begins.
