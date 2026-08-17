# KB-094 — Production Portability Pack (cloud-agnostic)

Status: Implemented (docs + scripts + env templates).  
Module type: **Deployment automation foundation** — no schema, compose, or `.env` changes.  
Builds on: KB-020 (production bootstrap), KB-039 (Ansible foundation), KB-060 (ops runbook), `DOCS/CURSOR_REDEPLOYMENT_PLAYBOOK.md`, KB-093P (appliance golden).

---

## 1. Purpose

So **cloud provider choice day** is mostly “fill config + run scripts,” not redo weeks of manual wiring.

Four layers (unchanged recipe, swappable config):

| Layer | What | KB-094 deliverable |
|-------|------|-------------------|
| **1. Recipe** | Git: code, SQL, Compose, Ansible, golden appliance | Already in repo |
| **2. Config** | `.env` + `.secrets/` per environment | `deploy/environments/*.example.env` |
| **3. Automation** | One-command control plane + engine orchestrator | `scripts/production_deploy_*.sh` |
| **4. Proof** | Validators + release checklist + git tag | `deploy/RELEASE_CHECKLIST.md`, `kb094_validate_*.sh` |

**Cloud-agnostic rule:** AWS, Azure, and GCP only change **hostnames, IPs, and TLS** in Layer 2. The same git tag deploys everywhere.

---

## 2. What you run (operator cheat sheet)

### Lab (VM 100) — after code changes

```bash
cd /opt/mssp-control
./scripts/production_deploy_control_plane.sh
```

### Production / cloud — first control plane

1. Ubuntu host + Docker
2. `git clone` + checkout **release tag**
3. `cp deploy/environments/control-plane.production.example.env .env` → fill secrets
4. Populate `.secrets/` from vault
5. `./scripts/production_deploy_control_plane.sh`
6. `./scripts/bootstrap_platform_admin.sh` (KB-020)
7. Engines: fill `ansible/inventory/production.example.yml` → sync → playbooks (see `ansible/README.md`)

### Engines (dry-run default)

```bash
./scripts/production_deploy_engines.sh
# When approved:
MSSP_ENGINE_DEPLOY_APPROVED=1 ./scripts/production_deploy_engines.sh
```

---

## 3. Golden appliance (VM 199)

| Item | Lab |
|------|-----|
| Master golden disk | Proxmox **VM 199** `mssp-appliance-golden-build` |
| New customer appliance | Clone from 199 → register → entitlements |
| Improvements | Commit to git → update/rebuild 199 → future clones inherit |
| Fleet reporting (day one) | Heartbeat uses `python3 -m … heartbeat` (agent inventory), CLI sends CPU/mem/disk + `enabled_services`, `/etc/kevantic/image-release.json` stamps version. Bake live disk: `kevantic-appliance/scripts/bake_golden_vm199_fleet_reporting.sh`. Future full rebuilds inherit via `kevantic_runtime` Ansible. Do **not** seed lab entitlements on 199. |

Optional mkosi factory **VM 113** is a workshop, not the golden customers clone from.

---

## 4. Appliance → control plane routing (locked)

| Traffic | Lab target |
|---------|------------|
| Register / heartbeat / channel | VM **114** (`192.168.0.224`) |
| High/critical alert telemetry | VM **100** (`/api/v1/telemetry/ingest`) |

Documented in `docs/KB093P_APPLIANCE_CRITICAL_ALERT_FORWARD.md`.

---

## 5. Disaster recovery alignment

| Path | When |
|------|------|
| **Path A** | USB cold copy of `/opt/mssp-control` + `.enc` DB |
| **Path B** | Git tag + secrets/DB from backup |

KB-094 scripts are the **normal** deploy path; DR playbook is the **disaster** path. Both use the same Compose stack.

See `DOCS/CURSOR_REDEPLOYMENT_PLAYBOOK.md`.

---

## 6. Files added by KB-094

```text
deploy/
├── RELEASE_CHECKLIST.md
└── environments/
    ├── README.md
    ├── control-plane.lab.example.env
    ├── control-plane.production.example.env
    ├── engines.lab.example.env
    └── engines.production.example.env
ansible/inventory/production.example.yml
scripts/
├── production_deploy_control_plane.sh
├── production_deploy_engines.sh
└── kb094_validate_production_portability_pack.sh
docs/KB094_PRODUCTION_PORTABILITY_PACK.md   # this file
```

---

## 7. Explicit non-goals (this KB)

- No Terraform / Kubernetes / managed-cloud modules (future KB when provider is chosen)
- No automatic tear-down of engine VMs
- No commit of real `.env` or `.secrets/`
- No change to customer/admin product features

---

## 8. Validate

```bash
cd /opt/mssp-control
./scripts/kb094_validate_production_portability_pack.sh
```

---

## 9. Related KBs

| KB | Topic |
|----|--------|
| KB-020 | Production bootstrap, no demo seed |
| KB-039 | Ansible layout |
| KB-060 | Backup / upgrade runbook |
| KB-073 | Tenant deployment modes |
| KB-093P | Appliance forwarder + golden 199 |
| KB-036 | Enterprise roadmap |
