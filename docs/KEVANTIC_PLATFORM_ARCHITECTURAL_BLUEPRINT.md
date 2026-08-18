# Kevantic Platform Architectural Blueprint

**Document type:** Architectural specification (pre-EDR extension baseline)  
**Audience:** Principal Security Systems Architect / platform owners  
**Date:** 2026-08-18  
**Control plane host:** VM 100 `mssp-control` `192.168.0.201`  
**Repository:** `/opt/mssp-control`  
**Verified against:** live Compose stack, git tags, and source files in this workspace (not stale KB prose alone)

**Purpose:** Freeze how engines, ingest, schemas, and dashboards actually work **today**, so a near-kernel / mid-layer EDR pipeline (eBPF, ETW, Minifilters, Sysmon, auditd) can be added **without** breaking Admin/Customer portals, backend contracts, or existing ingestion.

---

## Document identity and truth order

| Item | Value |
|---|---|
| Product (runtime branding) | Kevantic / Kestrel Cyber MSSP Control Plane |
| System of record | PostgreSQL on VM 100 (`security_alerts`, `incidents`, additive EDR tables) |
| Engines | Backend adapters only — never customer-facing UIs |
| Latest isolate/EDR product tag | `kb104-isolate-standard-golden-validated` |
| Historical UI baseline tag | `kb035-customer-appliance-detail-validated` |
| Related ops bible (narrative, not this spec) | `docs/MSSP_PLATFORM_MASTER_BLUEPRINT.md` |

**Truth order when documents disagree:**

1. Running containers / live VM listeners  
2. Git tags and validator PASS lines  
3. Source in `backend-api/`, `postgres/init/`, `frontend-*/`, `ansible/`, `kevantic-appliance/`  
4. This blueprint  
5. Older KB markdown (several engine-plan KBs are stale vs code)

This document does **not** propose implementing eBPF/ETW/Minifilter collectors. It only maps the current platform and the **safe plug-in surfaces**.

---

## 0. Executive architecture (locked)

```text
Endpoints / sensors / appliances
        │
        ├─ Wazuh agents ──TCP 1514/1515──► Wazuh Manager (VM 101 or local appliance Manager)
        │                                      │
        │                      wazuh-integratord hook (level ≥ 10)
        │                                      ▼
        │                   POST /integrations/soc/hooks/wazuh/{token}
        │                                      │
        │                                      ├─ normalize → PostgreSQL (instant SOC path)
        │                                      └─ async POST Shuffle webhook (TheHive tickets)
        │
        ├─ Appliance local Manager ──tail alerts.json──► POST /api/v1/telemetry/ingest
        │                                      (VM 100)     heartbeat/channel → VM 114
        │
        └─ Vuln / EASM pullers ──API key──► /integrations/vuln/sync , /integrations/easm/...

PostgreSQL ── FastAPI :8000 ── nginx :3000 Admin / :3001 Customer
```

**Hard product rules that EDR work must not violate:**

- Customers never see raw engine JSON, packet captures, credentials, or third-party product names as the *source label* (`customer_safe_labels.py`).  
- Customer portal never calls `/admin`. Browser `/api/*` is stripped by nginx and proxied to FastAPI.  
- Tenant mapping for Wazuh is **fail-closed** (agent group `tenant_<SHORT>` / binding). No DEMO default.  
- Duplicate alert identity is `(tenant_id, source_tool, external_alert_id)`.  
- Control plane does **not** run scanners or SIEM engines.

---

## 1. Backend engine map

### 1.1 Lab / production VM inventory

Source: `ansible/inventory/hosts.yml`, `CONTEXT.md`, `docker-compose.yml`.

| VM | Host / IP | Role | Engine(s) | State in this environment |
|---|---|---|---|---|
| 100 | `mssp-control` `192.168.0.201` | Control plane | FastAPI, Postgres, Redis, Admin/Customer nginx | **Live** (Compose) |
| 101 | `wazuh-stack` `192.168.0.211` | SIEM / EDR agent manager | Wazuh Manager + Indexer + Dashboard + Filebeat 7.10.2 | **Live** 4.14.6 |
| 102 | `thehive_shuffle` `192.168.0.212` | Case + SOAR | TheHive 4.1.24 `:9000`, Shuffle `:3001` | **Live** (co-located; roadmap VM 103 unused) |
| 104 | `windows-endpoint-lab` `192.168.0.214` | Windows agent lab | Wazuh agent + Sysmon/4688 bootstrap | Inventory present |
| 105 | `linux-endpoint-lab` `192.168.0.215` | Linux agent lab | Wazuh agent | **Decommissioned** (CONTEXT: VM destroyed 2026-07-29) |
| 106 | `suricata-sensor` `192.168.0.216` | NDR sensor | Suricata IDS + Zeek (co-located) + Wazuh agent | **Live** (Suricata); Zeek via KB-047 localfile |
| 108 | `misp` `192.168.0.218` | Threat intel | **Lightweight SQLite/HTTP bridge**, not full MISP | Adapter + seeded demo IOCs (`scripts/kb108_install_misp_direct.sh`) |
| 109 | `greenbone` `192.168.0.219` | Vuln + recon | Greenbone CE + Nuclei + Vuls + EASM/Amass | **Live** scanners; Enterprise deferred (KB-077) |
| 110 | `velociraptor` `192.168.0.220` | DFIR | Velociraptor | Client stub `:8001`; **not** a live connected engine |
| 111 | `monitoring` `192.168.0.221` | Observability | Prometheus/Grafana (roadmap) | Placeholder |
| 112 | `automation` `192.168.0.222` | Ansible controller | Playbooks only | Ready |
| 113 | `kevantic-appliance-build` `192.168.0.223` | ISO factory | mkosi | Disposable; `present: false` |
| 114 | `kevantic-appliance-mgmt` `192.168.0.224` | Appliance edge | `main_appliance_mgmt:app` `:8000` | **Live** (KB-093L) |
| 199 | `mssp-appliance-golden-build` `192.168.0.225` | Golden appliance disk | Local Wazuh Manager + Fluent Bit + engines | Clone source |

### 1.2 Control-plane Compose (VM 100) — do not add engines here

Source: `docker-compose.yml`. Observed running 2026-08-18:

