# Service Engine Development Roadmap

Status: Living tracker for backend engines behind the 10-card Service Catalog.  
Created: 2026-07-31 · **Updated 2026-08-04 — KB-094 Customer Boundary Hardening**

**Conventions (this repo):**
- Customer APIs: `/customer/{feature}/{short_code}/...` (nginx strips `/api` prefix).
- Admin APIs: `/admin/{feature}/...`
- Customer UI: capability labels only — **no** third-party engine brand names in `frontend-customer/`.
- Engines live on VMs 101–110; control plane (VM 100) is adapter-only.

---

## Catalog map (10 offerings)

| # | Catalog card | `service_key` | Backend engines (adapters) | Status |
|---|---|---|---|---|
| 1 | Log & Event Monitoring | `log_event_monitoring` | Wazuh Manager ingest → `security_alerts` + **Junexis Data Lake** (local/cloud Parquet retention) | **LIVE** (core) |
| 2 | Incident Response & Casework | `incident_response` | TheHive/Shuffle adapters → `incidents` + **AI Executive Summary** on customer incident detail | **LIVE** (core) |
| 3 | Security Automation & Containment | `security_automation` | Wazuh Active Response / EDR isolate + durable Shuffle queue | **LIVE** (core) |
| 4 | Vulnerability Management (VMaaS) | `vulnerability_management` | MSSP Internal Vulnerability Scanner (+ Nuclei/Vuls/Greenbone ingest) | **PHASE 4 — COMPLETE** |
| 5 | Continuous Compliance & Hardening (CaaS) | `continuous_compliance` | Wazuh SCA policies/checks | **PHASE 1 — COMPLETE** |
| 6 | Network Detection & Response (NDR) | `network_detection_response` | MSSP Network Detection & Response Engine (Suricata + Zeek adapters) | **PHASE 5 — COMPLETE** |
| 7 | Threat Intelligence & Enrichment | `threat_intelligence` | Global Threat Intel Engine + **STIX 2.1 / TAXII** + **90-day Junexis Retrospective Engine** | **PHASE 6 — COMPLETE** (+ STIX/Retro 2026-08-04) |
| 8 | Endpoint Forensics & Deception | `endpoint_forensics_deception` | **VM 110 Velociraptor** + **Junexis ThreatLens** (IOC extraction / advisory analysis) | **LIVE (VM 110)** + ThreatLens |
| 9 | External Attack Surface (EASM) | `external_attack_surface` | **VM 109 Amass + Nuclei** agent → `/integrations/easm/*` | **LIVE (VM 109 deep recon)** |
| 10 | Cloud & Identity Protection (ITDR) | `cloud_identity_protection` | MSSP Cloud Identity Protection Engine | **PHASE 3 — COMPLETE** |

---

## Phase tracker

### KB-095: Threat Intel Admin Ops + Catalog Label Sync — 2026-08-04

Closes remaining Anomali-style Threat Intelligence / ThreatLens gaps.

**Delivered:**
- Admin **Threat Intel** console (`:3000/threat-intel`): cross-tenant IOC/campaign summary, tenant detail, Sync, **STIX 2.1 paste ingest**, **TAXII 2.x pull** (form or `JUNEXIS_TAXII_*` env feed).
- Backend: `GET/POST /admin/threat-intel/{tenant_ref}/…` detail/iocs/campaigns/taxii-pull; static `/admin/threat-intel/summary` registered before path params.
- Customer Detection Stack panel now uses the same 10 catalog names/descriptions as Service Portfolio.
- Admin Subscription / Create Customer entitlement labels already aligned to Service Catalog (prior fix in this session).

**Env (optional TAXII defaults — never commit secrets):**
- `JUNEXIS_TAXII_API_ROOT`
- `JUNEXIS_TAXII_COLLECTION_ID`
- `JUNEXIS_TAXII_USERNAME`
- `JUNEXIS_TAXII_PASSWORD`

### KB-094: Customer Boundary Hardening — 2026-08-04

Hardens the 3 Golden Rules of MSSP separation between `:3001` (customer) and `:3000` (admin/SOC).

**Delivered:**
- **API leak fix:** `_customer_safe_incident_row()` is now an explicit whitelist (no `dict(row)` copy). Dashboard + incident list SQL no longer select `sa.raw_event`. Engine ids remapped via `customer_safe_alert_source()`.
- **Customer audit scrub:** customer audit responses drop `source_ip` and nested detail blobs; UI shows localized action labels (no raw JSON `<pre>` dumps).
- **Executive UI:** Incident detail leads with `AiExecutiveSummary` (“Action Taken by Junexis SOC”); EDR process tree is a **collapsed-by-default** accordion titled “Technical Forensic Details (EDR Execution Tree)”.
- **Copy hygiene:** Sysmon empty-state → “Junexis Endpoint Telemetry”.
- **Dead code removed:** unused admin-flavored `IncidentDetailPanel` / `IncidentDrawer` purged from `frontend-customer`.

**Verify:**
```bash
# After rebuild — no raw_event in customer incident list JSON
curl -fsS -H "Authorization: Bearer $TOKEN" \
  "http://127.0.0.1:8000/customer/incidents/ALPHAWINCORP-6VS2?page=1&page_size=5" \
  | jq 'paths | select(.[-1]=="raw_event")'
# expect empty
```

### Phases 1–6 — COMPLETE
CaaS, EASM (stdlib MVP), ITDR, VMaaS, NDR, Threat Intelligence (see prior commits).

### Universal Retrospective + ThreatLens — 2026-08-04

**Delivered (control plane):**
- Schema: `postgres/init/029_threatlens_retrospective.sql` (`retrospective_hunt_jobs`, `tenant_appliances` view, appliance disk/ingest columns). Note: prompt’s `025_*` filename was already VMaaS.
- **Junexis ThreatLens** NLP extract + 90-day sweep APIs (`/customer/threatlens/...` and `/api/v1/customer/threatlens/...`)
- **Junexis Retrospective Engine** dual-route: `LOCAL_APPLIANCE` (Modes 2/4 → appliance hunt API + telemetry callback) vs `CLOUD_SOC` (Modes 1/3 → DuckDB/Parquet under `JUNEXIS_CLOUD_DATALAKE_ROOT`)
- **STIX 2.1 / TAXII** parse + ingest helpers in `threat_intel_service.py` (`stix2`, `taxii2-client`, DuckDB in requirements)
- Customer portal `:3001/threatlens` + AI Executive Summary on incident detail
- Admin `:3000` appliance command tile + `/retrospective-hunts` monitor
- Marketing site copy for Cards 1/7/8 and Mode 1 vs Mode 4 deployments

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
| Redis-backed hunt job queue | Upgrade from BackgroundTasks to durable Redis list (Shuffle pattern) |
| Cloud Parquet writers | Populate `JUNEXIS_CLOUD_DATALAKE_ROOT` for Modes 1/3 cold storage |

---
