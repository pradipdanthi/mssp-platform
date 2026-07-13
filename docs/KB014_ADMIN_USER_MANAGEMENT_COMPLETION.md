# KB-014 Admin User Management API Foundation — Completion Summary

## 1. Module name and purpose

**KB-014: Admin User Management API Foundation.**

Purpose: give `platform_admin` a proper API-based way to list, view, create, update, disable/enable, and set passwords for `platform_users` rows — the platform/SOC accounts and customer accounts that log into this system — instead of relying on manual SQL updates. `soc_manager` and `soc_analyst` get read-only visibility into the same data (list and detail), matching their existing read tier on tenant management. This is a foundation module: it adds new endpoints alongside the existing `/auth/*` authentication endpoints, with no schema, infrastructure, or auth-model changes.

## 2. Starting point

- Previous validated commit: `95064ed`
- Previous tag: `kb013-admin-tenant-management-validated`
- Previous module: KB-013 Admin Tenant Management API Foundation
- Branch worked on: `kb014-admin-user-management`

## 3. Scope of KB-014

- Added five new endpoints under `/admin/users/*`:
  - `GET /admin/users` — list all users.
  - `GET /admin/users/{user_id}` — single user detail.
  - `POST /admin/users` — create a new user, with bcrypt password hashing.
  - `PATCH /admin/users/{user_id}` — update `full_name`/`phone`/`status` only.
  - `PATCH /admin/users/{user_id}/password` — admin-triggered password set (not a self-service reset).
- Added Pydantic request/response models for these endpoints (`backend-api/app/schemas/users.py`), including server-side derivation of `user_type` from `role` and strict enforcement of the admin/SOC-vs-customer `tenant_id` rule.
- Added `scripts/kb014_validate_admin_user_management.sh`, which validates the new endpoints end-to-end and then reruns `scripts/kb013_validate_admin_tenant_management.sh` unmodified as a regression gate (which itself cascades through KB-012 and KB-011).
- **Mid-module security fix:** discovered and fixed a validation-error information-disclosure issue (see section 11) by adding a global `RequestValidationError` handler (`backend-api/app/core/error_handlers.py`) and registering it in `main.py`. This fix is a core part of KB-014, not a separate module, since it was required before KB-014 could pass its own validation safely.
- `backend-api/app/db/session.py` needed **zero changes** — the existing `fetch_one_write()` (added in KB-013) already covered every write KB-014 needed.

## 4. What was intentionally not included

- **No frontend.** No admin or customer dashboard UI work was done or scaffolded.
- **No database schema change.** The existing `platform_users` table (from `postgres/init/001_mssp_core_schema.sql` plus the KB-010 `password_hash` addition in `postgres/init/002_kb010_auth_rbac.sql`) already had every field KB-014 needed.
- **No `docker-compose.yml` change.** No new services, environment variables, or container config were added.
- **No `.env` change.** `.env` was never read, printed, or modified at any point in this module.
- **No `DELETE /admin/users/{user_id}` endpoint.** See section 12 for why.
- **No self-service forgot-password workflow.** The password-set endpoint is admin-triggered only (`platform_admin` supplies the new password directly) — a token/email-based "forgot password" flow was explicitly deferred because it requires notification-delivery infrastructure that does not exist yet in this platform.
- **No role reassignment, tenant transfer, or email-change capability.** `PATCH /admin/users/{user_id}` is deliberately limited to `full_name`/`phone`/`status` only (Decision F) — changing a user's `role`, `tenant_id`, or `email` after creation is out of scope for this foundation module, matching the same "stable identifier at creation" precedent KB-013 set for `short_code`.

## 5. Files created

- `backend-api/app/schemas/users.py` — `UserCreateRequest`, `UserUpdateRequest`, `UserPasswordUpdateRequest`, `UserDetail`, `UsersListResponse` Pydantic models, plus the shared `ADMIN_ROLES`/`CUSTOMER_ROLES` role-bucket constants.
- `backend-api/app/api/routes/user_management.py` — the new `/admin/users/*` router (`GET ""`, `GET /{user_id}`, `POST ""`, `PATCH /{user_id}`, `PATCH /{user_id}/password`).
- `backend-api/app/core/error_handlers.py` — the global `RequestValidationError` sanitizing handler added as part of the mid-module security fix (see section 11).
- `scripts/kb014_validate_admin_user_management.sh` — KB-014 validation script.
- `docs/KB014_ADMIN_USER_MANAGEMENT_COMPLETION.md` — this file.