| Container | Ports | Notes |
|---|---|---|
| `mssp-postgres` | `127.0.0.1:5432` | Loopback only; VM 114 uses SSH tunnel |
| `mssp-redis` | `127.0.0.1:6379` | Shuffle retry queue + AI queue |
| `mssp-backend-api` | `0.0.0.0:8000` | FastAPI system of record |
| `mssp-frontend-admin` | `0.0.0.0:3000` | nginx static build |
| `mssp-frontend-customer` | `0.0.0.0:3001` | nginx static build |

**Not present on VM 100:** Wazuh, Suricata, Zeek, TheHive, Shuffle, MISP, Greenbone, Nuclei, Vuls, Filebeat, Logstash, Elastic, osquery server, eBPF loaders.

### 1.3 Engine-by-engine wiring

#### Wazuh (primary SIEM + current EDR transport)

| Item | Fact |
|---|---|
| Version | 4.14.6 (`ansible/roles/wazuh_stack/defaults/main.yml`) |
| Host | VM 101 `192.168.0.211` |
| Ports | Agent **1514**, enrollment **1515**, Dashboard **443**, API **55000**, Indexer **9200** |
| Internal shipper | **Filebeat 7.10.2** Manager → Wazuh Indexer only. Not a control-plane ingest path |
| Control-plane client | `backend-api/app/services/wazuh_client.py`; env `WAZUH_API_URL` default `https://192.168.0.211:55000` |
| Tenant binding | KB-072 groups `tenant_<SHORT_CODE>`; fail-closed in `_normalize_wazuh_alert` |
| Rules / decoders | **Not in this git repo.** They live on the Manager (`/var/ossec/ruleset/`, `etc/rules/`, `etc/decoders/`). This repo consumes **already-decoded JSON** |
| Custom rule evidence | KB-063 mentions live custom rule **100049** hitting the instant hook |
| Ansible | `ansible/roles/wazuh_stack`, `wazuh_agent`, `suricata_wazuh`, `zeek_wazuh` |
| Appliance local Manager | `kevantic-appliance/ansible/roles/wazuh_local` (+ Fluent Bit, not Filebeat) |

#### Suricata (network IDS)

| Item | Fact |
|---|---|
| Host | VM 106 `192.168.0.216` |
| Path to SIEM | Wazuh agent `localfile` JSON tail of `/var/log/suricata/eve.json` (`ansible/roles/suricata_wazuh/tasks/main.yml`) |
| Manager | `192.168.0.211:1514` / enroll `1515` |
| Control-plane `source_tool` | `suricata` (taxonomy → `network_ids_sensors`) |
| NDR tables | `tenant_ndr_sensors` / `tenant_ndr_events` import from `security_alerts` when `source_tool IN ('suricata','zeek')` (`ndr_service.py`) |

#### Zeek (NTA)

| Item | Fact |
|---|---|
| Host | **Co-located on VM 106**, not VM 107 |
| Path to SIEM | Wazuh agent `localfile` syslog of `/opt/zeek-logs/current/notice.log` (`ansible/roles/zeek_wazuh/tasks/main.yml`) |
| Ansible default | `zeek_wazuh_execution_mode: preflight` until explicitly applied |
| Control-plane `source_tool` | `zeek` |
| Entitlement flag | `tenant_entitlements.zeek_enabled` |

#### TheHive + Shuffle (case / SOAR)

| Item | Fact |
|---|---|
| Host | VM 102 `192.168.0.212` |
| Ports | TheHive **9000**, Shuffle **3001** (`ansible/roles/case_soar/defaults/main.yml`) |
| Default org | `THEHIVE_DEFAULT_ORG=MSSP` |
| Control-plane ingest | Normalized `POST /integrations/soc/sync` (`X-SOC-Sync-Key`) |
| Dual path | Instant Wazuh hook **also** forwards original JSON to Shuffle (`SHUFFLE_WEBHOOK_URL`) |
| EDR workflows | `shuffle_edr_client.py` posts `{source: mssp-control-plane-edr, forensics_workflow: EDR_COLLECT_FORENSICS}` |
| **Port collision warning** | Shuffle **3001** equals Customer portal **3001** — safe only because they are **different hosts**. Never co-locate Shuffle on VM 100 |

#### Greenbone CE / Nuclei / Vuls (vulnerability)

| Item | Fact |
|---|---|
| Host | VM 109 `192.168.0.219` |
| Greenbone UI | GSA HTTPS **443**, HTTP **9392** (SOC only) |
| Nuclei | 3.11.0 under `/opt/mssp-vuln-free` |
| Ingest | `POST /integrations/vuln/sync` (`X-Vuln-Sync-Key`) |
| Schema | `vulnerabilities.source_platform` ∈ `greenbone` / `nuclei` / `vuls` (not `security_alerts.source_tool`) |
| Customer label | “Vulnerability assessment” |

#### MISP / Velociraptor / osquery

| Engine | Code present | Runtime |
|---|---|---|
| MISP | `misp_client.py`, env `MISP_URL` default `http://192.168.0.218:8080` | **Not the KB-036 MISP platform.** `scripts/kb108_install_misp_direct.sh` deploys a hand-rolled Python server on `:8080` with SQLite and **seeded fake IOCs** (APT29/FIN7 samples). Enterprise gap — needs a named KB before treating as live threat intel |
| Velociraptor | `velociraptor_client.py`; bridge `:8001`, GUI `:8889`, frontend `:8000` | Ansible default `preflight`; EDR forensics still Shuffle until `VELOCIRAPTOR_SERVER_URL` is live |
| osquery | Pack `backend-api/app/endpoint_configs/osquery-endpoint-pack.conf`; process-tree parser understands osquery rows | **Downloadable template only.** Linux agent ZIP (`agent_package_builder._linux_script`) installs `wazuh-agent` and does **not** install osqueryd |

#### Fluent Bit (appliance only)

Appliance golden image uses **Fluent Bit** with local Wazuh Manager (`kevantic-appliance/ansible/roles/wazuh_local`). That is **not** the VM 100 ingest path. Do not introduce Fluent Bit/Filebeat/Logstash onto the control plane for EDR.

#### Not found as live collectors in this repo

- eBPF programs / bpftrace / Cilium Tetragon  
- ETW providers beyond what **Sysmon** already consumes  
- Windows minifilter drivers  
- Elastic SIEM, Logstash, OpenSearch Dashboards on VM 100 (legacy archive under `archive/legacy-docker-stack-export-2026-07-06/` is retired)

