# KB-060 — Backup, Monitoring, Upgrade, and Operations Runbook

Status: Implemented (pending validation/commit).  
Module type: **Planning / documentation only** — no runtime code, schema, compose, or `.env` changes.

Builds on: `docs/KB036_MSSP_PLATFORM_ARCHITECTURE_ROADMAP.md` (**Phase 12**), `docs/KB037_CLUSTER_APPLIANCE_REGISTRY_PLANNING.md`, `docs/KB059_MULTI_CLUSTER_CAPACITY_CUSTOMER_PLACEMENT.md`.  
Related: KB-039 (Ansible automation), KB-041 (Wazuh install validation), control plane on **VM 100**.

---

## 1. Purpose

Provide an **operations runbook** for the MSSP platform covering:

- **VM 111** (`monitoring`) — Prometheus/Grafana platform health
- **Backup and restore** for PostgreSQL and the control plane
- **Upgrade** procedures for control plane and (later) SOC stack components
- **Proxmox snapshot** guidance for lab and production-like change windows

This KB is **runbook / planning only**. It does not install Prometheus, Grafana, backup agents, or change running containers.

---

## 2. Current baseline

| Area | Status |
|---|---|
| VM 100 `mssp-control` | Deployed — FastAPI, PostgreSQL, Redis, admin/customer UIs |
| VM 111 `monitoring` | Roadmap placeholder — **not deployed** |
| Automated DB backups | Not standardized in-repo — design in this KB |
| Upgrade automation | Partial (Compose/Ansible future) — runbook here |
| Proxmox snapshots | Lab practice (user-driven) — guidance only |
| SOC stack VMs 101–110 | Not deployed |

---

## 3. Phase 12 context (KB-036)

KB-036 **Phase 12** = on-prem/hybrid + scale + ops:

| KB | Focus |
|---|---|
| KB-058 | On-prem appliance template and registration |
| KB-059 | Multi-cluster capacity and customer placement |
| **KB-060** | Backup, monitoring, upgrade, and operations runbook |

Parent doc: `docs/KB036_MSSP_PLATFORM_ARCHITECTURE_ROADMAP.md` §10 Phase 12.

---

## 4. VM 111 — monitoring (Prometheus / Grafana)

### 4.1 Role

| Item | Plan |
|---|---|
| VM | **VM 111** `monitoring` |
| Stack | Prometheus (metrics scrape) + Grafana (dashboards) |
| Scope | Platform health: control plane (VM 100), later SOC clusters, sensors, DFIR |
| Audience | Admin/SOC operators only — **not** customer portal |

### 4.2 Suggested metric targets (future)

| Target | Examples |
|---|---|
| Control plane | API `/health`, container up, Postgres connections, Redis ping, disk |
| `soc_clusters` | Agent count vs `max_agents`, EPS vs budget, indexer disk, sync health |
| Appliances | Heartbeat age, `sync_health_status` rollups (metadata only) |
| Future engines | Wazuh Manager, Suricata, Zeek, TheHive, Shuffle, MISP, Greenbone, Velociraptor |

### 4.3 Safety

- Grafana/Prometheus UIs are **admin/ops only** — never exposed as customer product UI.
- Dashboards must not embed secrets, JWT material, or customer PII in panel titles/queries committed to Git.
- Alerting channels (email/Slack/etc.) configured via secret store / env — **no secrets** in this runbook or Git.

### 4.4 Deploy note

Create VM 111 and install monitoring **only** when an implementation KB explicitly approves it. This document is the ops design, not the install ticket.

---

## 5. Backup and restore

### 5.1 What to protect (control plane)

| Asset | Location (typical) | Priority |
|---|---|---|
| **PostgreSQL** | `mssp-postgres` volume / data dir | **Critical** — system of record |
| Redis | `mssp-redis` | Cache/queue — rebuildable; optional snapshot |
| Compose / app config | `/opt/mssp-control` (excluding `.env`) | High — code + templates |
| **Secrets** | `.env` / vault only | Critical — backup offline encrypted; **never commit** |
| Container images | Registry / Compose pins | Medium — pin versions for restore |

SOC cluster data (Wazuh Indexer, TheHive, etc.) gets **separate** backup policies when those VMs exist — do not assume control-plane backup covers engine raw logs.

### 5.2 PostgreSQL backup sketch (ops procedure)

**Backup (logical dump — preferred for portability):**

```bash
# Example pattern only — adjust container name/paths; never paste real passwords into docs or tickets.
cd /opt/mssp-control
docker compose exec -T mssp-postgres \
  pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc \
  > "/var/backups/mssp/postgres/mssp_$(date -u +%Y%m%dT%H%M%SZ).dump"
```

**Restore (destructive — confirm snapshot first):**

1. Take Proxmox snapshot of VM 100 (see §7).
2. Stop API writers if possible (`mssp-backend-api`) to reduce write race.
3. Restore dump into empty or replaced database using `pg_restore` (exact flags in implementation KB).
4. Restart services; verify `curl -fsS http://localhost:8000/health`.
5. Spot-check tenant isolation with known admin validation scripts.

