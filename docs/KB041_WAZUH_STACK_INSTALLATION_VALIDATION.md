# KB-041 — Wazuh Stack Installation and Validation

Status: Implemented (pending validation/commit).  
Branch: `kb039-kb060-platform-roadmap-execution`  
Module type: **Planning / Ansible playbook stub only** — **NOT** a live Wazuh install.

Builds on: `docs/KB036_MSSP_PLATFORM_ARCHITECTURE_ROADMAP.md`, `docs/KB037_CLUSTER_APPLIANCE_REGISTRY_PLANNING.md`, `docs/KB038_TENANT_DEPLOYMENT_MODE_PLANNING.md`, `docs/KB039_DEPLOYMENT_AUTOMATION_FOUNDATION.md`, and `docs/KB040_WAZUH_STACK_VM_DEPLOYMENT_PLAN.md`.

---

## 1. Purpose

Provide an **Ansible playbook stub** (`ansible/playbooks/wazuh-stack-install.yml`) and validation plan for installing and validating the Wazuh stack on **VM 101 (`wazuh-stack`)**.

This KB documents **what KB-041 will do when executed** — it does **not** run installs in the lab until explicitly approved and VM 101 exists.

---

## 2. VM reference

| Field | Value |
|---|---|
| **VM** | 101 — `wazuh-stack` |
| **Target group** | `wazuh_stack` in `ansible/inventory/hosts.yml` |
| **Components** | Wazuh Manager, Indexer/OpenSearch, Dashboard |

---

## 3. Playbook stub

File: `ansible/playbooks/wazuh-stack-install.yml`

The stub lists planned task phases with `ansible.builtin.debug` placeholders:

1. Pre-flight (OS, disk, ports)
2. Wazuh Indexer install
3. Wazuh Manager install
4. Wazuh Dashboard install
5. Service health checks
6. Post-install validation (API, indexer cluster green)
7. Register cluster metadata hook (future `soc_clusters` API)

**Do not run this playbook until VM 101 is provisioned and secrets are in Vault.**

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
| `ansible-playbook wazuh-stack-install.yml` | After VM 101 exists + ops approval |
| Wazuh version pinning and package URLs | Implementation pass in KB-041 execution |
| Indexer certificate management | Vault + KB-060 runbook |
| Cluster registry write-back | Future schema/API KB |
| Production hardening | KB-060 |

**KB-041 stub validation passes without installing Wazuh.**

---

## 9. What KB-041 changes (and must not)

### Changes

- `docs/KB041_WAZUH_STACK_INSTALLATION_VALIDATION.md` (this file)
- `scripts/kb041_validate_wazuh_stack_installation_validation.sh`
- `ansible/playbooks/wazuh-stack-install.yml` (stub)

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

Expected final line:

```text
KB-041 WAZUH STACK INSTALLATION VALIDATION PASSED
```