### 1.4 How data currently flows between engines

```text
Windows/Linux agent
  Sysmon Operational + Security/4688  (Windows)
  auditd / osquery pack               (Linux, optional)
        → Wazuh agent → Manager
              → Filebeat → Wazuh Indexer (analyst search on :443 — SOC tool, not our product UI)
              → wazuh-integratord → Control plane hook → PostgreSQL
              → Shuffle → TheHive case

Suricata eve.json ─┐
Zeek notice.log ───┴→ same Wazuh agent on VM 106 → same hook → source_tool suricata|zeek

Appliance endpoints → local Manager → critical_alert_watcher
        → privacy.to_cloud_alert() → POST /api/v1/telemetry/ingest
        → security_alerts (customer_visible=true by default)
        Heartbeat/isolate channel → VM 114, not this ingest URL

Nuclei/Vuls/Greenbone → POST /integrations/vuln/sync → vulnerabilities table
        → Admin triage → optional customer_recommendations
```

---

## 2. Log ingestion and data pipelines

### 2.1 There is no Logstash / Filebeat path into the dashboards

| Mechanism | Used? | Where |
|---|---|---|
| Wazuh agent `localfile` tail | **Yes** | Sensors and endpoints → Manager |
| Wazuh `eventchannel` | **Yes** | Windows Sysmon + 4688 (`scripts/bootstrap_windows_telemetry.ps1`) |
| Syslog into Wazuh | **Yes (network appliances)** | KB-085 decoder names; taxonomy `network_appliance` |
| Wazuh integratord HTTP hook | **Yes — primary SOC SLA path** | `POST /integrations/soc/hooks/wazuh/{token}` |
| Normalized SOC sync API | **Yes** | `POST /integrations/soc/sync` |
| Appliance HTTPS ingest | **Yes** | `POST /api/v1/telemetry/ingest` and `POST /appliance/alerts` |
| Filebeat | **Manager→Indexer only** | VM 101; not Postgres |
| Logstash | **No** | — |
| Direct OpenSearch queries from portals | **No** | Portals read PostgreSQL via FastAPI |

### 2.2 Ingest endpoints (FastAPI)

Registered in `backend-api/app/main.py`.

| Path | Auth | Writer | Default customer_visible | Incident prefix |
|---|---|---|---|---|
| `POST /integrations/soc/hooks/wazuh/{token}` | Path token `WAZUH_INGRESS_TOKEN` (wrong token → **404**) | `soc_sync_service.sync_soc_alert` + `edr_ingress.persist_wazuh_alert_enrichment` | **false** until SOC publish | `INC-<SHORT>-TH-####` |
| `POST /integrations/soc/sync` | `X-SOC-Sync-Key` | Same sync service; **no** EDR process persist | false | `INC-<SHORT>-TH-####` |
| `POST /appliance/alerts` | `X-Appliance-ID` + `X-Appliance-API-Key` | Direct INSERT `security_alerts` | **true** | `INC-<SHORT>-APP-####` (high/critical) |
| `POST /api/v1/telemetry/ingest` | Same appliance keys | Delegates to appliance alert ingest | true | APP prefix |
| `POST /api/v1/telemetry/hunt-results` | Appliance keys | Retrospective hunt metadata | n/a | n/a |
| `POST /integrations/vuln/sync` | `X-Vuln-Sync-Key` | `vulnerabilities` | n/a | n/a |
| `POST /v1/edr/actions/callback` | `X-EDR-Callback-Key` or SOC sync key | EDR action lifecycle | n/a | n/a |

**Critical EDR gap (do not ignore):** only the **Wazuh instant hook** calls `persist_wazuh_alert_enrichment()`, which writes `raw_event`, MITRE, host/user, **and** `edr_process_events`. Appliance ingest stores a privacy-scrubbed `raw_event` stub (`privacy.to_cloud_alert` keeps `agent/rule/decoder/data/syscheck`) but **does not** populate `edr_process_events`. Process trees can still be rebuilt from `raw_event` if Sysmon-shaped `data.win.eventdata` survived scrubbing.

### 2.3 Wazuh JSON → control-plane field mapping

Implemented in `backend-api/app/api/routes/soc_sync.py` (`_normalize_wazuh_alert`).

| Wazuh JSON | Control-plane column / field |
|---|---|
| `rule.description` / `title` | `security_alerts.alert_title` |
| `rule.level` | severity: ≥15 critical, ≥10 high, ≥7 medium, else low |
| `rule.id` | carried in description + later `wazuh_rule_id` (derived at read time) |
| `id` / `uuid` / fallback `wazuh-{rule}-{agent}-{level}` | `external_alert_id` |
| `agent.name` | `destination_host` |
| `agent.ip` | `source_ip` and `destination_ip` (agent IP reused) |
| `agent.id` | `wazuh_agent_id` on sync payload; `protected_assets.details->>'wazuh_agent_id'` |
| `agent.groups` / Manager API groups | tenant via `tenant_<SHORT>` |
| `data.win.eventdata.User` etc. | `source_user` |
| `data.win.eventdata.Image/CommandLine/ProcessGuid/...` | EDR process cache |
| wrapped `all_fields` | unwrapped (`unwrap_wazuh_ingress_payload`) |

Level ≥ 10 opens an incident unless `is_known_noise_file_drop` (PowerShell `__psscriptpolicytest_` on Wazuh rule **92213**).

### 2.4 PostgreSQL schemas that power dashboards

Core: `postgres/init/001_mssp_core_schema.sql`.

**`security_alerts` (dashboard system of record)**

| Column | Notes |
|---|---|
| `id` UUID | Admin `alert.id` / customer `alert_id` |
| `tenant_id` | Isolation key |
| `appliance_id`, `asset_id` | Optional links |
| `source_tool` TEXT NOT NULL | Engine discriminator (`wazuh`, `suricata`, `zeek`, `network_appliance`, …) |
| `external_alert_id` | Dedup with tenant + source_tool |
| `severity` | `low\|medium\|high\|critical` |
| `alert_title`, `alert_description` | |
| `event_time` | |
| `source_ip`, `destination_ip`, `source_user`, `destination_host` | |
| `raw_event` JSONB | SOC-only; stripped from customer whitelist |
| `mitre_mapping` JSONB | |
| `ai_*` summaries | Optional LLM (KB-092, default off) |
| `customer_visible` | Customer list/detail filter |
| `status` | `new\|triaged\|incident_created\|false_positive\|closed` |

