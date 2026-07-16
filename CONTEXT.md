# CONTEXT.md — MSSP Control Plane Current Snapshot

Status: Living context file for AI agents and humans. Refreshed in **KB-036** (Enterprise Platform Architecture Roadmap).  
Project path: `/opt/mssp-control`  
VM: **100 — `mssp-control`** (`192.168.0.201`)

**How to use:** Read with `AGENTS.md`, `CLAUDE.md`, and `docs/KB036_MSSP_PLATFORM_ARCHITECTURE_ROADMAP.md` at session start.

**Source of truth hierarchy:** git commits/tags → validation PASS → live source files → this file / AGENTS.md / ledger.

---

## 1. Latest validated feature baseline

| Item | Value |
|---|---|
| Latest validated feature KB | **KB-035** — Customer Appliance Detail UI |
| Commit | **`1ac1df3`** |
| Tag | **`kb035-customer-appliance-detail-validated`** |
| Active docs module | **KB-037** — Cluster and appliance registry planning (docs only) |
| Architecture baseline | **KB-036** — `kb036-mssp-platform-architecture-roadmap-validated` (`c39fddc`) |

---

## 2. Enterprise platform vision (not a Wazuh dashboard)

We are building a **strong enterprise-style open-source MSSP / SOC / MDR / XDR platform**.

Monitoring and response scope includes: endpoints, servers, network traffic, firewalls/network devices, applications, cloud/on-prem environments, alerts, incidents/cases, vulnerabilities, threat intelligence, automation/playbooks, and customer reporting.

**MSSP Control Plane** (FastAPI + PostgreSQL + Redis + admin/customer UIs) is the product. Open-source engines are **backend adapters only**.

Full roadmap: `docs/KB036_MSSP_PLATFORM_ARCHITECTURE_ROADMAP.md`

---

## 3. Enterprise capability stack (planned — mostly not deployed yet)

| Layer | Tools |
|---|---|
| Control plane | FastAPI, PostgreSQL, Redis, admin + customer dashboards (**deployed VM 100**) |
| SIEM / endpoint | Wazuh Manager/API, Wazuh Indexer/OpenSearch, Wazuh Dashboard, Wazuh Agents |
| Network / NDR | Suricata, Zeek |
| Case management | TheHive, Cortex (if needed) |
| SOAR | Shuffle |
| Threat intel | MISP (OpenCTI future optional) |
| Vulnerability | Greenbone / OpenVAS |
| DFIR | Velociraptor, osquery (optional) |
| Deployment automation | Ansible + Docker Compose first; Terraform later; K8s future optional |
| Observability | Prometheus/Grafana (or equivalent) |

**Critical:** The real SOC stack has **not deployed yet**. No live ingestion adapters. Data is mostly app/database-driven today.

---

## 4. Deployment models

### A. Cloud-hosted MSSP

Shared SOC clusters; multiple customers per cluster by **capacity** (agents, EPS, GB/day, retention, performance, isolation) — not a fixed customer count.

### B. On-prem appliance

Logs stay on customer site; appliance runs local stack; only **safe metadata** syncs to control plane.

### C. Hybrid

Mixed on-prem processing + central sync; some customers on dedicated cloud clusters.

### Normalization rule

Control plane consumes **normalized, tenant-scoped records** regardless of source (Wazuh, Suricata, Zeek, TheHive, Shuffle, MISP, Greenbone, Velociraptor, on-prem appliance, etc.).

Record concepts: `tenant`, `source_platform`, `asset`, `alert`, `incident`/`case`, `recommendation`, `vulnerability`, `report`, `visibility_status`, `sync_health_status`.

---

## 5. Planned VM layout

