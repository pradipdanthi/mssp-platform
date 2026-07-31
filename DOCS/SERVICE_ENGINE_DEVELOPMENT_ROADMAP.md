# Service Engine Development Roadmap

Status: Living tracker for backend engines behind the 10-card Service Catalog.  
Created: 2026-07-31 · **Phase 3 Cloud & Identity (ITDR) — COMPLETE**

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
| 10 | Cloud & Identity Protection (ITDR) | `cloud_identity_protection` | MSSP Cloud Identity Protection Engine (M365/Entra) | **PHASE 3 — COMPLETE** |

---

## Phase tracker

### Phase 1 — Continuous Compliance & Hardening (CaaS) — COMPLETE (2026-07-31)

SCA sync, customer `/compliance`, catalog Card 5 ACTIVE binding.

### Phase 2 — External Attack Surface Management (EASM) — COMPLETE (2026-07-31)

Perimeter discovery, customer `/easm`, catalog Card 9 ACTIVE binding.

### Phase 3 — Cloud & Identity Threat Protection (ITDR) — COMPLETE (2026-07-31)

**Delivered:**
- Schema: `postgres/init/024_cloud_itdr_identity.sql` — `tenant_cloud_identity_configs`, `tenant_cloud_identity_events`, `tenant_entitlements.cloud_identity_protection_enabled`
- Service: `backend-api/app/services/itdr_service.py` — connect M365/Entra domain + identity-rule analysis adapter (impossible travel, MFA bypass, rogue admin, external forwarding, suspicious login). Customer label: **MSSP Cloud Identity Protection Engine**. Live Graph OAuth can replace the analysis adapter later without API changes.
- APIs:
  - `GET /customer/itdr/{short_code}/summary`
  - `GET /customer/itdr/{short_code}/events`
  - `GET /customer/itdr/{short_code}/configs`
  - `POST /customer/itdr/{short_code}/connect`
  - `POST /admin/itdr/{tenant_ref}/sync`
  - `GET /admin/itdr/summary`
- Customer UI: `/itdr` — posture gauge, KPI cards, events + remediation, Connect Microsoft 365 modal
- Catalog Card 10 → `ACTIVE` when identity tenant connected / entitlement enabled
- Customer APIs omit `source_ip` and `raw_details`
- Phase 1 SCA + Phase 2 EASM paths untouched

### Phase 4+ (next)

| Phase | Service | Notes |
|---|---|---|
| 4 | NDR completion | Zeek metadata + customer-safe NDR summary |
| 5 | Threat Intelligence | MISP IOC enrichment into alerts |
| 6 | Endpoint Forensics & Deception | Velociraptor + canary tripwires |
| Later | ITDR live Graph | OAuth app registration + real Entra audit/sign-in pull |
| Later | EASM deep scan | Optional Amass/Nuclei template jobs on VM 109 |

---

## Dependencies by phase

- **Phase 1:** Wazuh Manager API; agent ↔ tenant mapping.
- **Phase 2:** Outbound DNS/TLS/TCP to customer-approved public targets.
- **Phase 3:** Customer-approved M365/Entra tenant domain registration; analysis adapter until Graph credentials are configured.
- **Later phases:** Do not install new VMs/tools unless a named KB approves it.