**`incidents` + `incident_alerts` + `incident_timeline`**

Customer incident URLs use `incident_number`, not UUID (`/incidents/:incidentNumber`).

**EDR additive (do not replace alerts):**

- `014_kb083_edr_actions.sql` — `edr_action_executions`, `edr_endpoint_isolation`, `edr_telemetry_stats`  
- `015_kb084_edr_lifecycle_forensics.sql` — lifecycle statuses, `edr_forensic_artifacts`, **`edr_process_events`**

**`edr_process_events` columns (stable EDR cache):**  
`tenant_id, alert_id, agent_id, pid, parent_pid, process_guid, parent_process_guid, process_name, parent_process_name, command_line, parent_command_line, username, hash_md5, hash_sha256, signed_status, event_time, mitre_techniques, raw_source`

`raw_source` internal values today: `endpoint_process_create` (Sysmon), `endpoint_process_query` (osquery), `endpoint_audit_exec` (auditd).

**Other product tables (not alert ingest):**  
`vulnerabilities` (`source_platform`), `tenant_ndr_*`, `tenant_entitlements`, appliances/heartbeats, recommendations, reports, notifications, audit_logs, EASM/ITDR/compliance/ThreatLens (several of those UIs still have sample/adapter fallbacks).

### 2.5 Pydantic contracts that must stay stable

| Model | File | Constraint |
|---|---|---|
| `SocSyncRequest` | `schemas/soc_sync.py` | `extra="forbid"`; required `tenant_short_code`, `source_tool`, `external_alert_id`, `severity`, `alert_title` |
| `ApplianceAlertIngestRequest` | `schemas/alert_ingest.py` | `extra="forbid"`; no `tenant_id` from client |
| `EdrActionExecuteRequest` | `schemas/edr.py` | action types listed below |
| `ProcessTreeNode` | `schemas/edr.py` | pid/guid/name/cmdline/hashes/MITRE |

Adding a mid-layer EDR event as a **new top-level JSON field** on those request models requires a coordinated API + UI change. Prefer stuffing kernel telemetry into existing `raw_event` / `edr_process_events` shapes.

### 2.6 Custom Wazuh decoders / index mappings in git

| Artifact | Location | Status |
|---|---|---|
| Custom `local_rules.xml` / decoders | **Not in repo** | Live on VM 101 Manager |
| OpenSearch mapping.json | `archive/legacy-docker-stack-export-2026-07-06/configs/opensearch/mapping.json` | **Retired** Docker SIEM |
| Sysmon baseline | `scripts/sysmon-windows-baseline.xml` (copies under `deploy/`, `backend-api/app/endpoint_configs/`, `templates/`) | Endpoint config, not a Wazuh decoder |
| Network decoder names consumed by taxonomy | `fortigate-firewall`, `pfsense`, `vyos`, `opnsense`, `cisco-ios` (`soc_alert_taxonomy.py`) | Detection by `raw_event.decoder.name` |

**Implication for EDR:** new kernel events should ride **existing Wazuh Windows/Linux decoders** (Sysmon, eventchannel, auditd) or a **new Manager local rule in the 100000+ range**, not a new OpenSearch index and not a new Postgres alert table.

### 2.7 Derived fields (read-time — no extra schema)

`soc_alert_taxonomy.py` + `soc_alert_synthesis.py` attach:

- `asset_category` / `asset_category_label` / `device_type` / `contextual`  
- `wazuh_rule_id`, `wazuh_rule_level`, `wazuh_agent_id`  
- `process_name`, `parent_process_name`, `command_line`, `parent_command_line`, `hash_md5`, `hash_sha256`  
- `file_path` / `file_name`  
- `mitre_tactics` / `mitre_techniques`  
- `display_ip_address`, `display_operating_system`, `display_mac_address`

Taxonomy slugs (Admin filter badges):  
`all, uncategorized, endpoints_windows, endpoints_linux, endpoints_vm_container, network_ids_sensors, network_hardware, security_edge_appliances, databases_storage, identity_access, iot_ot, vuln_web_app, vuln_infrastructure`.

Windows/Linux EDR telemetry that arrives with `source_tool=wazuh` already lands in `endpoints_windows` / `endpoints_linux` via agent OS in `raw_event.agent.os`.

### 2.8 Customer-safe source labels

`backend-api/app/services/customer_safe_labels.py`:

| Internal `source_tool` | Customer `source` |
|---|---|
| `wazuh` | Endpoint monitoring |
| `suricata` | Network monitoring |
| `zeek` | Network traffic analysis |
| `nuclei` / `vuls` / `greenbone` / `openvas` | Vulnerability assessment |
| `shuffle` | Security automation |
| `thehive` | Incident response |
| `misp` | Threat intelligence |
| `velociraptor` | Endpoint forensics |
| unknown / empty | Managed detection |

**Any new EDR `source_tool` (e.g. `ebpf`, `sysmon`, `etw`) must be added here** or customers will see the generic “Managed detection” label (safe) rather than a broken panel — but Admin `source_tool` column will show the raw value.

---

## 3. Dashboard and UI dependencies

Both portals are React + nginx. Browser calls `/api/...`; nginx rewrites to FastAPI (`frontend-admin/nginx.conf`, `frontend-customer/nginx.conf`).

### 3.1 Admin / SOC portal (`:3000`)

Routes: `frontend-admin/src/App.tsx` + nav `frontend-admin/src/components/Layout.tsx`.

| Route | Page | Primary APIs |
|---|---|---|
| `/dashboard` | Dashboard | admin summaries |
| `/tenants` | Customers | `/admin/tenants` |
| `/users` | Users | `/admin/users` |
| `/appliances` `/appliances/:id` | Appliances | `/admin/appliances` |
| `/assets` | Protected assets | `/admin/assets` |
| `/alerts` `/alerts/:alertId` | SOC alerts | `/admin/alerts`, taxonomy-summary, tenant-summary |
| `/incidents` `/incidents/:incidentId` | Incidents + EDR deep dive | `/admin/incidents`, `/v1/edr/incidents/deep-dive`, `/v1/edr/actions/*` |
| `/vulnerabilities` | Vuln triage | vuln admin APIs |
| `/recommendations` | Recommendations | admin recs |
| `/reports` | Monthly reports | reports |
| `/notifications` | Notification events | admin notifications |
| `/audit` | Audit | `/admin/audit-logs` |
| `/services` `/service-requests` | Catalog | catalog APIs |
| `/retrospective-hunts` | ThreatLens hunts | threatlens |
| `/threat-intel` | MISP ops | threat intel admin |
| `/ai-assistant` | AI chat | `/admin` AI (flag `AI_CHAT_ENABLED`) |

