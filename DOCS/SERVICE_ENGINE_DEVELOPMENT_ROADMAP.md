# Service Engine Development Roadmap

Status: Living tracker for backend engines behind the 10-card Service Catalog.  
Created: 2026-07-31 · **Phase 4 Vulnerability Management (VMaaS) — COMPLETE**

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
| 4 | Vulnerability Management (VMaaS) | `vulnerability_management` | MSSP Internal Vulnerability Scanner (+ Nuclei/Vuls/Greenbone ingest on VM 109) | **PHASE 4 — COMPLETE** |
| 5 | Continuous Compliance & Hardening (CaaS) | `continuous_compliance` | Wazuh SCA policies/checks | **PHASE 1 — COMPLETE** |
| 6 | Network Detection & Response (NDR) | `network_detection_response` | Suricata (VM 106) + Zeek (pending) | **PARTIAL** (Suricata live; Zeek pending) |
| 7 | Threat Intelligence & Enrichment | `threat_intelligence` | MISP (pending) + enrichment workers | **PLANNED** |
| 8 | Endpoint Forensics & Deception | `endpoint_forensics_deception` | Velociraptor + Canarytokens (pending) | **PLANNED** |
| 9 | External Attack Surface (EASM) | `external_attack_surface` | MSSP External Surface Scanner (+ future Amass/Nuclei on VM 109) | **PHASE 2 — COMPLETE** |
| 10 | Cloud & Identity Protection (ITDR) | `cloud_identity_protection` | MSSP Cloud Identity Protection Engine (M365/Entra) | **PHASE 3 — COMPLETE** |

---

## Phase tracker

### Phase 1 — Continuous Compliance (CaaS) — COMPLETE
### Phase 2 — External Attack Surface (EASM) — COMPLETE
### Phase 3 — Cloud & Identity (ITDR) — COMPLETE

### Phase 4 — Vulnerability Management (VMaaS) — COMPLETE (2026-07-31)

**Delivered:**
- Schema: `postgres/init/025_vulnerability_management_vmaas.sql` — `tenant_vulnerability_scans`, `tenant_vulnerability_findings`
- Service: `backend-api/app/services/vmaas_service.py` — imports live `vulnerabilities` rows when present; otherwise analysis-adapter samples. Customer label: **MSSP Internal Vulnerability Scanner**. Existing `/integrations/vuln/*` ingest untouched.
- APIs:
  - `GET /customer/vmaas/{short_code}/summary`
  - `GET /customer/vmaas/{short_code}/findings`
  - `GET /customer/vmaas/{short_code}/scans`
  - `POST /customer/vmaas/{short_code}/scan`
  - `POST /admin/vmaas/{tenant_ref}/sync`
  - `GET /admin/vmaas/summary`
- Customer UI: `/vulnerabilities` (+ `/vulnerability`) — posture gauge, KPI cards, CVE table + remediation, Schedule Internal Scan modal; upgrade form retained when not entitled
- Catalog Card 4 → `ACTIVE` when VMaaS findings / entitlement present
- Phases 1–3 regression: SCA / EASM / ITDR paths untouched

### Phase 5+ (next)

| Phase | Service | Notes |
|---|---|---|
| 5 | NDR completion | Zeek metadata + customer-safe NDR summary |
| 6 | Threat Intelligence | MISP IOC enrichment |
| 7 | Endpoint Forensics & Deception | Velociraptor + canaries |

---

## Dependencies by phase

- **Phase 4:** Prefer live findings from VM 109 sync into `vulnerabilities`; VMaaS tables are the customer dashboard projection. Queues `last_vuln_scan_at = NULL` so the existing scan-plan agent can pick up on-demand runs.
- **Later phases:** Do not install new VMs/tools unless a named KB approves it.