| VM | Name | Purpose | Status |
|---|---|---|---|
| **VM 100** | `mssp-control` | Control Plane (`192.168.0.201`) | **Deployed** |
| **VM 101** | `wazuh-stack` | Wazuh Manager, Indexer/OpenSearch, Dashboard | Future |
| **VM 102** | `thehive` | TheHive (+ Cortex if needed) | Future |
| **VM 103** | `shuffle` | SOAR | Future |
| **VM 104** | `windows-endpoint-lab` | Windows + Wazuh Agent | Future |
| **VM 105** | `linux-endpoint-lab` | Linux + Wazuh Agent | Future |
| **VM 106** | `suricata-sensor` | Suricata IDS/IPS | Future |
| **VM 107** | `zeek-sensor` | Zeek NSM | Future |
| **VM 108** | `misp` | MISP threat intel | Future |
| **VM 109** | `greenbone` | Greenbone/OpenVAS | Future |
| **VM 110** | `velociraptor` | DFIR | Future |
| **VM 111** | `monitoring` | Prometheus/Grafana | Future |

Do not install SOC tools on VM 100 or create VMs 101–111 until the matching KB is approved.

Future: **cluster registry**, **appliance registry**, **deployment automation** (KB-037–039).

---

## 6. Running services (VM 100)

| Container | Role |
|---|---|
| `mssp-postgres` | PostgreSQL |
| `mssp-redis` | Redis |
| `mssp-backend-api` | FastAPI port **8000** |
| `mssp-frontend-admin` | Admin/SOC UI port **3000** |
| `mssp-frontend-customer` | Customer portal port **3001** |

---

## 7. Control plane — what is built today

### Admin / SOC (KB-010–020, KB-016/017)

Auth/RBAC, tenant/user/appliance admin APIs, activation tokens, appliance registration/heartbeat, credential rotation, admin frontend foundation.

### Customer portal (KB-021–035)

Dashboard v2; alerts/incidents/assets/appliances/reports/recommendations (list + detail); notifications; account hardening. **No `/admin` calls.**

---

## 8. Customer data safety

Customer portal must never expose: raw logs, raw Wazuh/Suricata/Zeek alerts, raw JSON, packet captures, credentials, hashes, tokens, API keys, internal/admin notes, stack traces, unfiltered SOC data.

---

## 9. Future KB roadmap (after KB-036)

KB-037 through KB-060 — see `docs/KB036_MSSP_PLATFORM_ARCHITECTURE_ROADMAP.md`.

Examples: **KB-037** cluster/appliance registry planning (in progress), KB-038 deployment mode, KB-039 Ansible automation, KB-040–042 Wazuh, KB-043–046 Suricata/Zeek, KB-047–049 TheHive/Shuffle, KB-050–051 MISP, KB-052–053 Greenbone, KB-054–055 Velociraptor, KB-056–057 SOC ops + live integration, KB-058–060 on-prem/scale/ops.

User must explicitly kick off each KB. **No tool installs until approved.**

---

## 10. Roadmap phases (summary)

| Phase | Theme |
|---|---|
| Phase 1 | Control plane foundation (KB-010–035) — mostly complete |
| Phase 2 | Architecture roadmap (KB-036) — this docs module |
| Phase 3–12 | Registry, automation, Wazuh, network sensors, case/SOAR, intel, vuln, DFIR, SOC ops, on-prem/scale/ops (KB-037–060) |

Phase 12 covers on-prem appliance, multi-cluster placement, and operations runbooks (KB-058–060).

---

## 11. Safe KB workflow

**Planning before implementation** · **no .env** · **no /admin** from customer UI · **validation before commit**

KB-036 validation success line:

```text
KB-036 MSSP PLATFORM ARCHITECTURE ROADMAP VALIDATION PASSED
```

---

## 12. Key paths

| Path | Purpose |
|---|---|
| `docs/KB036_MSSP_PLATFORM_ARCHITECTURE_ROADMAP.md` | Enterprise architecture roadmap |
| `scripts/kb036_validate_mssp_platform_architecture_roadmap.sh` | KB-036 docs gate |
| `AGENTS.md` | Full rulebook |
| `docs/AI_PROMPT_LEDGER.md` | Change ledger |
