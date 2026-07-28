# KB-075 — Contract-Ready Customer Onboarding

Status: **Implemented** on control plane (VM 100).

## Goal

When you **Onboard customer** in Admin, **every** new customer (not a special case) is prepared
end-to-end in one form:

1. Organization + contacts + address
2. Commercial / contract fields
3. Contracted service entitlements
4. Backend engine slots (Wazuh group + TheHive org/tag for SIEM/IR)
5. **Required** first customer portal admin login
6. Clear onboard result / next steps (device enrollment comes after)

This is the standard MSSP onboarding path for all tenants going forward.

## Operator flow

1. Admin → Customers → **Add Customer**
2. Fill organization, contacts, address, contract, services, portal admin, deployment
3. Click **Onboard customer**
4. Read success message for engine readiness + portal admin status
5. Enroll devices into the printed Wazuh group (or issue appliance token when mode requires it)

## Schema

`postgres/init/011_kb075_contract_ready_onboarding.sql`

## Apply + validate

```bash
cd /opt/mssp-control
chmod +x scripts/kb075_create_contract_ready_onboarding.sh scripts/kb075_validate_contract_ready_onboarding.sh
./scripts/kb075_create_contract_ready_onboarding.sh
./scripts/kb075_validate_contract_ready_onboarding.sh
```

Then rebuild Admin UI / backend:

```bash
docker compose up -d --build backend-api frontend-admin
```
