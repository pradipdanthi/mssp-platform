# KB-085 — Lab Reset, Customer Users, Audit Trail, Dual-Tenant Provisioning

Date: 2026-07-28

## Summary

1. **Purge** lab/test operational data while keeping schema + platform SOC staff.
2. **Onboarding** already creates tenant + first `customer_admin` (`portal_admin`); alias `POST /v1/admin/customers`.
3. **Admin Users tab** lists MSSP staff only; customer users under Customers → Users.
4. **Customer portal** Users + Audit pages with tenant-isolated APIs.
5. **Audit logs** enriched (`actor_email`, `actor_role`, `action_status`, `resource_*`) and wired for auth/EDR/onboard/user mgmt.
6. **Lab tenants** Alpha-Win-Corp (`ALPHAWIN`) + Beta-Linux-Corp (`BETALINUX`).
7. **Network appliance** taxonomy: `device_type=network_appliance` for firewall/syslog ingest without endpoint agent IDs.

## Commands

```bash
# Migration + purge + provision lab tenants
chmod +x scripts/kb085_purge_and_provision_lab.sh scripts/purge_test_data.py
./scripts/kb085_purge_and_provision_lab.sh

# Validate
./scripts/kb085_validate_lab_reset_rbac_audit.sh
```

## Lab credentials (temporary)

| Portal | Email | Password |
|--------|-------|----------|
| Admin | platform.admin@example.local | TempPass123! (reset by provision script) |
| Alpha | admin@alphawin.com | TempPass123! |
| Beta | admin@betalinux.com | TempPass123! |

Change these after first login in production.

## Agent mapping

- Agent `003` → Wazuh group `tenant_ALPHAWIN` (Windows)
- Agent `001` → Wazuh group `tenant_BETALINUX` (Linux)

## Network appliance prep

Set `source_tool` to `network_appliance` (or use FortiGate/pfSense/VyOS decoder names) on ingest so taxonomy maps to `security_edge_appliances` / `network_appliance` without requiring an endpoint `agent.id`.
