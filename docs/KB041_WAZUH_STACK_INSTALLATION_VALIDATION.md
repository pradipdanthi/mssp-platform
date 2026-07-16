# KB-041 — Wazuh Stack Installation and Validation

Status: Infrastructure automation prepared; live execution requires separate approval.
Branch: `kb039-kb060-platform-roadmap-execution`  
Module type: **Infrastructure automation** — **NOT** a live Wazuh install.

Builds on: `docs/KB036_MSSP_PLATFORM_ARCHITECTURE_ROADMAP.md`, `docs/KB037_CLUSTER_APPLIANCE_REGISTRY_PLANNING.md`, `docs/KB038_TENANT_DEPLOYMENT_MODE_PLANNING.md`, `docs/KB039_DEPLOYMENT_AUTOMATION_FOUNDATION.md`, and `docs/KB040_WAZUH_STACK_VM_DEPLOYMENT_PLAN.md`.

---

## 1. Purpose

Provide a safe, version-pinned Ansible role and playbook
(`ansible/playbooks/wazuh-stack-install.yml`) for preflighting, installing, and
validating the Wazuh stack on **VM 101 (`wazuh-stack`)**.

The automation defaults to **preflight only**. This preparation pass does
**not** contact Proxmox, create VM 101, or install Wazuh. Live execution remains
blocked until the user gives separate approval, VM 101 exists, a pre-install
snapshot exists, and the official installer digest has been verified.

---

## 2. VM reference

| Field | Value |
|---|---|
| **VM** | 101 — `wazuh-stack` |
| **Target group** | `wazuh_stack` in `ansible/inventory/hosts.yml` |
| **Components** | Wazuh Manager, Indexer/OpenSearch, Dashboard |

---

## 3. Prepared automation

File: `ansible/playbooks/wazuh-stack-install.yml`

Role: `ansible/roles/wazuh_stack/`

The role provides three explicit modes:

| Mode | Behavior |
|---|---|
| `preflight` | Default. Checks VM identity, OS, architecture, RAM, disk, and current listeners. Makes no package changes. |
| `install` | Runs only when `wazuh_live_install_approved=true` and a verified 64-character SHA-256 digest is supplied. |
| `validate` | Verifies pinned package versions, services, and local listeners on an existing installation. |

The pinned release for this preparation is **Wazuh 4.14.6** (official release,
1 July 2026). The official 4.14 installation assistant performs the all-in-one
deployment of Manager, Indexer, Dashboard, and Filebeat. The role disables the
Wazuh APT repository afterward to prevent an accidental unreviewed upgrade.

### 3.1 Safety interlocks

- Safe defaults: `wazuh_execution_mode=preflight` and
  `wazuh_live_install_approved=false`.
- Installation is limited to inventory `vm_id=101` with
  `deployment_role=wazuh_cluster`.
- Installer SHA-256 must be verified out-of-band immediately before deployment.
- Installer output uses `no_log: true` because the official assistant generates
  credentials.
- Generated credentials remain root-only on VM 101 and must be transferred to
  the approved secrets system; **no secrets in Git**.
- A successful installation marker is written only after package, service, and
  listener validation passes.

**Do not run this playbook against VM 101 until provisioning, Vault/secrets
handling, and a pre-install snapshot are separately approved.**

---

## 4. Validation plan (when live execution is approved)

| Check | Expected |
|---|---|
| Manager API | Responds on admin port (authenticated) |
| Indexer | Cluster status green / single-node healthy |
| Dashboard | Login page reachable (SOC network only) |
| Agent port | Listener open for KB-042 enrollment |
| No secrets in Git | Vault-only credentials |
| Control plane | VM 100 can reach Manager API (future adapter test) |

---

## 5. Relationship to KB-036 / KB-037 / KB-038

| KB | Relevance |
|---|---|
| **KB-036** | Wazuh is a backend detection engine — not the customer UI |
| **KB-037** | Successful install enables `soc_clusters` registration with capacity fields |
| **KB-038** | Cloud/hybrid tenants route agents to this cluster via `primary_cluster_id` |

---

## 6. Security and no secrets

- All Wazuh credentials via Ansible Vault — **no secrets in Git or docs**
- Dashboard and API endpoints are admin/SOC only
- Playbook must not echo passwords in logs (`no_log: true` on secret tasks — future implementation)

---

## 7. Customer safety

- Installation targets **SOC infrastructure** only
- Indexed logs and raw alerts remain in the Wazuh cluster
- Customer portal receives **normalized summaries** via future MSSP adapters — never raw Wazuh JSON
- On-prem tenants (`deployment_mode = on_prem`) do not send raw logs to this cluster

---

## 8. Deferred live execution

| Item | Deferred to |
|---|---|
| Proxmox VM 101 creation | Separate explicit infrastructure approval |
| VM 101 pre-install snapshot | After OS provisioning, before Wazuh installation |
| `ansible-playbook wazuh-stack-install.yml` | After VM 101 exists + separate live-deployment approval |
| Installer SHA-256 verification | Immediately before the approved deployment |
| Generated credential custody | Approved secrets system / Vault, never Git |
| Indexer certificate management | VM 101 restricted files + KB-060 runbook |
| Cluster registry write-back | Future schema/API KB |
| Production hardening | KB-060 |

### 8.1 Target and rollback

- **Provisioning target:** Proxmox host creates VM 101.
- **Installation target:** VM 101 (`wazuh-stack`, proposed `192.168.0.211`).
- **Control plane:** VM 100 remains unchanged; Wazuh is never installed there.
- **Rollback:** restore the VM 101 pre-install snapshot. If provisioning itself
  fails, remove only the newly-created VM 101 after confirming VM ID and scope.
- Existing VM 100 snapshot `kb060-ok` remains the control-plane safety baseline.

**KB-041 preparation validation passes without contacting VM 101 or installing
Wazuh.**

---

## 9. What KB-041 changes (and must not)

### Changes

- `docs/KB041_WAZUH_STACK_INSTALLATION_VALIDATION.md` (this file)
- `scripts/kb041_validate_wazuh_stack_installation_validation.sh`
- `ansible/playbooks/wazuh-stack-install.yml`
- `ansible/group_vars/all.yml`
- `ansible/roles/wazuh_stack/defaults/main.yml`
- `ansible/roles/wazuh_stack/tasks/main.yml`
- `ansible/roles/wazuh_stack/handlers/main.yml`

### Must not change

- `backend-api/`, `frontend-customer/`, `frontend-admin/`
- `postgres/init/`, `docker-compose.yml`, `.env`

---

## 10. Validation

```bash
cd /opt/mssp-control
chmod +x scripts/kb041_validate_wazuh_stack_installation_validation.sh
./scripts/kb041_validate_wazuh_stack_installation_validation.sh
```

The validator parses YAML, checks execution interlocks and the Wazuh version
pin, scans for obvious secrets, confirms protected application paths are
unchanged, and runs `ansible-playbook --syntax-check` when Ansible is available.
It does **not** use the live inventory or connect to any host.

Expected final line:

```text
KB-041 WAZUH STACK INSTALLATION VALIDATION PASSED
```
