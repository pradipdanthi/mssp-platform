# Service Engine Development Roadmap

Status: Living tracker for backend engines behind the 10-card Service Catalog.  
Created: 2026-07-31 · **Phase 6 Threat Intelligence & Enrichment — COMPLETE**

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
| 4 | Vulnerability Management (VMaaS) | `vulnerability_management` | MSSP Internal Vulnerability Scanner (+ Nuclei/Vuls/Greenbone ingest) | **PHASE 4 — COMPLETE** |
| 5 | Continuous Compliance & Hardening (CaaS) | `continuous_compliance` | Wazuh SCA policies/checks | **PHASE 1 — COMPLETE** |
| 6 | Network Detection & Response (NDR) | `network_detection_response` | MSSP Network Detection & Response Engine (Suricata + Zeek adapters) | **PHASE 5 — COMPLETE** |
| 7 | Threat Intelligence & Enrichment | `threat_intelligence` | MSSP Global Threat Intelligence Engine (MISP/OTX/AbuseIPDB adapters) | **PHASE 6 — COMPLETE** |
| 8 | Endpoint Forensics & Deception | `endpoint_forensics_deception` | Velociraptor + Canarytokens (pending) | **PLANNED** |
| 9 | External Attack Surface (EASM) | `external_attack_surface` | MSSP External Surface Scanner | **PHASE 2 — COMPLETE** |
| 10 | Cloud & Identity Protection (ITDR) | `cloud_identity_protection` | MSSP Cloud Identity Protection Engine | **PHASE 3 — COMPLETE** |

---

## Phase tracker

### Phases 1–5 — COMPLETE
CaaS, EASM, ITDR, VMaaS, NDR (see prior commits).

### Phase 6 — Threat Intelligence & Enrichment — COMPLETE (2026-07-31)

**Delivered:**
- Schema: `postgres/init/027_threat_intelligence_enrichment.sql` — `tenant_threat_intel_iocs`, `tenant_threat_intel_campaigns`
- Service: `backend-api/app/services/threat_intel_service.py` — matches alert indicators against curated reputation corpus; seeds campaign bulletins when live feed adapters are offline. Customer label: **MSSP Global Threat Intelligence Engine**.
- APIs:
  - `GET /customer/threat-intel/{short_code}/summary`
  - `GET /customer/threat-intel/{short_code}/iocs`
  - `GET /customer/threat-intel/{short_code}/campaigns`
  - `POST /admin/threat-intel/{tenant_ref}/sync`
  - `GET /admin/threat-intel/summary`
- Customer UI: `/threat-intel` — KPI cards, IOC table (reputation + confidence + actor + ATT&CK), campaign bulletins tab
- Catalog Card 7 → `ACTIVE` when TI data / `misp_enabled` entitlement present
- Customer APIs omit vendor feed brand names (MISP/OTX/AbuseIPDB)
- Phases 1–5 regression paths untouched

### Phase 7+ (next)

| Phase | Service | Notes |
|---|---|---|
| 7 | Endpoint Forensics & Deception | Velociraptor + canaries |
| Later | Live MISP install | Named KB required; deepen live IOC pull |

---

## Dependencies by phase

- **Phase 6:** MISP still pending a named KB. Customer dashboard works via alert-indicator matching + analysis adapter until MISP is online.
- **Later phases:** Do not install new VMs/tools unless a named KB approves it.
