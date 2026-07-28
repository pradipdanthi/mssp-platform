# KB-072 — Tenant Engine Provisioning (Wazuh + TheHive)

Status: **Implemented** on control plane (VM 100). Live engine calls require API secrets.

## Goal

When you **Add Customer** in the Admin dashboard, the control plane automatically:

1. Creates a DB binding for that tenant  
2. Creates / ensures a **Wazuh agent group** `tenant_<SHORT_CODE>`  
3. Creates / ensures a **TheHive organisation** `MSSP-<SHORT_CODE>` (or falls back to shared `THEHIVE_DEFAULT_ORG`, default **`MSSP`**, plus tag `tenant:<SHORT_CODE>`)  

Your team does **not** manually create customers inside Wazuh/TheHive for onboarding.

## Operator flow

1. Admin → Customers → **Add Customer**  
2. Note the success message: Wazuh group + TheHive org/tag status  
3. Create customer portal user(s)  
4. Issue appliance activation token  
5. Install agents / appliance and assign them to Wazuh group `tenant_<SHORT_CODE>`  
6. Alerts from that group map to the correct tenant in the control plane  

Actions menu: **Engine binding / provision** · header: **Provision all engines** (backfill).

## Secrets (never commit)

| File | Purpose |
|------|---------|
| `/opt/mssp-control/.secrets/thehive_password` | TheHive admin password (already used by KB-061) |
| `/opt/mssp-control/.secrets/wazuh_api_user` | Wazuh API user (often `wazuh-wui`) |
| `/opt/mssp-control/.secrets/wazuh_api_password` | Wazuh API password from VM 101 install archive |

Populate Wazuh secrets from VM 101 root-only install files (do not paste into chat/Git):

```bash
# On a host that can read VM 101 install credentials (root on 192.168.0.211):
# Extract API user/password into the two files above (mode 600), then:
cd /opt/mssp-control
docker compose up -d backend-api
```

Then in Admin: **Provision all engines** (or per-tenant Retry).

## API

- `POST /admin/tenants` — create + auto-provision  
- `GET /admin/tenants/{id}/engine-binding`  
- `POST /admin/tenants/{id}/engine-provision`  
- `POST /admin/tenants/engine-provision/backfill`  

## Status values

`pending` · `provisioned` · `tag_only` (TheHive shared org) · `error` · `skipped`

Tenant create **always succeeds** even if engines are down; binding shows `pending`/`error` for retry.

## Validation

```bash
cd /opt/mssp-control
./scripts/kb072_validate_tenant_engine_provisioning.sh
```
