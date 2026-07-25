# KB-036 — MSSP Platform Architecture and Deployment Model Roadmap

Status: Validated (pending tag).  
Branch: `kb036-mssp-platform-architecture-roadmap`  
Module type: **Documentation only** — no runtime code, schema, compose, or `.env` changes.

---

## 1. Purpose

Document the **enterprise-style open-source MSSP / SOC / MDR / XDR platform** vision, approved capability stack, deployment models (cloud, on-prem, hybrid), planned VM layout, normalization rules, customer safety boundaries, and the **KB-037 through KB-060** implementation roadmap.

This is **not** a small Wazuh dashboard project. MSSP Control Plane is the multi-tenant product; open-source engines are backend adapters only.

---

## 2. Enterprise platform vision

We are building a **strong, futuristic, multi-tenant MSSP SOC platform** that supports monitoring and response across:

- Endpoints and servers
- Network traffic
- Firewalls and network devices
- Applications
- Cloud and on-prem environments
- Security alerts and incidents/cases
- Vulnerabilities and threat intelligence
- Automation/playbooks
- Customer reporting and visibility controls

The platform includes:

1. **Admin/SOC-facing control plane** — triage, cases, integrations, tenant onboarding
2. **Customer-facing portal** — plain-English, customer-safe summaries only
3. **Multi-tenant customer onboarding**
4. **Cloud-hosted MSSP cluster deployment**
5. **Customer on-prem appliance deployment**
6. **Hybrid deployment** (mixed on-prem + central sync)
7. **Automated deployment templates** (Ansible + Compose first)
8. **Normalized ingestion** from all approved SOC tools

---

## 3. Current application state (Phase 1 — mostly complete)

### 3.1 VM 100 — MSSP Control Plane (deployed)

| Item | Value |
|---|---|
| VM | **100** — `mssp-control` |
| IP | `192.168.0.201` |
| Path | `/opt/mssp-control` |
| Stack | FastAPI, PostgreSQL, Redis, Docker Compose |
| UIs | Admin/SOC `:3000`, Customer `:3001` |

**Do not install heavy SOC tools on VM 100** unless explicitly approved in a future KB.

### 3.2 Latest validated feature baseline

| Item | Value |
|---|---|
| Latest validated feature KB | **KB-035** — Customer Appliance Detail UI |
| Commit | `1ac1df3` |
| Tag | `kb035-customer-appliance-detail-validated` |

### 3.3 MSSP Control Plane — already built

**Admin / SOC (KB-010–KB-020, KB-016/017):**

- Auth/RBAC, protected admin and customer APIs
- Tenant, user, appliance management
- Activation tokens, appliance registration/heartbeat
- Credential visibility/rotation (admin only)
- Admin frontend foundation

**Customer portal (KB-021–KB-035):**

- Dashboard v2, alerts, incidents, assets, appliances, reports, recommendations (list + detail)
- Notifications history (KB-033), account/profile hardening (KB-034)

**Not built yet on control plane:**

- Deployment and integration registry (KB-037+)
- Live SOC data adapters (KB-057+)
- Vulnerability, threat-intel, and network-sensor normalized tables/endpoints (future schema KBs)

### 3.4 Critical current limitation

**The real enterprise SOC stack has NOT been deployed yet.**

- No Wazuh, Suricata, Zeek, TheHive, Shuffle, MISP, Greenbone, or Velociraptor in lab VMs
- No integration adapters — customer portal does **not** receive live SOC alerts
- Current data is mostly **app/database-driven** (demo/fixtures)

Do **not** install tools or create VMs until the relevant future KB is explicitly approved.

---

## 4. Enterprise open-source capability stack

### Layer 1 — MSSP Control Plane

| Component | Status |
|---|---|
| FastAPI / PostgreSQL / Redis | Deployed (VM 100) |
| Multi-tenant tenant/customer management | Built |
| Customer-safe portal | Built (KB-021–035) |
| Admin/SOC dashboard | Foundation built |
| Deployment and integration registry | Future (KB-037+) |

### Layer 2 — SIEM / endpoint security / log security

| Tool | Role |
|---|---|
| Wazuh Manager / API | Detection, agent management, alert source |
| Wazuh Indexer / OpenSearch | Log and alert indexing |
| Wazuh Dashboard | SOC analyst UI (not customer-facing) |
| Wazuh Agents | Endpoint and server collection |

### Layer 3 — Network detection / NDR-style visibility

| Tool | Role |
|---|---|
| Suricata | IDS/IPS, network threat detection |
| Zeek | Network security monitoring, protocol visibility |

### Layer 4 — Case management / incident response

| Tool | Role |
|---|---|
| TheHive | Case and incident workflow |
| Cortex | Analyzer/responder capability with TheHive workflows (if needed) |

### Layer 5 — SOAR automation

| Tool | Role |
|---|---|
| Shuffle | Playbooks and automation orchestration |

### Layer 6 — Threat intelligence

