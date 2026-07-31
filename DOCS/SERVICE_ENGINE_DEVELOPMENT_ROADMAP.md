# Service Engine Development Roadmap

Status: Living tracker for backend engines behind the 10-card Service Catalog.  
Created: 2026-07-31 · **Phase 5 Network Detection & Response (NDR) — COMPLETE**

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
| 7 | Threat Intelligence & Enrichment | `threat_intelligence` | MISP (pending) + enrichment workers | **PLANNED** |
| 8 | Endpoint Forensics & Deception | `endpoint_forensics_deception` | Velociraptor + Canarytokens (pending) | **PLANNED** |
| 9 | External Attack Surface (EASM) | `external_attack_surface` | MSSP External Surface Scanner | **PHASE 2 — COMPLETE** |
| 10 | Cloud & Identity Protection (ITDR) | `cloud_identity_protection` | MSSP Cloud Identity Protection Engine | **PHASE 3 — COMPLETE** |

---

## Phase tracker

### Phases 1–4 — COMPLETE
CaaS, EASM, ITDR, VMaaS (see prior commits).

### Phase 5 — Network Detection & Response (NDR) — COMPLETE (2026-07-31)

**Delivered:**
- Schema: `postgres/init/026_network_detection_response_ndr.sql` — `tenant_ndr_sensors`, `tenant_ndr_events`
- Service: `backend-api/app/services/ndr_service.py` — imports network-tagged `security_alerts` when present; otherwise analysis-adapter samples (lateral movement, C2, DNS tunneling, TLS risk, port scan, exploit attempt). Customer label: **MSSP Network Detection & Response Engine**.
- APIs:
  - `GET /customer/ndr/{short_code}/summary`
  - `GET /customer/ndr/{short_code}/events`
  - `GET /customer/ndr/{short_code}/sensors`
  - `POST /admin/ndr/{tenant_ref}/sync`
  - `GET /admin/ndr/summary`
- Customer UI: `/ndr` (+ `/network`) — KPI cards, events table with ATT&CK + containment guidance, Sensor status & coverage tab
- Customer APIs omit raw `source_ip` / `destination_ip` / `raw_details` (endpoint labels instead)
- Catalog Card 6 → `ACTIVE` when NDR data / `zeek_enabled` entitlement present
- Phases 1–4 regression paths untouched

### Phase 6+ (next)

| Phase | Service | Notes |
|---|---|---|
| 6 | Threat Intelligence | MISP IOC enrichment |
| 7 | Endpoint Forensics & Deception | Velociraptor + canaries |
| Later | Live Zeek install | Named KB required; deepen metadata pull |

---

## Dependencies by phase

- **Phase 5:** Suricata already on VM 106; Zeek still pending a named KB. Customer dashboard works via alert import + analysis adapter until Zeek is online.
- **Later phases:** Do not install new VMs/tools unless a named KB approves it.