## 6. Files modified

- `backend-api/app/main.py` — two new import lines (`user_management_router`, and `RequestValidationError`/`validation_exception_handler` for the security fix) and two new registration lines (`app.add_exception_handler(...)` and `app.include_router(user_management_router)`). No other line was touched; the existing 5 `include_router` calls and app metadata from KB-010–KB-013 are unchanged.
- `docs/AI_PROMPT_LEDGER.md` — new KB-014 row added (see section 17/ledger update below).

## 7. Protected files intentionally not touched

- `backend-api/app/api/routes/admin.py`, `tenant_management.py`, `auth.py`, `customer.py`, `health.py`
- `backend-api/app/api/dependencies.py`
- `backend-api/app/core/security.py`, `core/config.py`
- `backend-api/app/services/auth_service.py`
- `backend-api/app/schemas/auth.py`, `schemas/tenants.py`
- `backend-api/app/db/session.py` — no new helper was needed; `fetch_one_write()` from KB-013 covered everything.
- `backend-api/requirements.txt` — no new dependency was needed (email format uses a plain regex, not `EmailStr`/`email-validator`).
- `docker-compose.yml`, `.env`
- `postgres/init/001_mssp_core_schema.sql`, `postgres/init/002_kb010_auth_rbac.sql`
- `scripts/kb008_validate_backend_api_foundation.sh`, `kb010_validate_auth_rbac.sh`, `kb011_validate_protected_apis.sh`, `kb011_seed_rbac_fixtures.sh`, `kb012_validate_route_modularization.sh`, `kb013_validate_admin_tenant_management.sh`

## 8. API endpoints added

- `GET /admin/users` — list all platform users. Requires `platform_admin`, `soc_manager`, or `soc_analyst`.
- `GET /admin/users/{user_id}` — single user detail. Same read roles as above. `404` if not found; `422` if `user_id` isn't a valid UUID.
- `POST /admin/users` — create a new user, with bcrypt password hashing. Requires `platform_admin`. Returns `201` with the created user's detail.
- `PATCH /admin/users/{user_id}` — update `full_name`/`phone`/`status` only. Requires `platform_admin`. Returns `200` with the updated user's detail.
- `PATCH /admin/users/{user_id}/password` — admin-triggered password set. Requires `platform_admin`. Returns `200` with the user's detail (never the password or its hash).

## 9. RBAC behavior

| Role | `GET /admin/users`, `GET /admin/users/{id}` | `POST /admin/users` | `PATCH /admin/users/{id}` | `PATCH /admin/users/{id}/password` |
|---|---|---|---|---|
| `platform_admin` | Allowed | Allowed | Allowed | Allowed |
| `soc_manager` | Allowed (read-only) | Denied — 403 | Denied — 403 | Denied — 403 |
| `soc_analyst` | Allowed (read-only) | Denied — 403 | Denied — 403 | Denied — 403 |
| `customer_admin` | Denied — 403 | Denied — 403 | Denied — 403 | Denied — 403 |
| `customer_viewer` | Denied — 403 | Denied — 403 | Denied — 403 | Denied — 403 |
| No token / garbage token | Denied — 401 | Denied — 401 | Denied — 401 | Denied — 401 |

This matches approved Decision A: `platform_admin` has full read/write/password-set access; `soc_manager` and `soc_analyst` are read-only; customer roles are denied entirely — the same shape KB-013 established for tenant management.

## 10. User validation behavior

