# KB-019 — Admin Activation Token Management UI Completion

**Status:** Validated and ready for commit  
**Branch:** `kb019-admin-activation-token-ui`

## Purpose

Add admin activation-token management UI so SOC/platform operators can issue and revoke appliance onboarding tokens from the branded admin frontend, using the existing KB-015 backend APIs.

## What shipped

Activation-token management lives **inside the existing Appliances page** (no new sidebar route).

| Role | Behavior |
|---|---|
| `platform_admin` | Can create activation tokens and revoke **pending** tokens |
| `soc_manager` / `soc_analyst` | Read-only token list; create/revoke controls hidden |

After create, the **raw activation token is shown exactly once** in React component state, with an explicit copy warning. It is **not** stored in `localStorage`, `sessionStorage`, the URL, or the browser console. List/refresh never re-shows the raw value.

This module also fixed the **broken Kestrel logo** on the login page (invalid SVG content + mark fallback).

## Files modified

- `frontend-admin/public/brand/kestrel-logo.svg`
- `frontend-admin/src/api/appliances.ts`
- `frontend-admin/src/components/BrandMark.tsx`
- `frontend-admin/src/pages/AppliancesPage.tsx`
- `frontend-admin/src/pages/LoginPage.tsx`
- `frontend-admin/src/styles.css`

## Files added

- `scripts/kb019_validate_admin_activation_token_ui.sh`

## Intentionally untouched

- `backend-api/`
- `postgres/init/`
- `.env`
- `docker-compose.yml`
- Database schema, migrations, and seed/demo data

## Validation

Automated result:

```text
KB-019 ADMIN ACTIVATION TOKEN UI VALIDATION PASSED
```

Manual browser checks completed:

- Login logo visible (no broken-image icon)
- Appliances page loads
- Activation Tokens section appears below the appliance list
- Tenant dropdown works and loads that tenant’s tokens
- `platform_admin` can create and revoke; revoked token shows **Revoked**

## Follow-ups (out of scope for KB-019)

- Production Bootstrap and Demo Data Separation
- Customer Dashboard Foundation
- Frontend Dependency Audit and Production Build Hardening
- Reverse Proxy / HTTPS / Production Compose Profile
- Cloud Deployment Preparation