**Admin alert list fields that must not disappear** (`frontend-admin/src/api/admin.ts` `Alert` / `AlertDetail`):

`id, tenant_name, short_code, external_alert_id, source_tool, severity, alert_title, source_ip, destination_ip, destination_host, source_user, ai_plain_summary, ai_likely_attack_type, customer_visible, status, created_at, asset_category, device_type, asset_category_label, contextual`

**Admin alert detail extra fields (SOC-only raw allowed):**

`raw_event, mitre_mapping, ai_technical_summary, wazuh_rule_id, wazuh_rule_level, wazuh_agent_id, process_name, parent_process_name, command_line, parent_command_line, hash_md5, hash_sha256, file_path, file_name, mitre_tactics, mitre_techniques, display_*`

Rendered explicitly in `AlertDetailPage.tsx` (`source_tool`, `external_alert_id`, `wazuh_rule_id`, `asset_category_label`).

**EDR widgets** (`frontend-admin/src/api/edr.ts`, `IncidentDetailPanel.tsx`, `IncidentDetailPage.tsx`):

- `GET /v1/edr/incidents/deep-dive` → `process_tree.root`, MITRE, recent actions, forensic artifacts  
- `POST /v1/edr/actions/execute`  
- `GET /v1/edr/metrics/summary`

Process tree node fields: `pid, parent_pid, process_guid, parent_process_guid, process_name, parent_process_name, command_line, parent_command_line, user, hash_md5, hash_sha256, signed_status, mitre_techniques, event_time, child_processes`.

### 3.2 Customer portal (`:3001`)

Routes: `frontend-customer/src/App.tsx`. Nav split: always-on core vs entitlement add-ons (`navEntitlements.ts`).

**Core (always):** Dashboard, Alerts, Incidents, Assets, Recommendations, Reports, Notifications, Users, Audit, Account, Service Portfolio.

**Entitlement-gated:** Vulnerabilities, Compliance, Attack Surface, Cloud & Identity, Network Detection, Threat Intel, ThreatLens, Forensics.

Customer APIs: `backend-api/app/api/routes/customer.py` prefix `/customer`.

**Customer alert detail whitelist** (`_customer_safe_alert_detail_row`) — breaking any of these names breaks the customer Alert/Incident cards:

`alert_id, title, severity, status, source, summary, description, detected_at, hostname, asset_category, asset_category_label, device_type, operating_system, business_impact, recommended_action, likely_attack_type, criticality, wazuh_rule_id, wazuh_rule_level, file_path, file_name, process_name, parent_process_name, command_line, parent_command_line, hash_md5, hash_sha256, mitre_tactics, mitre_techniques`

Note: customer responses **do** currently include `wazuh_rule_id` / `wazuh_rule_level` even though engine *names* are remapped via `source`. Do not rename those keys without a frontend change.

**Customer copy leaks (capability-label gaps — do not “fix” as part of EDR ingest without a named KB):**

| Location | What customers see today |
|---|---|
| `frontend-customer/src/pages/AlertDetailPage.tsx` | Table header **“Wazuh rule”** plus `wazuh_rule_id` / level |
| `frontend-customer/src/pages/IncidentDetailPage.tsx` | Same **“Wazuh rule”** row |
| `frontend-customer/src/components/edr/EdrControlPanel.tsx` | Isolate confirm text names **“Wazuh Manager ports 1514/1515”** |

Frontends contain **no hardcoded alert UUIDs or numeric Wazuh rule IDs**; 92213/92057 live only in backend Python. Admin `TriageListFilters` also has a `source_platform` query key — that is a filter name, not the alert column (`source_tool`).

**Customer EDR containment** (`frontend-customer/src/components/edr/EdrControlPanel.tsx`):  
`customer_admin` may `ISOLATE_HOST`, `UNISOLATE_HOST`, `KILL_PROCESS`, `COLLECT_FORENSICS`, `BLOCK_HASH` (KB-083 co-managed policy). Isolate is **hold until Un-isolate** (KB-104). Windows quarantine is **firewall + watchdog**, not a kernel driver (`Watch-MsspQuarantine.ps1`).

### 3.3 Hardcoded rule IDs and decoder names the UI/logic depends on

These are **not** dashboard panel IDs; they are code branches. Changing Manager rules without updating code changes SOC copy / incident creation.

| ID / name | Where | Effect |
|---|---|---|
| Wazuh **92213** | `soc_sync.py` noise filter; `soc_alert_synthesis.py` | File-drop / PowerShell policy-test; can suppress auto-incident |
| Wazuh **92057** | `soc_alert_synthesis.py` | Maps likely attack to T1059.001 PowerShell |
| Custom **100049** | KB-063 lab proof | Already used on Manager (reserve nearby IDs carefully) |
| Decoder `fortigate-firewall`, `pfsense`, `vyos`, `opnsense`, `cisco-ios` | taxonomy | Maps to `security_edge_appliances` |
| AR commands `mssp-isolate-host`, `mssp-kill-process`, `mssp-block-hash` (+ `.cmd` on Windows) | `deploy/wazuh-active-response/`, appliance `register_ops.py` | Isolate/kill/hash |

There are **no** Grafana/Kibana/OpenSearch custom dashboard JSON files powering the product UIs. The “custom dashboards” **are** the React portals.

---

## 4. Current development stage and wiring

### 4.1 Production-ready vs in-development vs mock/sample

