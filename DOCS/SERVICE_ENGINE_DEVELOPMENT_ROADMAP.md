# Service Engine Development Roadmap

Status: Living tracker for backend engines behind the 10-card Service Catalog.  
Created: 2026-07-31 · **Phase 7 Endpoint Forensics & Deception — COMPLETE (control-plane)**

**Conventions (this repo):**
- Customer APIs: `/customer/{feature}/{short_code}/...` (nginx strips `/api` prefix).
- Admin APIs: `/admin/{feature}/...`
- Customer UI: capability labels only — **no** third-party engine brand names in `frontend-customer/`.
- Engines live on VMs 101–109 (+ future DFIR VM); control plane (VM 100) is adapter-only.

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
| 8 | Endpoint Forensics & Deception | `endpoint_forensics_deception` | MSSP Endpoint Forensics & Deception Engine (Velociraptor/canary adapters pending live install) | **PHASE 7 — COMPLETE** |
| 9 | External Attack Surface (EASM) | `external_attack_surface` | MSSP External Surface Scanner | **PHASE 2 — COMPLETE** |
| 10 | Cloud & Identity Protection (ITDR) | `cloud_identity_protection` | MSSP Cloud Identity Protection Engine | **PHASE 3 — COMPLETE** |

---

## Phase tracker

### Phases 1–6 — COMPLETE
CaaS, EASM, ITDR, VMaaS, NDR, Threat Intelligence (see prior commits).

### Phase 7 — Endpoint Forensics & Deception — COMPLETE (2026-08-01)

**Delivered (control plane; no new DFIR VM installed):**
- Schema: `postgres/init/028_endpoint_forensics_deception.sql` — `tenant_deception_tripwires`, `tenant_deception_events`, `tenant_forensics_collections`
- Service: `backend-api/app/services/endpoint_forensics_service.py` — seeds tripwires/events/collections; optional bridge from `edr_forensic_artifacts`. Customer label: **MSSP Endpoint Forensics & Deception Engine**.
- APIs:
  - `GET /customer/forensics/{short_code}/summary`
  - `GET /customer/forensics/{short_code}/tripwires`
  - `GET /customer/forensics/{short_code}/events`
  - `GET /customer/forensics/{short_code}/collections`
  - `POST /admin/forensics/{tenant_ref}/sync`
  - `GET /admin/forensics/summary`
- Customer UI: `/forensics` — KPIs + events / tripwires / collections tabs
- Catalog Card 8 → `ACTIVE` when forensics data / `velociraptor_enabled` entitlement present
- Customer APIs omit vendor brand names (Velociraptor / Canarytokens)
- Existing KB-083/084 EDR forensics pipeline remains for incident-response deep dives

### Later (optional deepen)

| Item | Notes |
|---|---|
| Live Velociraptor VM | Named KB required before install |
| Live canary/deception deployment | Named KB; wire trip events from real sensors |
| Live MISP install | Named KB; deepen Phase 6 IOC pull |

---

## Dependencies by phase

- **Phase 7:** Dashboard works via analysis adapter + optional EDR artifact bridge until Velociraptor/canaries are online.
- **Later phases:** Do not install new VMs/tools unless a named KB approves it.
