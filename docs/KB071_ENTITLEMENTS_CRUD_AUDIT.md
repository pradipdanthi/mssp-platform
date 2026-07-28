# KB-071 — Tenant Entitlements, Row Actions & Connected Audit

Status: Implemented on control plane (VM 100). Validation:
`./scripts/kb071_validate_entitlements_audit.sh`

## What this delivers

1. **Admin row actions (⋯)** on Customers, Users, and Appliances.
2. **Subscription matrix** per tenant — UI uses **service capability names only**
   (never third-party engine brands in customer/admin subscription copy):
   - SIEM & Log Management
   - Incident Response & Casework
   - Security Automation (SOAR)
   - Vulnerability Management
   - Network Traffic Analysis *(roadmap / building)*
   - Threat Intelligence Sharing *(roadmap / building)*
   - Endpoint Forensics & Hunting *(roadmap / building)*
3. **Customer adaptive UI**: `/vulnerabilities` locks when Vulnerability Management is off.
4. **Connected Audit Log**: actor filter, entity JSON diff, CSV/JSON export.
5. **Dashboard upgrades**: dark high-contrast severity tiles, SOC efficiency strip,
   service stack coverage panel.

Roadmap services can be marked requested now; backends ship when demand / totals justify rollout.

## Apply schema

```bash
cd /opt/mssp-control
./scripts/kb071_create_entitlements.sh
./scripts/kb071b_create_entitlement_roadmap.sh
```