| Capability | Stage | Evidence |
|---|---|---|
| Auth / RBAC / tenant isolation | **Production** | KB-010/011; portals live |
| Admin + Customer nginx portals | **Production** | Compose; KB-035+ |
| Wazuh instant ingress + Shuffle forward | **Production** | KB-063 live; hook in `soc_sync.py` |
| Suricata → Wazuh localfile | **Production** (sensor) | KB-044 role |
| Zeek co-located | **Deployed path exists**; Ansible default still `preflight` until apply | KB-047 |
| TheHive/Shuffle case path | **Production** (VM 102) | dual-path ingest |
| EDR actions + process trees + forensics upload | **Production (committed)** tags `kb083-*`, `kb084-edr-lifecycle-forensics-validated` | `/v1/edr/*` |
| Host isolate hold-until-unisolate | **Production default** | tag `kb104-isolate-standard-golden-validated` |
| Windows Sysmon + 4688 bootstrap | **Production packaging** | `bootstrap_windows_telemetry.ps1`, agent ZIP |
| Appliance register/heartbeat/channel | **Production** on VM 114 | KB-093L |
| Appliance critical-alert forward | **Production** golden recipe | KB-093P |
| Nuclei + Vuls + Greenbone CE adapters | **Production ingest contract** | `/integrations/vuln/sync` |
| Greenbone Enterprise | **Deferred** | KB-077 |
| NDR customer UI | **Hybrid** | Live import from suricata/zeek alerts **or** controlled sample seed (`ndr_service.py`) |
| ITDR / some Threat Intel | **Adapter + sample seed** when Graph/MISP live credentials missing | `itdr_service.py`, `threat_intel_service.py` |
| AI alert analysis / SOC chat | **Code complete, flags default off** | `AI_ALERT_ENABLED`, `AI_CHAT_ENABLED`, `AI_SOC_TRIAGE_ENABLED` |
| MISP VM 108 | **Stub IOC bridge** (SQLite + seeded demo attributes), not real MISP | `scripts/kb108_install_misp_direct.sh` |
| Velociraptor VM 110 | **Adapter-ready, not confirmed live** | `velociraptor_client.py`; Ansible `preflight` |
| Linux osquery | **Template only** — not auto-installed | `osquery-endpoint-pack.conf` vs `_linux_script()` |
| Linux endpoint VM 105 | **Gone** | CONTEXT |
| Notification send worker | **Paused** (project rules) | — |
| Near-kernel eBPF/ETW/Minifilter pipeline | **Not present** | this blueprint’s future work |

Mock payloads for EDR tests: `docs/fixtures/kb084_edr_mock_payloads.json` (tests/fixtures only — not runtime defaults).

### 4.2 How endpoints are managed today

| Channel | Mechanism | Files |
|---|---|---|
| Windows/Linux agent packages | Per-tenant ZIP/one-liner from control plane | `admin_agent_packages.py`, `agent_package_builder.py`, `public_agent_install.py` |
| Windows telemetry | Sysmon XML + auditpol 4688 + `ossec.conf` eventchannels | `scripts/bootstrap_windows_telemetry.ps1` |
| Linux telemetry pack | osquery JSON pack is **admin-downloadable only**; Linux ZIP does not install osqueryd | `osquery-endpoint-pack.conf`, `agent_package_builder.py` |
| AR script trees | Dual copies (KB-091 gap H4) | `deploy/wazuh-active-response/` vs `backend-api/app/endpoint_configs/{windows,linux}-edr-ar/`; Linux endpoint_configs tree has **only** `mssp-block-hash` |
| Sysmon baseline XML | Four copies — edit all or pick one source of truth | `scripts/`, `deploy/windows-endpoint-telemetry/`, `templates/endpoint-configs/`, `backend-api/app/endpoint_configs/` |
| Wazuh enrollment | Agent → Manager **1515**, events **1514**; groups `tenant_<SHORT>` | `endpoint_configs/wazuh-agent-parameters.conf` |
| Isolate / kill / block | Wazuh Active Response scripts published to Manager shared groups; appliance channel can dispatch | `deploy/wazuh-active-response/`, `edr_actions.py` |
| Appliance fleet | Register + heartbeat to **VM 114**; jobs over channel (WSS/HTTPS poll) | `appliance_agent.py`, `appliance_channel.py` |
| Orchestration | Ansible from VM 112; playbooks default **preflight** until `*_live_*_approved=true` | `ansible/playbooks/*` |
| SOAR | Shuffle webhook + Redis durable retry (`mssp:shuffle:outbound`) | `shuffle_retry_queue.py` |

### 4.3 Background workers on API startup

`main.py` starts: `edr_sweeper_loop`, Shuffle retry worker, AI alert worker (no-op if disabled).

---

## 5. Safe extension points for mid-layer EDR

### 5.1 Recommended native plug-in (does not change schemas)

**Put kernel telemetry into the Wazuh agent → Manager → existing instant hook.**

That is how Sysmon, 4688, auditd, and osquery already work. eBPF/ETW/Minifilter collectors should **emit into a channel Wazuh already tails**, then reuse:

1. `POST /integrations/soc/hooks/wazuh/{token}`  
2. `source_tool="wazuh"` (keeps customer label “Endpoint monitoring” and taxonomy Windows/Linux)  
3. Sysmon-like `data.win.eventdata` **or** auditd `data.audit` **or** osquery rows so `normalize_process_event()` fills process trees **with zero UI change**

| Telemetry | Existing native landing zone | Parser already understands |
|---|---|---|
| Windows process create | Sysmon Event ID 1 via `Microsoft-Windows-Sysmon/Operational` | `edr_process_tree.py` Sysmon branch |
| Windows 4688 | Security eventchannel query `EventID=4688` | Partial (better coverage if also Sysmon) |
| Windows ETW (general) | **Sysmon is the current ETW consumer** | Image/CommandLine/ProcessGuid/Hashes |
| Windows minifilter / file | Sysmon FileCreate (`targetFilename` extracted in `soc_sync.py`) | Alert evidence `file_path` |
| Linux exec | auditd EXECVE groups | `raw_source=endpoint_audit_exec` |
| Linux eBPF | **No collector yet** — safest is CO-RE program → JSON log → Wazuh `localfile` json **shaped like osquery process_events** (`pid, parent, name, path, cmdline, username, sha256`) | osquery branch |
| Container | taxonomy keywords docker/k8s in blob | `endpoints_vm_container` |

**Do not** create a parallel `kernel_events` table as the dashboard source. Admin/Customer alerts **only** list `security_alerts`. Optionally INSERT the same normalized row into `edr_process_events` (additive cache). If the event did not come through the Wazuh hook, call `persist_wazuh_alert_enrichment` (or equivalent) from the new writer so process trees stay populated.

### 5.2 Acceptable alternative: new `source_tool` without schema change

If kernel telemetry must be distinguished internally:

