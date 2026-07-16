# KB-058 — On-Prem Appliance Template and Registration

Status: Implemented (pending validation/commit).  
Module type: Safe deployment template and admin download API/UI.

## Purpose

KB-058 provides a placeholder-only starting bundle for an on-prem appliance and
makes it downloadable from the admin Appliances page.

The bundle contains:

- `templates/on-prem-appliance/README.md`
- `templates/on-prem-appliance/docker-compose.yml.template`

It does not deploy a SOC engine, create a VM, contain an image credential, or
modify the control-plane `docker-compose.yml`.

## Registration workflow

1. A `platform_admin` creates a one-time tenant activation token.
2. An operator downloads the on-prem template bundle.
3. The operator replaces every angle-bracket placeholder locally.
4. The appliance calls the existing KB-016 `POST /appliance/register`.
5. The returned durable API key is stored in the appliance's local secret store.
6. The registered appliance uses its ID/key headers for heartbeat and KB-057
   normalized alert ingestion.

Neither the one-time activation token nor durable API key belongs in Git, the
template bundle, logs, browser storage, or the customer portal.

## Admin API and RBAC

`GET /admin/appliances/on-prem-template`

- Allowed: `platform_admin`, `soc_manager`
- Denied: `soc_analyst`, `customer_admin`, `customer_viewer`
- Authentication: existing human JWT/RBAC dependency
- Response: bundle name/version, `contains_secrets = false`, and the two files'
  path, media type, and text

The route embeds the same safe template text that ships under `templates/`.
This keeps the endpoint available in the current backend image, whose build
context copies only `backend-api/app`.

## Admin frontend

`frontend-admin/src/pages/AppliancesPage.tsx` adds a
**Download on-prem template** button in the Activation Tokens area for
`platform_admin` and `soc_manager`. It downloads one JSON bundle containing
both file texts and their metadata. The JSON contains placeholders only.

## Safety boundaries

- No real secrets or customer data.
- No `.env`, schema, migration, or runtime Compose changes.
- No customer frontend changes.
- No `/admin` call from the customer portal.
- Raw events, IP addresses, packet captures, credentials, and internal notes
  stay outside customer-safe synchronization.

## Files

- `templates/on-prem-appliance/README.md`
- `templates/on-prem-appliance/docker-compose.yml.template`
- `backend-api/app/api/routes/on_prem_template.py`
- `backend-api/app/main.py`
- `frontend-admin/src/api/appliances.ts`
- `frontend-admin/src/pages/AppliancesPage.tsx`
- `scripts/kb058_validate_on_prem_appliance_template_registration.sh`
- `docs/KB058_ON_PREM_APPLIANCE_TEMPLATE_REGISTRATION.md`

## Validation

```bash
cd /opt/mssp-control
./scripts/kb058_validate_on_prem_appliance_template_registration.sh
```

Expected final line:

```text
KB-058 ON-PREM APPLIANCE TEMPLATE REGISTRATION VALIDATION PASSED
```