- **UUID `user_id` path parameter** on all three `{user_id}` routes (Decision B). FastAPI/Pydantic reject a malformed ID with a clean `422` before any database call — an invalid UUID never produces a raw database error.
- **Email normalized to lowercase** on create, matching the case-insensitive lookup `auth_service.get_user_by_email()` already uses for login (`lower(email) = lower(%s)`), so no new case-variant duplicate can be created going forward.
- **Duplicate email → clean `409`**, via a two-layer defense: a pre-check `SELECT` before insert (fast path), plus a `psycopg.errors.UniqueViolation` catch around the `INSERT` itself (race-condition backstop) — the same pattern KB-013 used for tenant `short_code`.
- **Valid role enforcement.** `role` is a Pydantic `Literal` restricted to the 5 values in the `platform_users_role_check` constraint (`platform_admin`, `soc_manager`, `soc_analyst`, `customer_admin`, `customer_viewer`) — any other value is rejected with a clean `422` before it reaches SQL.
- **Admin/SOC roles must not have a `tenant_id`; customer roles must have a valid one (Decision E).** Enforced two ways: `UserCreateRequest`'s `model_validator` rejects the *shape* mismatch (e.g. a `customer_viewer` submitted with no `tenant_id`, or a `soc_analyst` submitted with one) with a clean `422`; separately, if a `tenant_id` is supplied, the router checks it against the `tenants` table and returns a clean `422` if it doesn't reference a real tenant.
- **`user_type` is derived server-side from `role`, never accepted as input.** `UserCreateRequest` has no `user_type` field at all, so a role/user_type mismatch is structurally impossible to submit — this closes a gap the database schema itself doesn't cover (there is no `CHECK` constraint tying `role` to `user_type`).
- **Invalid payloads → `422`.** Missing required fields, bad email format, invalid role/status enum values, and an empty `PATCH` body (no fields at all) all return `422` with a standard FastAPI validation error body — never a raw exception or stack trace, and (after the mid-module fix) never the caller's submitted password either.

## 11. Password/security behavior

- **Password hashing uses the existing `hash_password()`** from `backend-api/app/core/security.py`, unchanged — the exact same bcrypt function `POST /auth/login` already trusts, imported and called, never reimplemented.
- **`password_hash` is never returned.** Every SQL query in `user_management.py` explicitly lists columns and never selects `password_hash`; `UserDetail` has no such field at all, making a leak through the normal response path structurally impossible (the same principle `UserPublic` in `schemas/auth.py` already used).
- **Password values are never returned** in a successful response — `POST`/`PATCH .../password` responses return `UserDetail` only, never echoing the submitted password back.
- **Mid-module security issue found and fixed: the validation-error response path could leak a submitted password.** FastAPI's default `RequestValidationError` handler includes an `"input"` field on each error entry, which is the raw value Pydantic tried to validate. For a whole-model validator (`UserCreateRequest`'s `model_validator(mode="after")`, which enforces the admin/SOC-vs-customer `tenant_id` rule above), that `"input"` is the *entire submitted request body* — not just the offending field — so a `422` response to, for example, "customer role submitted without a `tenant_id`" would have echoed the caller's plaintext `password` straight back in the response. This was caught by the KB-014 validation script itself on the first run (see section 13).

  **Fix:** added `backend-api/app/core/error_handlers.py`, a global handler for `RequestValidationError` registered in `main.py`. It keeps the standard `422` status code and `{"detail": [...]}` shape, with `loc`/`type`/`msg` preserved exactly as before (they only ever identify which field failed and why, never the value) — it redacts `"input"` (and defensively `"ctx"`) to the string `"<redacted>"` in two cases: (a) the error's own `loc` points directly at a sensitive field name (e.g. `["body", "new_password"]`, covering plain field-level errors like a too-short password), or (b) `input` is itself a dict/list containing a sensitive key anywhere inside it, at any depth (covering the whole-model-validator case that caused the failure). The sensitive-key list is `password`, `new_password`, `password_hash`, `access_token`, `token`, `jwt`, `secret`, `jwt_secret`. The handler is deliberately global — it applies to every route in the app, not only KB-014's — but it was verified (via direct `jq` testing against sample payloads before rerunning the full validation) to leave every non-sensitive `422` response completely unchanged, including KB-013's existing tenant-validation errors (bad `short_code`, invalid `status` enum) and error `loc` arrays that merely contain the word `"password"` as an array value rather than a real object key.

