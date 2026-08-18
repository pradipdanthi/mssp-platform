# CONTEXT.md — MSSP Control Plane Current Snapshot

Status: Living context file for AI agents and humans.  
Project path: `/opt/mssp-control`  
Host: **VM 100 — `mssp-control`** (`192.168.0.201`) — **production control plane** (same design migrates to cloud later).

**How to use:** Read with `AGENTS.md`, `CLAUDE.md`, and `docs/KB036_MSSP_PLATFORM_ARCHITECTURE_ROADMAP.md` at session start.

**Source of truth hierarchy:** git commits/tags → validation PASS → live source files → this file / AGENTS.md / ledger.

---

## 1. Production posture (enterprise-ready mandate)

| Item | Value |
|---|---|
| Product | **Kestrel Cyber MSSP Control Plane** — Admin/SOC + Customer portals |
| Deployment reality | **On-prem local servers now** = production path for a complete end-to-end MSSP; **not** a disposable lab |
| Quality bar | Every backend tool, adapter wiring, configuration, and security control must be **enterprise-ready** (or an explicit, dated gap with upgrade path) |
| Runtime | Docker Compose on VM 100; frontends are **nginx production builds** (`:3000` / `:3001`) |
| Backend | FastAPI `:8000` — system of record; engines are adapters only |
| Tenant isolation | Customer wrong-tenant → **404**; no raw engine data in customer UI |
| Alert tenant mapping | Fail-closed — Wazuh agent group / binding required (no DEMO default) |
| Shared TheHive org | `THEHIVE_DEFAULT_ORG` default **`MSSP`** (override in `.env` if existing org name differs) |
| Cloud | Same architecture; migrate later — do not invent a second product |
| **Appliance Management (production)** | **VM 114** `kevantic-appliance-mgmt` (`192.168.0.224`) — channel/register/heartbeat edge (KB-093L); Admin/Customer + Postgres stay on VM 100 |
| **Appliance golden image (master clone source)** | Proxmox **VM 199** `mssp-appliance-golden-build` (`192.168.0.225`) — permanent golden disk; improvements commit to repo then bake/update 199; new customer appliances clone from 199. Fleet reporting is in the golden recipe — bake with `kevantic-appliance/scripts/bake_golden_vm199_fleet_reporting.sh` |
| **Appliance image factory (optional mkosi/ISO workshop)** | **VM 113** when needed (KB-093F); may be stopped/destroyed between builds — not the same as golden 199 |
| **KB-093P critical-alert forward** | Baked in golden recipe (`ada21fe`+); Beta field-upgraded; telemetry → VM 100, heartbeat → VM 114 |
| **Host isolate (KB-104)** | **Hold until Un-isolate** (no 2-minute auto-lift). Windows: default-deny except Manager TCP/UDP **1514** and TCP **1515**, plus DHCP/loopback, plus quarantine watchdog. Day-one agent ZIP installs the scripts; appliance heartbeat publishes them to Manager shared groups. Bake into VM **199** with `kevantic-appliance/scripts/bake_golden_vm199_fleet_reporting.sh`. Isolate buttons travel **VM 100 → VM 114 channel → appliance Manager → agent**. Do not use unsigned WPK as the update path. |
| **KB-094 production portability** | Env templates (`deploy/environments/`), `production_deploy_control_plane.sh`, release checklist — cloud-agnostic deploy path. **KB-105** is wired in: Sysmon cache before image build; Linux Manager rules playbook after Wazuh. |

**Do not** treat this platform as a lab prototype in planning, user-facing copy, dashboards, or runtime defaults. Lab shortcuts need explicit user acceptance + upgrade plan.

### Vulnerability scanning note (KB-078)

| Item | Value |
|---|---|
| **Primary free stack ($0)** | **Nuclei + Vuls** on **VM 109** `/opt/mssp-vuln-free` (with Greenbone CE) — see KB-078 |
| Greenbone Community (VM 109) | Optional classic NVT backup — co-located; no customer UI |
| Control plane (VM 100) | **No** scanner engines — adapters/API only |
| Greenbone Enterprise | **Deferred** until ~5–10 customers (KB-077) — no paid license yet |
| Product path | Scan → normalize (`nuclei`/`vuls`/`greenbone`) → Admin triage/promote → customer-safe recommendations |

---

## 2. Latest validated feature baseline

