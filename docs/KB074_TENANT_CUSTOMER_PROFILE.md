# KB-074 — Tenant Customer Profile Fields

Status: Implemented on control plane (VM 100).

## Goal

Expand Admin → Customers Add/Edit forms with standard organization profile fields used during MSSP onboarding.

## Fields added on `tenants`

**Required on create:** `primary_contact_name`, `primary_contact_email`, `country`

**Optional:** `primary_contact_phone`, secondary contact name/email/phone, `billing_email`, `address_line1`, `address_line2`, `city`, `state_region`, `postal_code`, `website`, `industry`

## Apply / validate

```bash
cd /opt/mssp-control
./scripts/kb074_create_tenant_customer_profile.sh
docker compose up -d --build backend-api frontend-admin
./scripts/kb074_validate_tenant_customer_profile.sh
```

## Notes

- Existing tenants keep null profile fields until edited.
- Customer portal users remain separate (Users → Add User after tenant create).
- `tenant_contacts` table still exists for future multi-contact workflows; this module stores the primary profile on `tenants` for the onboarding form.