Store dumps on **off-VM** storage when possible. Encrypt at rest. Retention policy: daily / weekly / monthly tiers (exact schedule set by ops policy — not hardcoded secrets).

### 5.3 Control plane config backup

- Back up Git-tracked tree via normal Git + tagged releases.
- Back up `.env` separately to encrypted offline media — **never** into Git, chat, or this document.
- Document restore: clone tagged release → restore `.env` from secure store → `docker compose up` → health check.

### 5.4 Verification

After every restore drill:

```bash
cd /opt/mssp-control
docker compose ps
curl -fsS http://localhost:8000/health | jq .
```

Expected: API, database, and Redis healthy. Then run the newest relevant `scripts/kb0NN_validate_*.sh` for the area under test.

---

## 6. Upgrade runbook

### 6.1 Principles

- **Validate before commit; snapshot before risky upgrades.**
- Upgrade one layer at a time (control plane app → Postgres minor → Redis → later SOC engines).
- Never upgrade production without a rollback path (Proxmox snapshot + DB dump).
- Pin dependency versions (`requirements.txt`, image tags) — avoid floating `latest` in production.

### 6.2 Control plane (VM 100) upgrade sketch

1. Confirm clean Git state and known-good tag.
2. Proxmox snapshot VM 100 (+ optional DB dump §5.2).
3. Pull/checkout approved release tag.
4. Apply migrations **only** if the KB explicitly ships them under `postgres/init/` or documented migration path.
5. Rebuild/recreate affected Compose services **when the change KB instructs** (do not restart casually).
6. Run `/health` + module validation script.
7. If failure: restore snapshot / dump; open incident; do not force-forward.

### 6.3 SOC stack upgrades (future)

When VMs 101–110 exist: upgrade Manager/Indexer/sensors per vendor notes, then re-validate adapters (KB-057+) and cluster capacity (KB-059). Monitoring on **VM 111** should show health before and after.

### 6.4 Ansible (KB-039)

Use inventory/templates for repeatable upgrades; inject secrets via Ansible Vault / secret store — **no secrets** in playbooks committed to Git.

---

## 7. Proxmox snapshot guidance

| When | Action |
|---|---|
| Before schema/migration KBs | Snapshot VM 100 |
| Before Compose/image upgrades | Snapshot VM 100 |
| Before restore drills | Snapshot so drills are reversible |
| After validated KB commit + tag | Optional named snapshot (lab habit) |
| Before creating/changing VMs 101–111 | Snapshot hypervisor change set if policy requires |

### 7.1 Lab naming sketch

```text
vm100-pre-<kbNN>-<YYYYMMDD>
vm100-post-<kbNN>-validated-<YYYYMMDD>
```

### 7.2 Rules

- Snapshots are **not** a substitute for off-box PostgreSQL backups.
- Do not keep unlimited snapshots — prune per storage policy.
- Document who took the snapshot and why (ops ticket) — no credentials in ticket bodies.

---

## 8. Day-2 operations checklist (summary)

| Cadence | Task |
|---|---|
| Continuous | VM 111 alerts on API/DB/disk/cluster headroom |
| Daily | Confirm Postgres backup job succeeded |
| Weekly | Restore drill on non-prod or lab copy |
| Per change | Snapshot → change → validate → tag |
| Capacity | Review KB-059 headroom; open new cluster before `full` |
| Security | Rotate credentials via vault; never commit `.env` |

---

## 9. Customer and security boundaries

- Ops dashboards, backup paths, restore commands, and cluster internals are **admin/ops only**.
- Customer portal never exposes backup status, monitoring URLs, snapshot names, or raw engine metrics.
- **No secrets** in this runbook: no real passwords, API keys, tokens, JWT values, or connection strings.
- Tenant isolation remains enforced in application code — backups must be restored with the same isolation assumptions (do not share DB dumps across untrusted environments without scrubbing).

---

## 10. Explicit deferrals

| Item | Deferred to |
|---|---|
| Install Prometheus/Grafana on VM 111 | Future implementation KB |
| Automated backup cron in-repo | Future ops implementation KB |
| Managed restore UI | Out of scope for v1 |
| Engine-specific backup (Wazuh Indexer, TheHive, …) | Per-tool KB + this runbook extension |
| On-prem appliance remote backup | **KB-058** + customer policy |

---

## 11. Validation

```bash
cd /opt/mssp-control
chmod +x scripts/kb060_validate_backup_monitoring_upgrade_operations_runbook.sh
./scripts/kb060_validate_backup_monitoring_upgrade_operations_runbook.sh
```

Expected success line:

```text
KB-060 BACKUP MONITORING UPGRADE OPERATIONS RUNBOOK VALIDATION PASSED
```

---

## 12. What KB-060 changes (and must not)

### Changes (documentation only)

- `docs/KB060_BACKUP_MONITORING_UPGRADE_OPERATIONS_RUNBOOK.md` (this file)
- `scripts/kb060_validate_backup_monitoring_upgrade_operations_runbook.sh`

### Must not change

- `backend-api/`, `frontend-customer/`, `frontend-admin/` runtime code
- `postgres/init/`, `docker-compose.yml`, `.env`
- No container restarts, no monitoring VM creation, no live backup job install in this module
