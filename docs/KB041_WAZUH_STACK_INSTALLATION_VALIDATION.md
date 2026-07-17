# KB-041 — Wazuh Stack Installation and Validation

Status: **Live install completed and validated** on VM 101 (Wazuh 4.14.6).
Branch: `kb039-kb060-platform-roadmap-execution`  
Module type: **Infrastructure automation** — live all-in-one install executed with explicit approval.

Builds on: `docs/KB036_MSSP_PLATFORM_ARCHITECTURE_ROADMAP.md`, `docs/KB037_CLUSTER_APPLIANCE_REGISTRY_PLANNING.md`, `docs/KB038_TENANT_DEPLOYMENT_MODE_PLANNING.md`, `docs/KB039_DEPLOYMENT_AUTOMATION_FOUNDATION.md`, and `docs/KB040_WAZUH_STACK_VM_DEPLOYMENT_PLAN.md`.

---

## 1. Purpose

Provide a safe, version-pinned Ansible role and playbook
(`ansible/playbooks/wazuh-stack-install.yml`) for preflighting, installing, and
validating the Wazuh stack on **VM 101 (`wazuh-stack`)**.

The automation defaults to **preflight only**. With explicit approval on
2026-07-17, VM 101 received the all-in-one Wazuh **4.14.6** install from
VM 112. A follow-up `validate` run confirmed packages, services, and listeners.
Credentials remain in the root-only archive on VM 101 and must never enter Git.

---

## 2. VM reference

| Field | Value |
|---|---|
| **VM** | 101 — `wazuh-stack` |
| **Address** | `192.168.0.211` |
| **Target group** | `wazuh_stack` in `ansible/inventory/hosts.yml` |
| **Controller** | VM 112 `automation` (`192.168.0.222`), Ansible Core 2.16.3 |
| **Components** | Wazuh Manager, Indexer/OpenSearch, Dashboard |

---

## 3. Prepared automation

File: `ansible/playbooks/wazuh-stack-install.yml`

Role: `ansible/roles/wazuh_stack/`

The role provides three explicit modes:

| Mode | Behavior |
|---|---|
| `preflight` | Default. Checks VM identity, OS, architecture, CPU, RAM, total/free disk, reboot state, installer TLS/checksum, and current listeners. Makes no package changes. |
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
- Two independent downloads on 2026-07-17 matched SHA-256
  `cb7f4ca737a798e4ed98c73579a6105b4dab45aa967bc1c0154f85ab2951b209`
  (208288 bytes). The byte-identical script pins Wazuh components to 4.14.6
  and Filebeat to 7.10.2; the checksum must be reverified before installation.
- Installer output uses `no_log: true` because the official assistant generates
  credentials.
- Generated credentials remain in
  `/root/wazuh-install/wazuh-install-files.tar` on VM 101 with owner
  `root:root` and mode `0600`. They must later be transferred through an
  approved secrets workflow; **never print, copy to Git, or place in docs**.
- A successful installation marker is written only after package, service, and
  listener validation passes.

**Do not run this playbook in `install` mode against VM 101 until
Vault/secrets handling and the exact deployment command are separately
approved.**

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
| Proxmox VM 101 creation | **Complete** |
| VM 101 pre-install snapshot | **Complete** — `kb041-os-updated` |
| VM 112 controller baseline | **Complete** — `kb112-ansible-ready` |
| Controlled automation sync to VM 112 | **Complete** |
| Preflight-only playbook execution | **Passed** — `changed=0`, `failed=0`, required Wazuh ports available |
| `ansible-playbook wazuh-stack-install.yml` in `install` mode | **Complete** — 2026-07-17; `ok=24 changed=7 failed=0` |
| Follow-up `validate` mode | **Passed** — `ok=12 changed=0 failed=0` |
| Installer SHA-256 verification | Verified 2026-07-17 (`cb7f4ca737a798e4ed98c73579a6105b4dab45aa967bc1c0154f85ab2951b209`) |
| Generated credential custody | Root-only archive on VM 101 (`/root/wazuh-install/wazuh-install-files.tar`, mode `600`); approved secrets workflow later, never Git |
| Indexer certificate management | VM 101 restricted files + KB-060 runbook |
| Cluster registry write-back | Future schema/API KB |
| Production hardening | KB-060 |
| Post-install Proxmox snapshot | Deferred to end-of-batch snapshot per operator request |

### 8.1 Target and rollback

- **Provisioning target:** VM 101 is deployed on Proxmox host `Labhyp`.
- **Installation target:** VM 101 (`wazuh-stack`, `192.168.0.211`).
- **Automation controller:** VM 112 (`automation`, `192.168.0.222`).
- **Control plane:** VM 100 remains unchanged; Wazuh is never installed there.
- **Rollback:** restore the VM 101 pre-install snapshot `kb041-os-updated`.
- Existing VM 100 snapshot `kb060-ok` remains the control-plane safety baseline.

### 8.2 Live install result (2026-07-17)

| Check | Result |
|---|---|
| Install recap | `ok=24 changed=7 failed=0` |
| Validate recap | `ok=12 changed=0 failed=0` |
| Packages | `wazuh-manager` / `wazuh-indexer` / `wazuh-dashboard` **4.14.6-1**; `filebeat` **7.10.2-2** |
| Services | All four expected units `active` |
| Listeners | Local TCP **443**, **1514**, **1515**, **55000**, **9200** |
| Install marker | `/var/lib/mssp/wazuh/4.14.6.installed` present |
| Credentials | Archive present, `root:root` mode `600` — **no secrets in Git** |

The earlier expanded preflight recap was `ok=15 changed=0 failed=0 skipped=16`
(4 vCPUs, ~16 GB RAM, ~193 GiB total / ~178 GiB free root, reboot-clean,
installer TLS/checksum verified, required ports free).

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

### 10.1 Live install command (executed 2026-07-17 with separate approval)

```bash
cd /home/secadmin/mssp-automation/ansible
ansible-playbook playbooks/wazuh-stack-install.yml \
  --limit wazuh-stack \
  -e wazuh_execution_mode=install \
  -e wazuh_live_install_approved=true
```

Do not add `--check`: installation requires real package and service changes,
followed by the role's package, service, listener, and credential-archive
validation. Defaults remain `preflight` / `wazuh_live_install_approved=false`
so a future accidental run without explicit `-e` overrides stays safe.

Re-run validation only with:

```bash
ansible-playbook playbooks/wazuh-stack-install.yml \
  --limit wazuh-stack \
  -e wazuh_execution_mode=validate
```

Expected local source-validator final line:

```text
KB-041 WAZUH STACK INSTALLATION VALIDATION PASSED
```