1. Keep `security_alerts` columns unchanged.  
2. Set `source_tool` to a **new slug** (recommend `endpoint_kernel`, not `ebpf`/`sysmon` in customer-visible Admin lists if you want to hide vendor/tech).  
3. Add mapping in `customer_safe_labels.py` → `"Endpoint monitoring"`.  
4. Extend `derive_asset_category()` so the slug still maps to `endpoints_windows` / `endpoints_linux` (today unknown tools fall through wazuh-like heuristics or `uncategorized`).  
5. Use a **new** `external_alert_id` namespace (e.g. `ekernel-<guid>`) so you do not collide with Wazuh alert ids on `(tenant, source_tool, external_alert_id)`.  
6. Prefer `POST /integrations/soc/sync` **plus** an explicit persist into `edr_process_events`. Soc sync alone does **not** call EDR persist.

### 5.3 Paths that will break dashboards if used naively

| Bad idea | Why it breaks |
|---|---|
| New OpenSearch index as UI source | Portals do not query Indexer |
| Filebeat/Logstash on VM 100 | New ports, new failure domain, bypasses tenant fail-closed hook |
| Extra JSON fields on `SocSyncRequest` / `ApplianceAlertIngestRequest` without model change | `extra="forbid"` → **422**, silent ingest death |
| Changing `source_tool` of existing Wazuh rows | Breaks Admin column, taxonomy, customer labels, dedup |
| Reusing Wazuh `external_alert_id` with a new `source_tool` | Creates **duplicate SOC cards** for one event |
| Reusing same `source_tool=wazuh` + same `external_alert_id` | Second pipeline is dropped as duplicate (`200` already synced) |
| Putting eBPF volume into appliance `to_cloud_alert` without size limits | Appliance path is **metadata**; raw logs must stay on-prem (KB-093P) |
| Binding a new UI on `:3001` on VM 100 | Collides with Customer portal |
| Binding Shuffle on VM 100 `:3001` | Same |
| Using Wazuh Dashboard as “the EDR UI” | Violates product architecture |

### 5.4 Collision register (must avoid)

#### Ports (by host)

| Port | VM 100 | VM 101 | VM 102 | VM 109 | VM 114 | VM 110 (planned) |
|---|---|---|---|---|---|---|
| 80/443 | nginx in containers map 3000/3001→80 | Wazuh Dashboard 443 | — | Greenbone GSA 443 | — | — |
| 1514/1515 | — | Wazuh agents | — | — | — | — |
| 3000 | **Admin portal** | — | — | — | — | — |
| 3001 | **Customer portal** | — | **Shuffle** | — | — | — |
| 5432 / 6379 | loopback Postgres/Redis | — | — | — | tunnel to 100 | — |
| 55000 / 9200 | — | Wazuh API / Indexer | — | — | — | — |
| 8000 | **FastAPI** | — | — | — | **Appliance Mgmt API** | — |
| 8001 | — | — | — | — | — | Velociraptor bridge default |
| 8080 | — | — | — | — | — | MISP default on 108 |
| 9000 | — | — | TheHive | — | — | — |
| 9392 | — | — | — | Greenbone HTTP | — | — |

New EDR collectors on endpoints should **not** need a control-plane listen port. If a dedicated receiver is required, pick an unused port **≥ 8100** on VM 100 or terminate on VM 114 (appliance plane), never 3000/3001/8000/1514/1515/55000.

#### Wazuh rule IDs

| Range | Owner | Guidance |
|---|---|---|
| 1–999 | Wazuh reserved | Do not use |
| ~61600–99000 stock Windows/Sysmon/FIM | Upstream ruleset | Do not overwrite |
| **92057, 92213** | Referenced in control-plane Python | Do not repurpose |
| **100049** | Already used in this lab (KB-063) | Do not reuse |
| **100000–109999** | Existing custom-ish range | Inventory Manager `local_rules.xml` before allocating |
| **110000–119999** | **Recommended reservation for kernel EDR rules** | Document in a new KB before shipping |

#### Naming

| Name | Already used |
|---|---|
| `source_tool=wazuh\|suricata\|zeek\|network_appliance\|nuclei\|vuls\|greenbone\|shuffle\|thehive\|misp\|velociraptor\|appliance` | Ingest + taxonomy + labels |
| `mssp-isolate-host` / `mssp-kill-process` / `mssp-block-hash` | Active Response |
| Incident `INC-<TENANT>-TH-*` vs `INC-<TENANT>-APP-*` | Two generators; do not invent a third prefix without UI search updates |
| Workflow `EDR_COLLECT_FORENSICS` | Shuffle |
| Redis keys `mssp:shuffle:outbound`, `mssp:ai:alert_analysis` | Workers |
| Agent localfile markers `MSSP KB-044 Suricata`, `MSSP KB-047 Zeek` | Ansible blockinfile |

#### Isolate path (do not bypass)

Isolate buttons travel **VM 100 EDR API → (optional Shuffle) → Wazuh AR and/or VM 114 channel → appliance Manager → agent**. Windows quarantine must keep Manager **TCP/UDP 1514** and **TCP 1515** plus DHCP/loopback (KB-104). A new eBPF/WFP filter that blocks 1514/1515 will brick both telemetry and un-isolate.

### 5.5 Concrete “do not break” checklist before writing EDR features

1. Keep writing alerts to **`security_alerts`** with existing columns.  
2. Keep nginx `/api/` rewrite behavior.  
3. Recreate **both** frontends if `backend-api` is recreated (stale Docker DNS).  
4. Do not change customer whitelist field names in `customer.py`.  
5. Do not change Admin `Alert` TypeScript interface names without updating `AlertsPage` / `AlertDetailPage`.  
6. Preserve process-tree parser keys: `data.win.eventdata.{Image,CommandLine,ProcessId,ParentProcessId,ProcessGuid,ParentProcessGuid,Hashes,User}`.  
7. Preserve fail-closed tenant mapping.  
8. Do not listen on 3000/3001/8000 on VM 100.  
9. Do not ship unsigned WPK as the EDR update path (CONTEXT / KB-104).  
10. After any control-plane code change: `./scripts/production_deploy_control_plane.sh` and `./scripts/run_post_change_checks.sh` (operator rule — not done for this docs-only audit).

### 5.6 Suggested first EDR increment (architecture only)

