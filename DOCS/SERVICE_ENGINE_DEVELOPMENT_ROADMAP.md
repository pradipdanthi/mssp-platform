# Service Engine Development Roadmap

Status: Living tracker for backend engines behind the 10-card Service Catalog.  
Created: 2026-07-31 · **Phase 1 Continuous Compliance (CaaS) — COMPLETE**

**Conventions (this repo):**
- Customer APIs: `/customer/{feature}/{short_code}/...` (nginx strips `/api` prefix).
- Admin APIs: `/admin/{feature}/...`
- Customer UI: capability labels only — **no** third-party engine brand names in `frontend-customer/`.
- Engines live on VMs 101–109; control plane (VM 100) is adapter-only.

---

## Catalog map (10 offerings)

| # | Catalog card | `service_key` | Backend engines (adapters) | Status |
|---|---|---|---|---|
| 1 | Log & Event Monitoring | `log_event_monitoring` | Wazuh Manager ingest → `security_alerts` | **LIVE** (core) |
| 2 | Incident Response & Casework | `incident_response` | TheHive/Shuffle adapters → `incidents` | **LIVE** (core) |
| 3 | Security Automation & Containment | `security_automation` | Wazuh Active Response / EDR isolate | **LIVE** (core) |
| 4 | Vulnerability Management (VMaaS) | `vulnerability_management` | Nuclei + Vuls + Greenbone CE (VM 109) | **LIVE** |
| 5 | Continuous Compliance & Hardening (CaaS) | `continuous_compliance` | Wazuh SCA policies/checks | **PHASE 1 — COMPLETE** |
| 6 | Network Detection & Response (NDR) | `network_detection_response` | Suricata (VM 106) + Zeek (pending) | **PARTIAL** (Suricata live; Zeek pending) |
| 7 | Threat Intelligence & Enrichment | `threat_intelligence` | MISP (pending) + enrichment workers | **PLANNED** |
| 8 | Endpoint Forensics & Deception | `endpoint_forensics_deception` | Velociraptor + Canarytokens (pending) | **PLANNED** |
| 9 | External Attack Surface (EASM) | `external_attack_surface` | Amass + Nuclei (VM 109 extend) | **PLANNED** |
| 10 | Cloud & Identity Protection (ITDR) | `cloud_identity_protection` | M365 / Entra ID connectors (pending) | **PLANNED** |

---

## Phase tracker

### Phase 1 — Continuous Compliance & Hardening (CaaS) — COMPLETE (2026-07-31)

**Delivered:**
- Schema: `postgres/init/022_continuous_compliance_sca.sql` — `tenant_compliance_summaries`, `sca_evaluations`, `sca_check_details`, `tenant_entitlements.continuous_compliance_enabled`
- Service: `backend-api/app/services/sca_compliance_service.py`
- Wazuh client helpers: `list_sca_policies`, `list_sca_checks` (alert ingest / AR untouched)
- APIs:
  - `GET /customer/compliance/{short_code}/summary`
  - `GET /customer/compliance/{short_code}/evaluations`
  - `GET /customer/compliance/{short_code}/checks`
  - `GET /customer/compliance/{short_code}/report` (HTML audit pack; print → PDF)
  - `POST /admin/compliance/{short_code}/sync`
  - `GET /admin/compliance/summary`
- Customer UI: `/compliance` — readiness gauge, framework tabs, failed-check table + remediation, download report
- Catalog Card 5 → `ACTIVE` when SCA data present / entitlement enabled
- Smoke (Alpha-Win): sync `ok`, score **27.3%**, 1 policy (CIS Windows Server 2022), 261 failed checks stored

### Phase 2+ (next)

| Phase | Service | Notes |
|---|---|---|
| 2 | NDR completion | Zeek metadata + customer-safe NDR summary |
| 3 | Threat Intelligence | MISP IOC enrichment into alerts |
| 4 | EASM | Scheduled Amass/Nuclei perimeter jobs on VM 109 |
| 5 | Endpoint Forensics & Deception | Velociraptor + canary tripwires |
| 6 | ITDR | M365/Entra connectors + Impossible Travel rules |

---

## Dependencies by phase

- **Phase 1:** Wazuh Manager API credentials already on control plane; agents with SCA policies enabled; tenant ↔ agent via `protected_assets.details.wazuh_agent_id` / engine bindings.
- **Later phases:** Do not install new VMs/tools unless a named KB approves it.