| Item | Value |
|---|---|
| Latest feature tag | **KB-105 Linux mid-layer EDR** — commits `ffe9f07` + `4e8841d` (tag `kb105-linux-midlayer-edr-validated` is on `ffe9f07`; retag after this portability rework if requested). Isolate standard remains **KB-104** `kb104-isolate-standard-golden-validated` (hold until Un-isolate). Historical UI baseline: **KB-035** Customer Appliance Detail (`1ac1df3`) |
| Post-KB-035 stack (git) | **KB-083/084 EDR** committed through `73376d6`; **KB-088 snapshot** (user mgmt, portal auth, `/assets` SPA, Windows telemetry) — see `docs/KB088_USER_MGMT_PORTAL_AUTH_WINDOWS_TELEMETRY.md` |
| Roadmap docs | **KB-036–KB-060** (+ later ops/integration KBs) |
| Active branch (typical) | `main` (control plane VM 100) |
| Engine provisioning | **KB-072** Tenant Engine Provisioning (Wazuh group + TheHive org/tag) |
| Tenant deployment mode | **KB-073** — cloud with/without appliance, on-prem with/without appliance, hybrid |
| Contract-ready onboard | **KB-075** — entitlements + engines + required portal admin on create |
| Vuln path | **KB-078** Nuclei+Vuls free stack (primary); **KB-068–070** Greenbone CE optional; **KB-076** upgrade requests; **KB-077** Enterprise deferred |
| Windows monitoring bar | Agent enroll **+** Sysmon/4688 telemetry bootstrap (package or `scripts/bootstrap_windows_telemetry.ps1`) — agent alone is not process-EDR ready. Cloud: `production_deploy_control_plane.sh` caches `Sysmon64.exe` (gitignored) so ZIPs embed it. |
| Linux mid-layer EDR (KB-105) | auditd execve (`key=mssp_exec`) + Manager rules 110001–110005 + `log_format=audit`. Cloud: `playbooks/mssp-linux-midlayer-manager.yml` (any `[wazuh_stack]` host). Lab: `scripts/kb105_apply_linux_midlayer_manager.sh`. Proof: `python3 scripts/verify_e2e_midlayer_edr.py`. |
| Portal auth | Admin `:3000` = staff roles only; Customer `:3001` = customer roles only (`portal` on login) |

---

## 3. Running services (VM 100)

| Container | Role |
|---|---|
| `mssp-postgres` | PostgreSQL |
| `mssp-redis` | Redis |
| `mssp-backend-api` | FastAPI port **8000** |
| `mssp-frontend-admin` | Admin/SOC UI port **3000** (nginx) |
| `mssp-frontend-customer` | Customer portal port **3001** (nginx) |

### Connected security engines

| VM | Host | Purpose | State |
|---|---|---|---|
| 101 | `wazuh-stack` (`192.168.0.211`) | Wazuh Manager/Indexer/Dashboard | Live 4.14.6 |
| 102 | `thehive_shuffle` (`192.168.0.212`) | TheHive + Shuffle | Live |
| 105 | Linux endpoint lab | **Decommissioned** (2026-07-29) — Proxmox VM destroyed; reinstall Ubuntu manually when ready | — |
| 106 | `suricata-sensor` (`192.168.0.216`) | Suricata IDS + Wazuh agent | Live |
| 109 | `greenbone` (`192.168.0.219`) | Greenbone CE + **Nuclei + Vuls** (`/opt/mssp-vuln-free`) | Live — scanners co-located; Enterprise deferred (KB-077) |
| 112 | `automation` (`192.168.0.222`) | Ansible controller | Ready |

---

## 4. Customer portal safety (unchanged)

Customer portal must never expose raw logs, raw engine alerts, raw JSON, packet captures, credentials, hashes, tokens, API keys, internal notes, or unfiltered SOC data. Customer UI never calls `/admin`.

---

## 5. Key paths

| Path | Purpose |
|---|---|
| `docs/KB088_USER_MGMT_PORTAL_AUTH_WINDOWS_TELEMETRY.md` | Redeploy snapshot: user mgmt, portal auth, SPA, Windows telemetry |
| `docs/KB036_MSSP_PLATFORM_ARCHITECTURE_ROADMAP.md` | Enterprise roadmap |
| `docs/KB072_TENANT_ENGINE_PROVISIONING.md` | Tenant → engine binding |
| `docs/KB077_GREENBONE_ENTERPRISE_READINESS_PLAN.md` | Vuln scanner enterprise gaps + phases |
| `AGENTS.md` | Full rulebook |
| `docs/AI_PROMPT_LEDGER.md` | Change ledger |
| `docker-compose.yml` | Production Compose stack |