| Tool | Role |
|---|---|
| MISP | Threat intelligence platform (planned roadmap) |
| OpenCTI | **Future optional** — not immediate scope |

### Layer 7 — Vulnerability management

| Tool | Role |
|---|---|
| Greenbone / OpenVAS | Vulnerability scanning and findings |

### Layer 8 — Endpoint investigation / DFIR

| Tool | Role |
|---|---|
| Velociraptor | DFIR and endpoint investigation |
| osquery | **Optional** — endpoint telemetry/investigation support |

### Layer 9 — Deployment automation

| Approach | Priority |
|---|---|
| Ansible | First |
| Docker Compose | First (per-service/cluster templates) |
| Terraform / OpenTofu | Later (infrastructure provisioning) |
| Kubernetes | **Future optional only** — not immediate |

### Layer 10 — Observability / platform health

| Tool | Role |
|---|---|
| Prometheus / Grafana (or equivalent) | Service, cluster, appliance, and ingestion health |

---

## 5. Normalization rule (architecture invariant)

**MSSP Control Plane must not care** whether data originated from:

- Cloud Wazuh cluster
- Customer on-prem appliance
- Suricata, Zeek, TheHive, Shuffle, MISP, Greenbone, Velociraptor
- Or any future approved integration

It only consumes **normalized, tenant-scoped records** with these concepts:

| Record concept | Purpose |
|---|---|
| `tenant` | Isolation boundary |
| `source_platform` | Which engine/cluster/appliance produced the data |
| `asset` | Protected asset posture |
| `alert` | Security alert (customer-safe projection for portal) |
| `incident` / `case` | Incident and case workflow |
| `recommendation` | Customer action items |
| `vulnerability` | Vulnerability findings (customer-safe projection) |
| `report` | Customer reports |
| `visibility_status` | What the customer may see |
| `sync_health_status` | Integration/appliance/cluster sync health |

Adapters: external tool → normalize → PostgreSQL → admin API vs customer-safe API filtering.

---

## 6. Deployment models

### A. Cloud-hosted MSSP model

- MSSP hosts **shared SOC clusters**
- Multiple customers per cluster based on **capacity** — agents, EPS, GB/day, retention, performance, isolation
- **Not** hardcoded as a fixed number of customers (e.g. not “exactly 10”)
- When a cluster reaches capacity, deploy a **new cluster** for future customers
- Raw logs and raw engine events stay in the SOC cluster

### B. Customer on-prem appliance model

- For customers whose policy requires logs **not to leave premises**
- Appliance runs collector/security stack locally
- Only **safe metadata** syncs to MSSP Control Plane:

  - Alert summary, incident/case summary/status
  - Asset health, appliance health
  - Recommendation summary, report summary
  - Case reference (ID/title/status — not raw case JSON)

- **No raw logs** to customer portal
- **No raw logs** required in customer-facing API responses

### C. Hybrid model

- Some data processed on-prem, some in cloud
- Safe summary/case/health metadata synced centrally
- Selected customers may use a **dedicated cloud cluster**
- Control plane still uses one normalized record model

### Data flows

**Cloud model:**

```
Endpoints/Wazuh agents + network sensors (Suricata/Zeek)
  → Wazuh cluster + Indexer/OpenSearch
  → Shuffle automation
  → TheHive case workflow
  → MISP enrichment / Greenbone vuln feeds (via adapters)
  → MSSP Control Plane (normalized records)
  → Admin/SOC dashboard
  → Customer-safe portal
```

**On-prem / hybrid model:**

```
Customer sources → on-prem appliance/stack → local retention
  → safe metadata sync → MSSP Control Plane
  → Admin/SOC dashboard → Customer-safe portal
```

---

## 7. Planned VM layout (Proxmox lab)

| VM | Name | Purpose | Status |
|---|---|---|---|
| **VM 100** | `mssp-control` | MSSP Control Plane (`192.168.0.201`) | **Deployed** |
| **VM 101** | `wazuh-stack` | Wazuh Manager, Indexer/OpenSearch, Dashboard | Future |
| **VM 102** | `thehive` | TheHive (+ Cortex if needed) | Future |
| **VM 103** | `shuffle` | SOAR playbooks | Future |
| **VM 104** | `windows-endpoint-lab` | Windows + Wazuh Agent | Future |
| **VM 105** | `linux-endpoint-lab` | Linux + Wazuh Agent | Future |
| **VM 106** | `suricata-sensor` | Suricata IDS/IPS sensor | Future |
| **VM 107** | `zeek-sensor` | Zeek network monitoring | Future |
| **VM 108** | `misp` | MISP threat intelligence | Future |
| **VM 109** | `greenbone` | Greenbone/OpenVAS vulnerability scanning | Future |
| **VM 110** | `velociraptor` | Velociraptor DFIR server | Future |
| **VM 111** | `monitoring` | Prometheus/Grafana platform health | Future |

VMs 101–111 are **roadmap placeholders** — create only when the matching KB is approved.

### Future customer on-prem appliance template

