# Service Engine Development Roadmap

Status: Living tracker for backend engines behind the 10-card Service Catalog.  
Created: 2026-07-31 · **Phase 2 External Attack Surface (EASM) — COMPLETE**

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
| 9 | External Attack Surface (EASM) | `external_attack_surface` | MSSP External Surface Scanner (+ future Amass/Nuclei on VM 109) | **PHASE 2 — COMPLETE** |
| 10 | Cloud & Identity Protection (ITDR) | `cloud_identity_protection` | M365 / Entra ID connectors (pending) | **PLANNED** |

---

## Phase tracker

### Phase 1 — Continuous Compliance & Hardening (CaaS) — COMPLETE (2026-07-31)

**Delivered:** SCA sync, customer `/compliance`, catalog Card 5 ACTIVE binding. See prior section history in git.

### Phase 2 — External Attack Surface Management (EASM) — COMPLETE (2026-07-31)

**Delivered:**
- Schema: `postgres/init/023_easm_attack_surface.sql` — `tenant_easm_assets`, `tenant_easm_scans`, `tenant_easm_findings`, `tenant_entitlements.external_attack_surface_enabled`
- Service: `backend-api/app/services/easm_service.py` — domain registration + lightweight perimeter discovery (DNS common-name enum, TLS, open ports, HTTP hardening). Customer label: **MSSP External Surface Scanner**. No Amass/Nuclei binaries on the control plane (VM 109 deep templates remain future extension).
- APIs:
  - `GET /customer/easm/{short_code}/summary`
  - `GET /customer/easm/{short_code}/assets`
  - `GET /customer/easm/{short_code}/findings`
  - `POST /customer/easm/{short_code}/domains`
  - `POST /admin/easm/{tenant_ref}/scan` (UUID or short_code)
  - `GET /admin/easm/summary`
- Customer UI: `/easm` — KPI cards, asset table, findings + remediation, Register New Domain modal
- Catalog Card 9 → `ACTIVE` when domains registered / entitlement enabled
- Phase 1 SCA paths untouched

### Phase 3+ (next)

| Phase | Service | Notes |
|---|---|---|
| 3 | NDR completion | Zeek metadata + customer-safe NDR summary |
| 4 | Threat Intelligence | MISP IOC enrichment into alerts |
| 5 | Endpoint Forensics & Deception | Velociraptor + canary tripwires |
| 6 | ITDR | M365/Entra connectors + Impossible Travel rules |
| Later | EASM deep scan | Optional Amass/Nuclei template jobs on VM 109 pushing into EASM tables |

---

## Dependencies by phase

- **Phase 1:** Wazuh Manager API; agent ↔ tenant mapping.
- **Phase 2:** Outbound DNS/TLS/TCP from control plane to customer-approved public targets only; no new VM installs.
- **Later phases:** Do not install new VMs/tools unless a named KB approves it.
