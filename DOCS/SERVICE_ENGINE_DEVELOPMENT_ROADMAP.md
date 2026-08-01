# Service Engine Development Roadmap

Status: Living tracker for backend engines behind the 10-card Service Catalog.  
Created: 2026-07-31 · **Updated 2026-08-01 — VM 110 Velociraptor LIVE + VM 109 Amass EASM LIVE**

**Conventions (this repo):**
- Customer APIs: `/customer/{feature}/{short_code}/...` (nginx strips `/api` prefix).
- Admin APIs: `/admin/{feature}/...`
- Customer UI: capability labels only — **no** third-party engine brand names in `frontend-customer/`.
- Engines live on VMs 101–110; control plane (VM 100) is adapter-only.

---

## Catalog map (10 offerings)

| # | Catalog card | `service_key` | Backend engines (adapters) | Status |
|---|---|---|---|---|
| 1 | Log & Event Monitoring | `log_event_monitoring` | Wazuh Manager ingest → `security_alerts` | **LIVE** (core) |
| 2 | Incident Response & Casework | `incident_response` | TheHive/Shuffle adapters → `incidents` | **LIVE** (core) |
| 3 | Security Automation & Containment | `security_automation` | Wazuh Active Response / EDR isolate + durable Shuffle queue | **LIVE** (core) |
| 4 | Vulnerability Management (VMaaS) | `vulnerability_management` | MSSP Internal Vulnerability Scanner (+ Nuclei/Vuls/Greenbone ingest) | **PHASE 4 — COMPLETE** |
| 5 | Continuous Compliance & Hardening (CaaS) | `continuous_compliance` | Wazuh SCA policies/checks | **PHASE 1 — COMPLETE** |
| 6 | Network Detection & Response (NDR) | `network_detection_response` | MSSP Network Detection & Response Engine (Suricata + Zeek adapters) | **PHASE 5 — COMPLETE** |
| 7 | Threat Intelligence & Enrichment | `threat_intelligence` | MSSP Global Threat Intelligence Engine (MISP/OTX/AbuseIPDB adapters) | **PHASE 6 — COMPLETE** (MISP VM still pending) |
| 8 | Endpoint Forensics & Deception | `endpoint_forensics_deception` | **VM 110 Velociraptor** bridge `:8001` + EDR artifact bridge | **LIVE (VM 110)** |
| 9 | External Attack Surface (EASM) | `external_attack_surface` | **VM 109 Amass + Nuclei** agent → `/integrations/easm/*` | **LIVE (VM 109 deep recon)** |
| 10 | Cloud & Identity Protection (ITDR) | `cloud_identity_protection` | MSSP Cloud Identity Protection Engine | **PHASE 3 — COMPLETE** |

---

## Phase tracker

### Phases 1–6 — COMPLETE
CaaS, EASM (stdlib MVP), ITDR, VMaaS, NDR, Threat Intelligence (see prior commits).

### Phase 7 — Endpoint Forensics & Deception — LIVE on VM 110 (2026-08-01)

**Delivered:**
- Proxmox VM 110 `velociraptor` @ `192.168.0.220`
- Ansible role `ansible/roles/velociraptor/` + direct install scripts `scripts/kb110_*`
- Bridge HTTP API on `:8001` (`mssp_velociraptor_bridge.py`)
- Control plane `velociraptor_client.py`; `COLLECT_FORENSICS` prefers VM 110
- Customer-safe forensics metadata only on `:3001`

### Deep EASM on VM 109 — LIVE (2026-08-01)

- Ansible role `ansible/roles/easm_recon_stack/`
- Agent `/opt/mssp-easm-agent` (Amass + optional Nuclei) → scan-plan/sync APIs
- Default `EASM_DISPATCH_MODE=remote` (stdlib local probes only if mode=local/hybrid)

### Later (optional deepen)

| Item | Notes |
|---|---|
| Live canary/deception sensors | Named KB; replace seeded tripwires with real sensor ingest |
| Live MISP install (VM 108) | Named KB; deepen Phase 6 IOC pull |
| Velociraptor endpoint clients | Enroll Windows/Linux lab agents for full host VQL collections |

---

## Dependencies by phase

- **Phase 7:** Live bridge on VM 110; enroll Velociraptor clients for deeper host collections.
- **Later phases:** Do not install new VMs/tools unless a named KB approves it.