- Deployed at customer site (VM or appliance hardware)
- Runs approved local collector/security stack
- Sends only safe metadata/health/status to control plane
- No secrets in Git; no raw logs to customer portal

---

## 8. Cluster registry and appliance registry (future)

Planned in KB-037/KB-038:

- **Cluster registry** — Wazuh/SOC clusters, capacity metrics, health
- **Appliance registry** — extends existing `appliances` table and admin APIs
- **Deployment mode per tenant:** `cloud` / `on-prem` / `hybrid`
- **Customer-to-cluster mapping** and multi-cluster placement (KB-059)
- **No appliance or integration secrets** exposed to customers or committed to Git

---

## 9. Customer portal safety (mandatory)

Customer portal must **never** expose:

- Raw logs, raw Wazuh alerts, raw Suricata/Zeek logs
- Raw JSON (`raw_event`, `raw_json`, `details`, `metrics`, `health_snapshot`)
- Packet captures
- `report_file_path`
- IP fields unless explicitly approved in a safe design
- Credentials, hashes, tokens, API keys, activation token material
- `internal_notes`, `admin_notes`, stack traces, backend internals
- Unfiltered SOC data

Admin/SOC may have deeper operational views; secrets never in Git or documentation.

---

## 10. Future KB roadmap (KB-037 through KB-060)

| KB | Title |
|---|---|
| KB-037 | Cluster and Appliance Registry Planning |
| KB-038 | Tenant Deployment Mode Model: cloud / on-prem / hybrid |
| KB-039 | Deployment Automation Foundation with Ansible inventory/templates |
| KB-040 | Wazuh Stack VM Deployment Plan |
| KB-041 | Wazuh Stack Installation and Validation |
| KB-042 | Wazuh Agent Onboarding: Windows/Linux |
| KB-043 | Suricata Sensor Deployment Plan |
| KB-044 | Suricata to Wazuh Integration |
| KB-045 | Zeek Sensor Deployment Plan |
| KB-046 | Zeek Log Integration |
| KB-047 | TheHive Deployment Plan |
| KB-048 | Shuffle SOAR Deployment Plan |
| KB-049 | Wazuh to Shuffle to TheHive Workflow |
| KB-050 | MISP Threat Intelligence Deployment Plan |
| KB-051 | Threat Intel Enrichment Workflow |
| KB-052 | Greenbone/OpenVAS Vulnerability Management Plan |
| KB-053 | Vulnerability to Recommendation Workflow |
| KB-054 | Velociraptor DFIR Deployment Plan |
| KB-055 | DFIR Evidence Safety and Case Workflow |
| KB-056 | Admin/SOC Triage Dashboard Enhancements |
| KB-057 | Customer-Safe Live SOC Data Integration |
| KB-058 | On-Prem Appliance Template and Registration |
| KB-059 | Multi-Cluster Capacity and Customer Placement |
| KB-060 | Backup, Monitoring, Upgrade, and Operations Runbook |
| KB-064 | End-to-End Simulation & Integration Testing Milestone |

### Phase grouping

| Phase | Scope |
|---|---|
| Phase 1 | Control plane foundation (KB-010–035) — mostly complete |
| Phase 2 | Architecture roadmap (KB-036) — this module |
| Phase 3 | Registry + deployment mode (KB-037–038) |
| Phase 4 | Deployment automation (KB-039) |
| Phase 5 | Wazuh stack (KB-040–042) |
| Phase 6 | Network detection (KB-043–046) |
| Phase 7 | Case + SOAR (KB-047–049) |
| Phase 8 | Threat intel (KB-050–051) |
| Phase 9 | Vulnerability (KB-052–053) |
| Phase 10 | DFIR (KB-054–055) |
| Phase 11 | SOC ops + live integration (KB-056–057) |
| Phase 12 | On-prem/hybrid + scale + ops (KB-058–060) |
| Phase 13 | E2E simulation & integration test (KB-064) — Linux+Windows agents, attack sims, dashboard proof |

---

## 11. What KB-036 changes (and must not)

### Changes (documentation only)

- `docs/KB036_MSSP_PLATFORM_ARCHITECTURE_ROADMAP.md` (this file)
- `scripts/kb036_validate_mssp_platform_architecture_roadmap.sh`
- `CONTEXT.md`, `AGENTS.md`, `CLAUDE.md`, `.cursor/rules/mssp-control-plane.mdc`
- `docs/AI_PROMPT_LEDGER.md`

### Must not change

- `backend-api/`, `frontend-customer/`, `frontend-admin/` runtime code
- `postgres/init/`, `docker-compose.yml`, `.env`

---

## 12. Validation

```bash
cd /opt/mssp-control
chmod +x scripts/kb036_validate_mssp_platform_architecture_roadmap.sh
./scripts/kb036_validate_mssp_platform_architecture_roadmap.sh
```

Expected final line:

```text
KB-036 MSSP PLATFORM ARCHITECTURE ROADMAP VALIDATION PASSED
```
