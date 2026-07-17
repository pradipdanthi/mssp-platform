# KB-039 — Deployment Automation Foundation

Status: Implemented (pending validation/commit).  
Branch: `kb039-kb060-platform-roadmap-execution`  
Module type: **Planning / Ansible scaffolding only** — no live VM provisioning, no runtime code, schema, compose, or `.env` changes.

Builds on: `docs/KB036_MSSP_PLATFORM_ARCHITECTURE_ROADMAP.md`, `docs/KB037_CLUSTER_APPLIANCE_REGISTRY_PLANNING.md`, and `docs/KB038_TENANT_DEPLOYMENT_MODE_PLANNING.md`.

---

## 1. Purpose

Establish the **Ansible foundation** for future MSSP SOC stack deployment automation:

- Standard directory layout under `ansible/`
- Inventory placeholders for lab VMs **100–111**
- Group variables with **placeholder** values only (no secrets)
- Stub playbooks that document intent without executing live installs

This KB produces **scaffolding and documentation only**. Proxmox VM creation, package installs, and service configuration are **deferred** to KB-040+.

---

## 2. VM references (lab Proxmox layout)

| VM | Hostname placeholder | Role | Status |
|---|---|---|---|
| **VM 100** | `mssp-control` | MSSP Control Plane (`192.168.0.201`) | **Deployed** |
| **VM 101** | `wazuh-stack` | Wazuh Manager, Indexer/OpenSearch, Dashboard | **OS deployed** (`192.168.0.211`); Wazuh not installed |
| **VM 102** | `thehive` | TheHive (+ Cortex if needed) | Future |
| **VM 103** | `shuffle` | SOAR playbooks | Future |
| **VM 104** | `windows-endpoint-lab` | Windows + Wazuh Agent | Future (KB-042) |
| **VM 105** | `linux-endpoint-lab` | Linux + Wazuh Agent | Future (KB-042) |
| **VM 106** | `suricata-sensor` | Suricata IDS/IPS sensor | Future (KB-043) |
| **VM 107** | `zeek-sensor` | Zeek network monitoring | Future |
| **VM 108** | `misp` | MISP threat intelligence | Future |
| **VM 109** | `greenbone` | Greenbone/OpenVAS | Future |
| **VM 110** | `velociraptor` | Velociraptor DFIR server | Future |
| **VM 111** | `monitoring` | Prometheus/Grafana | Future |
| **VM 112** | `automation` | Dedicated Ansible controller (`192.168.0.222`) | **Deployed** — Ansible Core 2.16.3 |

Inventory file: `ansible/inventory/hosts.yml` — real lab metadata for VMs
100/101/112 and placeholders for future VMs 102–111. It contains no secrets.

---

## 3. Ansible layout

```text
ansible/
├── README.md
├── ansible.cfg
├── inventory/
│   └── hosts.yml
├── group_vars/
│   └── all.yml
└── playbooks/
    └── bootstrap.yml          # stub — connectivity check only (KB-039)
```

Future KB modules add playbooks (e.g. `wazuh-stack-install.yml` in KB-041) without restructuring this foundation.

---

## 4. Relationship to KB-037 / KB-038

| KB | How KB-039 uses it |
|---|---|
| **KB-037** | Cluster registry (`soc_clusters`) will reference deployed cluster VMs (e.g. VM 101). Ansible host groups align with `cluster_code` / capacity planning — assignment logic stays in control plane, not in Git. |
| **KB-038** | Tenant `deployment_mode` (`cloud` / `on_prem` / `hybrid`) determines **which** automation path runs (cloud cluster vs on-prem appliance). Ansible scaffolding supports both; routing enforcement is control-plane responsibility. |

---

## 5. Security and secrets policy

- **No secrets in Git** — passwords, API keys, JWT secrets, Wazuh enrollment keys, and activation tokens must never appear in `ansible/`, docs, or validation scripts.
- Placeholder variables in `ansible/group_vars/all.yml` use values like `<SET_VIA_VAULT_OR_ENV>` — operators inject real values at runtime via Ansible Vault, CI secrets, or out-of-band env files **not** committed to the repository.
- Inventory uses placeholder management IPs (e.g. `192.168.0.2xx`) — adjust per lab without storing credentials.
- Admin-only URLs (Wazuh Manager, Indexer) belong in **runtime config / cluster registry**, not customer APIs or documentation with real values.

---

## 6. Customer safety

Deployment automation operates on **SOC infrastructure VMs** and **endpoint lab hosts** — not the customer portal.

- Ansible playbooks must **never** configure customer-facing APIs or weaken tenant isolation.
- Normalized alert/incident data reaching customers flows through MSSP Control Plane adapters with field allowlists (KB-036 §9).
- **Raw logs never** appear in the customer portal — regardless of deployment mode (KB-038).

---

## 7. Deferred live execution

| Item | Deferred to |
|---|---|
| Remaining Proxmox VM creation (102–111) | Matching deployment KB |
| `ansible-playbook` against live hosts | KB-040+ after VM approval |
| Ansible Vault / secret injection wiring | Ops runbook KB-060 |
| Cluster registry → inventory sync | Future implementation KB |
| On-prem appliance template automation | KB-058 |

**KB-039 does not run `ansible-playbook` against production or lab VMs.** The `bootstrap.yml` stub documents a future connectivity-check playbook only.

---

## 8. What KB-039 changes (and must not)

### Changes

- `docs/KB039_DEPLOYMENT_AUTOMATION_FOUNDATION.md` (this file)
- `scripts/kb039_validate_deployment_automation_foundation.sh`
- `ansible/README.md`, `ansible/ansible.cfg`, `ansible/inventory/hosts.yml`, `ansible/group_vars/all.yml`, `ansible/playbooks/bootstrap.yml`

### Must not change

- `backend-api/`, `frontend-customer/`, `frontend-admin/`
- `postgres/init/`, `docker-compose.yml`, `.env`

---

## 9. Validation

```bash
cd /opt/mssp-control
chmod +x scripts/kb039_validate_deployment_automation_foundation.sh
./scripts/kb039_validate_deployment_automation_foundation.sh
```

Expected final line:

```text
KB-039 DEPLOYMENT AUTOMATION FOUNDATION VALIDATION PASSED
```