- **Disabling a user via `status=inactive` (or `status=locked`) blocks their login immediately, using existing, unmodified auth behavior.** `app/services/auth_service.authenticate_user()` already checks `status != 'active'` and raises `AccountNotActiveError` → `auth.py` already turns that into `403 "Account is not active"`. `app/api/dependencies.py`'s `get_current_user()` also already re-checks `status` against the live database on *every* authenticated request, not just at login — so disabling a user immediately invalidates their already-issued, still-valid token too, with zero code changes to `auth.py`, `dependencies.py`, or `auth_service.py` for KB-014.

## 12. No hard-delete decision

- **No `DELETE /admin/users/{user_id}` endpoint was added, by design.** `platform_users.id` is referenced with `ON DELETE SET NULL` (not `CASCADE`) from `incidents.assigned_to_user_id`, `incident_timeline.created_by_user_id`, `incident_comments.created_by_user_id`, `appliance_activation_tokens.created_by_user_id`, and `audit_logs.actor_user_id`. A hard delete would not destroy those historical rows, but it would silently strip the attribution off them — every incident, comment, timeline entry, activation token, and audit log entry that user ever touched would permanently lose the record of *who* did it. For an MSSP platform where `audit_logs` exists specifically for "audit/compliance visibility" (a required capability per `AGENTS.md`), losing that attribution is a real, avoidable cost with no corresponding benefit.
- **`status = 'inactive'` or `status = 'locked'` is used instead**, via the existing `PATCH /admin/users/{user_id}` endpoint (e.g. `{"status": "inactive"}`). This immediately blocks the user's login and any already-issued token (see section 11), while keeping 100% of their historical attribution intact, and is fully reversible by simply patching `status` back to `active`. Both values were already valid under the existing `platform_users_status_check` constraint before KB-014 — no schema change was needed.
- **The validation script's own cleanup is a direct SQL `DELETE`, not the API.** `scripts/kb014_validate_admin_user_management.sh` removes its own throwaway fixture (`kb014.validation.user@example.local`) with a direct `DELETE FROM platform_users WHERE email = ...` against the database at the very end of the run (and in its failure-cleanup trap). This is the validation script cleaning up its own disposable test data at the database layer — a different concern from the API intentionally not exposing a `DELETE` endpoint to normal callers, which is specifically about protecting *real* audit/compliance history from accidental or malicious destruction.

## 13. Validation commands run

```bash
cd /opt/mssp-control
git branch --show-current
git status --short
docker compose build backend-api
docker compose up -d backend-api
docker compose ps
curl -fsS http://localhost:8000/health | jq .
./scripts/kb014_validate_admin_user_management.sh
```

`scripts/kb014_validate_admin_user_management.sh` internally reruns `./scripts/kb013_validate_admin_tenant_management.sh` (which itself reruns `kb012_validate_route_modularization.sh`, which reruns `kb011_validate_protected_apis.sh`) as its behavior-regression gate.

**First run: failed.** Section 12 of the validation script (`POST /admin/users customer role without tenant_id`) got the expected `422` status code, but the script's leak-checker detected a password-related field in the response body — this was the real security issue described in section 11 above, correctly caught by the validation script doing its job. The fix (`error_handlers.py` + the `main.py` registration + the improved leak-checker in the validation script itself) was applied, then the full script was rerun from a clean state.

**Second run: passed.**

## 14. Validation results

Reported by the user after rerunning `./scripts/kb014_validate_admin_user_management.sh` following the fix:

```
KB-014 ADMIN USER MANAGEMENT VALIDATION PASSED
```

Confirmed by that run:

