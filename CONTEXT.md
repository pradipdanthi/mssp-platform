# CONTEXT.md — MSSP Control Plane Current Snapshot

Status: Living context file for AI agents and humans. Refreshed after **KB-039–KB-060** overnight batch.  
Project path: `/opt/mssp-control`  
VM: **VM 100 — `mssp-control`** (`192.168.0.201`)

**How to use:** Read with `AGENTS.md`, `CLAUDE.md`, and `docs/KB036_MSSP_PLATFORM_ARCHITECTURE_ROADMAP.md` at session start.

**Source of truth hierarchy:** git commits/tags → validation PASS → live source files → this file / AGENTS.md / ledger.

---

## 1. Latest validated baseline

| Item | Value |
|---|---|
| Latest feature baseline | **KB-035** — Customer Appliance Detail UI (`1ac1df3`, `kb035-customer-appliance-detail-validated`) |
| Architecture / registry planning | **KB-036–KB-038** (docs) |
| Active overnight branch | `kb039-kb060-platform-roadmap-execution` |
| Roadmap execution | **KB-039 through KB-060** committed on that branch |
| Aggregate tag | `kb039-kb060-roadmap-batch-complete` (`f7ff691`) |
| Latest automation commit | KB-061 SOC sync (uncommitted); prior KB-049 `8297db6` |
| VM 100 snapshots | `kb060-ok`, `kb041-ok` |
| VM 101 | **Wazuh 4.14.6 installed** — `192.168.0.211` |
| VM 102 | **TheHive + Shuffle co-located** — `thehive_shuffle` / `192.168.0.212` / **16 GB**; UI :9000 / :3001 |
| VM 105 | **Wazuh agent 001** Active |
| VM 106 | **Suricata + Wazuh agent 002** Active; rule 86601 proof |
| VM 112 | **Ansible controller** `192.168.0.222` |
| VM 109 | **Greenbone Community Edition live** — `greenbone` / `192.168.0.219` / **9 GB**; GSA `https://192.168.0.219` (KB-068) |
| Active preparation | **KB-068 Greenbone live** + **KB-069 control-plane vuln adapter** (Admin Vulnerabilities + promote). |

---

## 2. What KB-039–KB-060 delivered

### Docs / planning / Ansible (no live SOC tool installs)

| KB | Summary |
|---|---|
| KB-039 | Ansible foundation (`ansible/` inventory VMs 100–111, stub playbooks) |
| KB-040–042 | Wazuh VM plan, KB-041 safe-default install role, agent onboarding stubs |
| KB-043–046 | Suricata / Zeek plans + integration plans |
| KB-047–049 | TheHive, Shuffle, Wazuh→Shuffle→TheHive workflow plans |
| KB-050–051 | MISP + threat-intel enrichment plans |
| KB-052–053 | Greenbone + vulnerability→recommendation plans |
| KB-054–055 | Velociraptor + DFIR evidence safety plans |
| KB-059 | Multi-cluster capacity / customer placement plan |
| KB-060 | Backup, monitoring (VM 111), upgrade, ops runbook |

### Control-plane code (runtime)

| KB | Summary |
|---|---|
| KB-056 | Admin SOC triage: alert/incident detail, PATCH triage, comments, list filters, admin UI detail pages |
| KB-057 | `POST /appliance/alerts` — customer-safe normalized ingest (appliance API key auth) |
| KB-058 | On-prem appliance template (`templates/on-prem-appliance/`) + admin download API/UI |

**Still not done:** creating remaining VMs 103–104 / 107–108 / 110–111; installing Zeek
(deferred), MISP, Velociraptor, etc.; or schema for `soc_clusters` /
`deployment_mode`. KB-049 auto-ticket and KB-061 TheHive→control-plane sync API
are live in lab (customer visibility still SOC-approved via KB-056).

**Greenbone status:** VM 109 Community Edition live (`https://192.168.0.219`).
KB-069 adapter + **KB-070 instant Task-Done hook** on VM 109 (`:9271`) plus
on-demand puller. Admin can promote to recommendations. Customer portal never
receives raw Greenbone data.

**Wazuh status:** VM 101 has Wazuh Manager, Indexer, Dashboard, and Filebeat
**4.14.6-1** installed and validated. Credentials remain root-only on VM 101
(`/root/wazuh-install/wazuh-install-files.tar`, mode `600`). Never print them
into Git or docs. VM 105 agent **001** is Active with detection proof.

**Suricata status:** VM 106 has Suricata **7.0.3** passive IDS with reversible
VM 105 traffic mirror. Wazuh agent **002** (`suricata-sensor`) tails
`/var/log/suricata/eve.json` into Manager; proof alert rule **86601**.

**Next safe action:** Resume KB-064 Phase A / Windows agent / MISP / Velociraptor,
or next SOC tool KB. Keep customer_visible SOC-gated.

**E2E milestone doc:** `docs/KB064_E2E_SIMULATION_INTEGRATION_TEST_MILESTONE.md`

---

## 3. Running services (VM 100)

| Container | Role |
|---|---|
| `mssp-postgres` | PostgreSQL |
| `mssp-redis` | Redis |
| `mssp-backend-api` | FastAPI port **8000** (rebuilt for KB-056–058) |
| `mssp-frontend-admin` | Admin/SOC UI port **3000** (rebuilt) |
| `mssp-frontend-customer` | Customer portal port **3001** |

### Infrastructure hosts

| VM | Host | Purpose | State |
|---|---|---|---|
| 101 | `wazuh-stack` (`192.168.0.211`) | Wazuh Manager/Indexer/Dashboard | Wazuh 4.14.6 live |
| 102 | `thehive_shuffle` (`192.168.0.212`) | TheHive + Shuffle (co-located) | Live :9000 / :3001; KB-049 auto-ticket validated |
| 105 | `linux-endpoint-lab` (`192.168.0.215`) | Linux agent lab | Agent 001 Active |
| 106 | `suricata-sensor` (`192.168.0.216`) | Suricata passive IDS + Wazuh agent | Suricata 7.0.3 live; Wazuh agent 002 Active |
| 112 | `automation` (`192.168.0.222`) | Ansible controller | Ansible Core ready |

---

## 4. Customer portal safety (unchanged)

Customer portal must never expose raw logs, raw engine alerts, raw JSON, packet captures, credentials, hashes, tokens, API keys, internal notes, or unfiltered SOC data. Customer UI never calls `/admin`.

---

## 5. Morning checklist (for the human)

1. Review branch: `git log --oneline kb038-tenant-deployment-mode-planning-validated..HEAD`
2. KB-056 live triage validation — **PASSED**
3. Confirm health: `curl -fsS http://localhost:8000/health | jq .`
4. **One Proxmox snapshot** (on Proxmox host, not inside VM):
   ```bash
   qm snapshot 100 kb060-ok
   ```

---

## 6. Key paths

| Path | Purpose |
|---|---|
| `docs/KB036_MSSP_PLATFORM_ARCHITECTURE_ROADMAP.md` | Enterprise roadmap |
| `ansible/` | Deployment automation stubs |
| `templates/on-prem-appliance/` | On-prem template placeholders |
| `scripts/kb039_kb060_validate_all.sh` | Master docs+module runner |
| `AGENTS.md` | Full rulebook |
| `docs/AI_PROMPT_LEDGER.md` | Change ledger |
