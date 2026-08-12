# KB-073 — Tenant Deployment Mode (Customer Onboarding)

Status: Implemented on control plane (VM 100). Extended in KB-073b for cloud + appliance.

## Goal

When onboarding a customer in Admin → Customers, choose how that tenant connects to the MSSP:

| Mode | Meaning |
|------|---------|
| `cloud` | **Cloud without appliance** — AWS / Azure / GCP / Other; agents feed MSSP cloud SOC directly |
| `cloud_appliance` | **Cloud with appliance** — cloud workloads **plus** edge/onsite appliance forwarding allowed metadata |
| `on_prem_direct` | **On-prem without appliance** — agents talk to MSSP cloud (no edge box) |
| `on_prem_appliance` | **On-prem with appliance** — edge appliance; only safe metadata to cloud |
| `hybrid` | Mix of cloud path and on-prem appliance under one customer |

`cloud_provider`: `aws` | `azure` | `gcp` | `other`  
Required for `cloud` and `cloud_appliance`; optional for `hybrid`.

## Appliance alert path (metadata only)

For `on_prem_appliance` / `cloud_appliance` / `hybrid`, agents report to the **local appliance Manager**.  
High/critical metadata is forwarded to the control plane over the secure channel — see **KB-093P**.

## What changed

- DB: `tenants.deployment_mode`, `tenants.cloud_provider` (`008_kb073_*.sql`)
- DB: allow `cloud_appliance` (`009_kb073b_cloud_appliance_mode.sql`)
- API: create / update / detail / list include the fields
- Admin UI: Add/Edit Customer dropdowns + list badge + filter chips (one Customers page)

## Apply / validate

```bash
cd /opt/mssp-control
./scripts/kb073_create_tenant_deployment_mode.sh
docker compose exec -T postgres psql -v ON_ERROR_STOP=1 -U mssp_admin -d mssp_control \
  < postgres/init/009_kb073b_cloud_appliance_mode.sql
docker compose up -d --build backend-api frontend-admin
./scripts/kb073_validate_tenant_deployment_mode.sh
```

## Notes

- Existing tenants default to `cloud` (without appliance) with `cloud_provider` null — edit to set provider / switch mode.
- Selecting any `*_appliance` or `hybrid` mode prompts activation-token next step after create.