1. Inventory live Manager `local_rules.xml` / decoder names on VM 101 (out of band; not in git).  
2. Reserve rule IDs **110000–119999**.  
3. Linux: eBPF exec/connect → JSON line log → existing Wazuh `localfile` `log_format=json` with osquery-compatible fields.  
4. Windows: keep Sysmon as the ETW/minifilter abstraction; add providers only via Sysmon XML (`sysmon-windows-baseline.xml`) so `ossec.conf` localfiles stay unchanged.  
5. Confirm events appear on Admin `/alerts` with `source_tool=wazuh` and non-empty process tree on `/incidents/:id`.  
6. Only then consider a distinct `source_tool` or a dedicated receiver.

---

## Appendix A — FastAPI router map (extension surface)

From `backend-api/app/main.py`:

Auth, health, admin, alert/incident triage, recommendations, admin ops, customer, tenants, users, on-prem template, appliance management, appliance agent, appliance channel, appliance alert ingest, telemetry ingest, soc sync, vuln/easm sync, vulnerability management, entitlements, service catalog, compliance, easm, itdr, vmaas, ndr, threat intel, threatlens, endpoint forensics, **edr**, admin AI chat, onboarding configs, agent packages, public install, customer users, audit logs.

EDR HTTP API (`backend-api/app/api/routes/edr.py`, nginx-exposed as `/api/v1/edr/...`):

| Method | Path |
|---|---|
| GET | `/v1/edr/telemetry/process-tree` |
| POST | `/v1/edr/actions/execute` |
| POST | `/v1/edr/actions/callback` |
| GET | `/v1/edr/actions/{execution_id}` |
| PUT | `/v1/edr/forensics/upload/{artifact_id}` |
| GET | `/v1/edr/forensics/download/{artifact_id}` |
| POST | `/v1/edr/forensics/complete` |
| GET | `/v1/edr/incidents/deep-dive` |
| GET | `/v1/edr/metrics/summary` |

---

## Appendix B — Normalization vocabulary

Control plane records (KB-036 rule), as implemented:

| Concept | Implementation |
|---|---|
| tenant | `tenants.id` / `short_code` |
| source_platform | **`vulnerabilities.source_platform`** only; alerts use **`source_tool`** |
| asset | `protected_assets` |
| alert | `security_alerts` |
| incident / case | `incidents` (TheHive is adapter, not SoR) |
| recommendation | `customer_recommendations` |
| vulnerability | `vulnerabilities` |
| visibility_status | **No such column.** Implemented as `security_alerts.customer_visible` (boolean). KB-104 `036_kb104_customer_alert_visibility_parity.sql` backfills non-`false_positive` rows to `true` |
| sync_health_status | **No such column.** Closest: `appliances.status`, `appliance_heartbeats.health_status`, `tenant_ndr_sensors.sensor_status` |

---

## Appendix C — Source files used for this audit

- `/opt/mssp-control/docker-compose.yml`  
- `/opt/mssp-control/ansible/inventory/hosts.yml`  
- `/opt/mssp-control/backend-api/app/main.py`  
- `/opt/mssp-control/backend-api/app/api/routes/soc_sync.py`  
- `/opt/mssp-control/backend-api/app/api/routes/appliance_alert_ingest.py`  
- `/opt/mssp-control/backend-api/app/api/routes/telemetry_ingest.py`  
- `/opt/mssp-control/backend-api/app/api/routes/edr.py`  
- `/opt/mssp-control/backend-api/app/api/routes/customer.py`  
- `/opt/mssp-control/backend-api/app/services/edr_ingress.py`  
- `/opt/mssp-control/backend-api/app/services/edr_process_tree.py`  
- `/opt/mssp-control/backend-api/app/services/soc_alert_taxonomy.py`  
- `/opt/mssp-control/backend-api/app/services/customer_safe_labels.py`  
- `/opt/mssp-control/postgres/init/001_mssp_core_schema.sql`  
- `/opt/mssp-control/postgres/init/014_kb083_edr_actions.sql`  
- `/opt/mssp-control/postgres/init/015_kb084_edr_lifecycle_forensics.sql`  
- `/opt/mssp-control/frontend-admin/src/App.tsx`  
- `/opt/mssp-control/frontend-customer/src/App.tsx`  
- `/opt/mssp-control/scripts/bootstrap_windows_telemetry.ps1`  
- `/opt/mssp-control/kevantic-appliance/appliance/common/privacy.py`  
- `/opt/mssp-control/CONTEXT.md`  

---

---

## Appendix D — Deep-scan corrections (same-day follow-up)

Additional facts from a second pass over adapters, frontends, and EDR trees. These override softer wording above.

1. **MISP is a stub.** Treat VM 108 as a restSearch-compatible demo API with seeded IOCs, not production MISP. Do not plug EDR intel enrichment into it as if it were a real platform.
2. **Greenbone tenant map lab default is `DEMO`** (`config/greenbone_host_tenant_map.yml`). Alert ingest remains fail-closed; vuln host-map is a separate, weaker default — do not copy that pattern into kernel telemetry tenant mapping.
3. **`edr_mitre.mitre_from_wazuh_alert()` hardcodes provenance `source: "wazuh_rule"`. ** A kernel sensor should emit a distinct MITRE `source` (for example `endpoint_kernel`) so Admin MITRE cards do not attribute eBPF hits to Wazuh rules.
4. **Telemetry counter** in `edr_ingress.bump_telemetry_counter()` currently matches blob substrings `sysmon` / `osquery` / `process` / `audit`. Add `ebpf` / `etw` / `minifilter` there if those events should appear in `/v1/edr/metrics/summary`.
5. **Action callback is already extensible:** `EdrActionCallbackRequest` uses `extra="allow"`. New AR/kernel proof fields can POST without a schema migration; isolate still requires `applied` / `released` booleans for Verified.
6. **Appliance watcher** (`critical_alert_watcher.py`) tails `/var/ossec/logs/alerts/alerts.json` from **EOF** on first start/rotation — historical alerts are not replayed.
7. **Velociraptor ports to avoid:** bridge **8001**, GUI **8889**, frontend **8000** (8000 already used on VM 100 and VM 114).
8. **Linux AR on the Manager** is the `deploy/wazuh-active-response/` tree (`mssp-isolate-host`, `mssp-kill-process`, `mssp-block-hash`). Do not add a fourth command name that collides; stay on the `mssp-` prefix.

---

*End of specification. No control-plane code or Compose services were changed for this audit.*
