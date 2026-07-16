# KB-040 — Wazuh Stack VM Deployment Plan (VM 101)

Status: Implemented (pending validation/commit).  
Branch: `kb039-kb060-platform-roadmap-execution`  
Module type: **Planning / documentation only** — no Proxmox VM creation, no Wazuh install, no runtime changes.

Builds on: `docs/KB036_MSSP_PLATFORM_ARCHITECTURE_ROADMAP.md`, `docs/KB037_CLUSTER_APPLIANCE_REGISTRY_PLANNING.md`, `docs/KB038_TENANT_DEPLOYMENT_MODE_PLANNING.md`, and `docs/KB039_DEPLOYMENT_AUTOMATION_FOUNDATION.md`.

---

## 1. Purpose

Define the **deployment plan** for **VM 101 (`wazuh-stack`)** — the first shared MSSP SOC cluster host running:

- Wazuh Manager (agent management, rules, API)
- Wazuh Indexer / OpenSearch (log and alert indexing)
- Wazuh Dashboard (SOC analyst UI — **not** customer-facing)

This KB is **planning only**. Actual VM provisioning and package installation are deferred to **KB-041**.

---

## 2. VM reference

| Field | Value |
|---|---|
| **VM ID** | 101 |
| **Hostname** | `wazuh-stack` |
| **Placeholder IP** | `192.168.0.211` (lab — adjust when provisioned) |
| **Ansible group** | `wazuh_stack` (see `ansible/inventory/hosts.yml`) |
| **Status** | **Not deployed** — roadmap placeholder |

### Components on VM 101

| Component | Role |
|---|---|
| Wazuh Manager | Agent enrollment, rule processing, API for adapters |
| Wazuh Indexer / OpenSearch | Index storage for alerts and logs |
| Wazuh Dashboard | Internal SOC UI — admins/SOC only |

**Do not install Wazuh on VM 100 (control plane)** unless explicitly approved in a future KB.

---

## 3. Relationship to KB-036 / KB-037 / KB-038 / KB-039

| KB | Relevance |
|---|---|
| **KB-036** | VM 101 is the primary `wazuh-stack` in the lab VM layout (§7). Cloud model data flow starts here. |
| **KB-037** | VM 101 maps to a `soc_clusters` record (`cluster_code`, capacity fields). Admin-only URLs stored in cluster registry — **no secrets in Git**. |
| **KB-038** | Tenants with `deployment_mode = cloud` or `hybrid` require `primary_cluster_id` pointing at this cluster when active. `on_prem` tenants do not use VM 101 for log storage. |
| **KB-039** | Ansible inventory and group vars provide scaffolding; KB-041 adds the install playbook stub. |

---

## 4. Provisioning plan (deferred)

### 4.1 VM sizing (lab baseline — adjust per capacity KB-059)

| Resource | Lab minimum |
|---|---|
| vCPU | 4 |
| RAM | 16 GB |
| Disk | 200 GB (SSD preferred) |
| OS | Ubuntu 22.04 LTS (or approved enterprise Linux) |

### 4.2 Network

- Management NIC on lab LAN (`192.168.0.0/24`)
- Agents (VM 104/105, future customer endpoints) reach Manager API on approved ports
- Indexer and Dashboard **admin/SOC access only** — not exposed to customers

### 4.3 Post-provision checklist (KB-041)

1. OS hardening baseline
2. Wazuh single-node or approved multi-node layout
3. Indexer cluster health
4. Dashboard admin login (Vault — not Git)
5. Register cluster in `soc_clusters` (future schema KB)
6. Adapter connectivity test from VM 100 (future ingestion KB)

---

## 5. Security and no secrets

- Wazuh admin passwords, API users, and enrollment keys: **Ansible Vault / runtime only**
- Never commit credentials to `ansible/`, docs, or Git
- Wazuh Dashboard is **SOC/admin tooling** — customers use MSSP Control Plane only
- Cluster internal URLs (`wazuh_manager_url`, `wazuh_indexer_url`) are **admin-only** registry fields (KB-037)

---

## 6. Customer safety

- Raw Wazuh alerts and indexed logs **stay in the SOC cluster** — never in customer portal
- MSSP adapters normalize alerts into `security_alerts` with customer-safe field allowlists
- Customer APIs must not expose: raw JSON, `source_ip`/`destination_ip` (unless future safe design), cluster URLs, or Wazuh credentials
- `deployment_mode = on_prem` tenants: logs remain on customer site; VM 101 is not their log store

---

## 7. Deferred live execution

| Item | Deferred to |
|---|---|
| Proxmox VM 101 creation | KB-041 (or ops approval) |
| Wazuh package/container install | KB-041 |
| Health validation and indexer tests | KB-041 |
| Agent enrollment | KB-042 |
| Alert ingestion adapter | KB-057+ |
| Multi-cluster placement automation | KB-059 |

**KB-040 does not create VM 101 or install Wazuh.**

---

## 8. What KB-040 changes (and must not)

### Changes

- `docs/KB040_WAZUH_STACK_VM_DEPLOYMENT_PLAN.md` (this file)
- `scripts/kb040_validate_wazuh_stack_vm_deployment_plan.sh`

### Must not change

- `backend-api/`, `frontend-customer/`, `frontend-admin/`
- `postgres/init/`, `docker-compose.yml`, `.env`
- Live Ansible execution against hosts

---

## 9. Validation

```bash
cd /opt/mssp-control
chmod +x scripts/kb040_validate_wazuh_stack_vm_deployment_plan.sh
./scripts/kb040_validate_wazuh_stack_vm_deployment_plan.sh
```

Expected final line:

```text
KB-040 WAZUH STACK VM DEPLOYMENT PLAN VALIDATION PASSED
```
