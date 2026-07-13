# KB-011 Protected APIs Completion Summary

## Status

**VALIDATED.**

KB-011 (Protect existing `/admin/*` and `/customer/*` APIs with Auth, RBAC, and Tenant Isolation) has been implemented and manually validated on branch:

`kb011-protect-admin-customer-apis`

## Validation command and result

Validation command:

```
./scripts/kb011_validate_protected_apis.sh
```

Validation result (as reported by the user after running it):

```
KB-011 PROTECTED APIS VALIDATION PASSED
KB-011 validation completed successfully.
```

## Approved decisions

The approved implementation choices were (see `docs/KB011_DECISION_QUESTIONS.md`, all approved as the recommended option):

1. Allow `platform_admin`, `soc_manager`, and `soc_analyst` cross-tenant read access on `/customer/*` for support/troubleshooting.
2. Give `soc_analyst` the same access as `soc_manager` on all 5 `/admin/*` endpoints (all read-only today).
3. Add a small, permanent, clearly-fake second demo tenant (`DEMO2`) for tenant-isolation testing, rather than a temporary create-and-delete-per-run tenant.
4. Add demo login accounts for the 3 roles that didn't have one yet (`platform_admin`, `soc_analyst`, `customer_admin`) so all 5 roles could be validated end-to-end.

## Public endpoints (unchanged, no token required)

- `GET /health`
- `POST /auth/login`
- `GET /auth/roles`
- `GET /docs`

## Protected endpoints

- `GET /auth/me` — protected since KB-010, unchanged by KB-011.
- `GET /admin/dashboard`
- `GET /admin/tenants`
- `GET /admin/appliances`
- `GET /admin/alerts`
- `GET /admin/incidents`
- `GET /customer/dashboard/{short_code}`
- `GET /customer/incidents/{short_code}`

## RBAC behavior

- `platform_admin`, `soc_manager`, and `soc_analyst` can access all 5 `/admin/*` endpoints, and can read `/customer/*` endpoints for any tenant (cross-tenant support/troubleshooting access).
- `customer_admin` and `customer_viewer` can access only their own tenant's `/customer/*` endpoints.
- Customer roles (`customer_admin`, `customer_viewer`) get **403 Forbidden** if they call any `/admin/*` endpoint.
- A customer role calling a `/customer/*` endpoint for a tenant that is not their own gets **404 Tenant not found** — the same response as a tenant that doesn't exist at all. This is deliberate anti-enumeration behavior: a customer's token can never be used to learn whether another tenant's `short_code` is real.
- Missing or invalid/expired tokens get **401 Unauthorized** on every protected endpoint.

## Demo fixture data used for validation

- Tenant `DEMO` — already existed (seeded in KB-007).
- Tenant `DEMO2` — added in KB-011, clearly fake, validation-only ("Demo Tenant Two (KB-011 Validation)").
- Demo login accounts exercised during validation:
  - `platform.admin@example.local` — role `platform_admin` (new in KB-011)
  - `soc.manager@example.local` — role `soc_manager` (existing since KB-010)
  - `soc.analyst@example.local` — role `soc_analyst` (new in KB-011)
  - `customer.admin@demo2.local` — role `customer_admin`, tenant `DEMO2` (new in KB-011)
  - `customer.viewer@demo.local` — role `customer_viewer`, tenant `DEMO` (existing since KB-010)

No passwords or password hashes are recorded anywhere in this document, in the seed script, or in the validation script. Passwords are entered interactively via hidden terminal prompts and only bcrypt hashes are ever stored in the database.

## Files changed

**Modified:**
- `backend-api/app/main.py` — added `Depends(require_roles(*ADMIN_SOC_ROLES))` to the 5 `/admin/*` endpoints; added `Depends(get_current_user)` plus a `require_tenant_match(...)` call to both `/customer/*` endpoints.
- `AGENTS.md`, `CLAUDE.md`, `.cursor/rules/mssp-control-plane.mdc` — updated to reflect KB-011 as validated/completed.
- `docs/AI_PROMPT_LEDGER.md` — KB-011 row updated from pending to passed.

**Created:**
- `scripts/kb011_seed_rbac_fixtures.sh` — seeds the `DEMO2` tenant and the 3 new demo users.
- `scripts/kb011_validate_protected_apis.sh` — the validation script referenced above.
- `docs/KB011_DECISION_QUESTIONS.md` — the 4 approved planning decisions.
- `docs/KB011_IMPLEMENTATION_PLAN.md` — the full implementation plan.
- `docs/KB011_PROTECTED_APIS_COMPLETION.md` — this file.

**Not touched:** `docker-compose.yml`, `postgres/init/001_mssp_core_schema.sql`, `postgres/init/002_kb010_auth_rbac.sql`, `backend-api/app/api/dependencies.py`, `backend-api/app/api/routes/auth.py`, `.env`.

## Important note about the older validation scripts

`scripts/kb008_validate_backend_api_foundation.sh` and `scripts/kb010_validate_auth_rbac.sh` (which internally re-runs the KB-008 script) call `/admin/*` and `/customer/*` **without** a token and expect `200`. Now that those endpoints require authentication, running either script unmodified will fail on those specific checks.

**This is expected and correct, not a defect.** Per the approved KB-011 guardrails, neither script was modified — they remain frozen historical records of pre-KB-011 (KB-008-era) behavior. `scripts/kb011_validate_protected_apis.sh` is the current must-pass validation gate for these 7 endpoints going forward.

## Rollback plan

If a rollback is ever needed:

- **Git rollback:** `git checkout kb010-auth-rbac-phase1-validated -- backend-api/app/main.py` (or revert the branch entirely), then rebuild and restart only the `backend-api` container: `docker compose build backend-api && docker compose up -d backend-api`. This restores the pre-KB-011 (KB-010) behavior, where `/admin/*` and `/customer/*` were unauthenticated.
- **Full VM rollback:** restore the Proxmox snapshot `baseline-auth-rbac-phase1`, which was taken at the same validated state as the `kb010-auth-rbac-phase1-validated` tag.
- No destructive database migration was introduced by KB-011 (only additive fixture rows for tenant `DEMO2` and 3 new users), so there is nothing at the schema level to roll back.

## Final validation result

`KB-011 PROTECTED APIS VALIDATION PASSED`