- `/health`, `/auth/roles`, `/docs` remain public.
- `GET`/`POST`/`PATCH /admin/users/*` all require a valid token (`401` enforced with no/garbage token).
- Customer roles (`customer_admin`, `customer_viewer`) are denied with `403` on all new endpoints.
- `soc_manager` and `soc_analyst` can list/read users but cannot create, update, or reset passwords (`403`).
- `platform_admin` can create, read, update, disable/enable, and set passwords for users.
- An invalid (non-UUID) `user_id` returns a clean `422`.
- Invalid payloads (bad role, missing/mismatched `tenant_id`, empty `PATCH` body) return a clean `422`.
- Duplicate email returns a clean `409`.
- The created validation user could log in with its created password.
- `PATCH {"status": "inactive"}` blocked login; `PATCH {"status": "active"}` restored it.
- `PATCH /admin/users/{user_id}/password` changed the password — the old password stopped working, and the new password worked.
- No response contained `password_hash`.
- No response exposed a password value (including in `422` validation-error bodies, after the fix).
- The validation user `kb014.validation.user@example.local` was cleaned up successfully — no leftover data.
- `./scripts/kb013_validate_admin_tenant_management.sh` passed unmodified inside the KB-014 run — no observable regression to tenant management.
- `./scripts/kb012_validate_route_modularization.sh` passed unmodified through KB-013 inside the KB-014 run — no observable regression to route structure.
- `./scripts/kb011_validate_protected_apis.sh` passed unmodified through KB-012 inside the KB-014 run — no observable regression to auth, RBAC, or tenant isolation.

## 15. Post-validation verification results

- Docker services (`mssp-postgres`, `mssp-redis`, `mssp-backend-api`) all running/healthy.
- `GET /health` returned API, database, and Redis all `ok`.
- `/openapi.json` now includes the three new paths:
  - `/admin/users`
  - `/admin/users/{user_id}`
  - `/admin/users/{user_id}/password`
- A follow-up cleanup query for `kb014.validation.user@example.local` returned **0 rows**, confirming no leftover validation data remains in `platform_users`.
- Python syntax check (`py_compile`) passed for all new/changed Python files.
- Bash syntax check (`bash -n`) passed for the validation script.

## 16. Final known-good state before commit

- Branch: `kb014-admin-user-management`
- Working tree changes (not yet committed):
  - Modified: `backend-api/app/main.py`
  - New: `backend-api/app/schemas/users.py`, `backend-api/app/api/routes/user_management.py`, `backend-api/app/core/error_handlers.py`, `scripts/kb014_validate_admin_user_management.sh`, `docs/KB014_ADMIN_USER_MANAGEMENT_COMPLETION.md`, and the `docs/AI_PROMPT_LEDGER.md` update from this same documentation pass.
- All KB-014 validation passed on the second run (after the mid-module security fix), and the KB-013/KB-012/KB-011 regression gates passed unmodified underneath it.
- Nothing has been staged or committed as part of this module. Committing remains a manual, explicit decision for the user.

## 17. Rollback plan

- **Git rollback:** if KB-014 needs to be undone, roll back to the last known-good state — tag `kb013-admin-tenant-management-validated` (commit `95064ed`) — e.g.:
  ```bash
  git checkout kb013-admin-tenant-management-validated -- backend-api/app/main.py
  rm -f backend-api/app/api/routes/user_management.py backend-api/app/schemas/users.py backend-api/app/core/error_handlers.py
  docker compose build backend-api
  docker compose up -d backend-api
  ```
- **Full VM rollback:** restore the Proxmox snapshot taken at the `kb013-admin-tenant-management-validated` state, if one exists.
- **Data layer:** no schema changes were part of KB-014, so there is nothing to roll back at the database layer. The only data KB-014 ever wrote (the `kb014.validation.user@example.local` validation user) was created and deleted entirely within the validation script's own run — nothing persists from it.

## 18. Next recommended KB module

A reasonable next step is **KB-015: extend the same pattern to a role/tenant-transfer follow-up module**, covering the capabilities explicitly deferred from KB-014's `PATCH /admin/users/{user_id}` (changing a user's `role`, moving a customer user between tenants, or changing `email`) — each of these requires re-validating the combined role/tenant_id/user_type state after the change, which is meaningfully more complex than the disable/enable and contact-info updates KB-014 covers, and was deliberately scoped out to keep this module small. Alternatively, **KB-015 could instead extend admin management to `appliance_activation_tokens`** (generate/revoke onboarding tokens through the API instead of SQL), reusing the same RBAC and validation patterns established across KB-013/KB-014. This is a recommendation only — the next module should be explicitly defined and approved by the user before any planning or implementation begins.
