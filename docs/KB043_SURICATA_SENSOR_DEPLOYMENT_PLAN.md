# KB-043 — Suricata Sensor Deployment (VM 106)

Status: **Live deploy completed and validated** — Suricata 7.0.3 passive IDS on VM 106 (`192.168.0.216`).  
Branch: `kb039-kb060-platform-roadmap-execution`  
Module type: **Infrastructure automation + live sensor deploy** — safe-default Ansible role with preflight gate; live install executed with plan approval.

Builds on: `docs/KB036_MSSP_PLATFORM_ARCHITECTURE_ROADMAP.md`, `docs/KB037_CLUSTER_APPLIANCE_REGISTRY_PLANNING.md`, `docs/KB038_TENANT_DEPLOYMENT_MODE_PLANNING.md`, and `docs/KB039_DEPLOYMENT_AUTOMATION_FOUNDATION.md`.

---

## 1. Purpose

Deploy **VM 106 (`suricata-sensor`)** as a **passive network IDS** for the lab, with safe Ansible automation, reversible traffic mirroring from the Linux endpoint lab VM, and local EVE JSON alert proof.

Suricata → Wazuh forwarding remains **KB-044**. Customer-safe normalization remains **KB-057+**. Raw Suricata logs/PCAPs never enter the customer portal.

---

## 2. VM reference

| Field | Value |
|---|---|
| **VM ID** | 106 |
| **Hostname** | `suricata-sensor` |
| **Management IP** | `192.168.0.216` |
| **Ansible group** | `network_sensors` |
| **Status** | **Deployed** — Suricata 7.0.3 active; local alert proof SID `2100498` |

### Role

| Function | Notes |
|---|---|
| Suricata passive IDS | Network traffic inspection (IDS only — never inline IPS) |
| EVE JSON alerts | SOC processing — not customer raw export |
| Capture path | Dual NIC: mgmt on `vmbr0` + no-IP capture NIC `enp6s19` on `vmbr-capture`; Proxmox `tc` mirror of VM 105 |

### Lab network decision (confirmed)

Proxmox `Labhyp` has one wired NIC on `vmbr0` and **no spare capture NIC**. Full-LAN SPAN is not available. The approved lab approach is:

1. Management NIC on `vmbr0` at `192.168.0.216`
2. Isolated capture bridge `vmbr-capture` (no physical port) for a no-IP monitor NIC
3. Narrow, reversible `tc` mirror of VM 105 (`tap105i0` → `tap106i1`)
4. Safe-default Ansible role (`preflight` → approved `install` → `validate`)

---

## 3. Relationship to KB-036 / KB-037 / KB-038 / KB-039

| KB | Relevance |
|---|---|
| **KB-036** | VM 106 in lab layout; Suricata listed in enterprise stack; cloud data flow includes network sensors |
| **KB-037** | Sensor may register as appliance with `source_platform = suricata`, `deployment_role = cloud_collector` when cloud-path |
| **KB-038** | Cloud/hybrid: sensor alerts feed shared cluster path. On-prem: local sensor stays on-site; metadata only to control plane |
| **KB-039** | Inventory under `network_sensors` group |

---

## 4. Live provisioned sizing

| Resource | Lab value |
|---|---|
| vCPU | 2 |
| RAM | 8 GB |
| Disk | 100 GB |
| NICs | `net0` → `vmbr0` (mgmt); `net1` → `vmbr-capture` (capture, no IP) |
| OS | Ubuntu 24.04 cloud image + cloud-init |

---

## 5. Security and no secrets

- Rule feed API keys (if commercial): **Vault only** — no secrets in Git
- Sensor management SSH: key-based (`id_ed25519_suricata` / Ansible `id_ed25519_ansible_suricata`)
- No packet captures or raw Suricata logs in customer portal

---

## 6. Customer safety

- Raw Suricata logs and PCAPs: **SOC infrastructure only** — **never** in customer portal
- Customer portal receives **plain-English alert summaries** via normalized records (future KB-057)
- Forbidden customer fields: raw JSON, packet captures, internal sensor IPs (unless future safe design), `raw_event`
- On-prem mode: network logs stay local; only safe metadata syncs (KB-038)

---

## 7. Live results (this KB) and still deferred

| Item | Status |
|---|---|
| Ansible `suricata_sensor` role + playbook | Done (safe default = **preflight**) |
| VM 106 Proxmox creation (dual NIC) | Done |
| Suricata 7.0.3 + EVE JSON | Done — service active |
| Reversible VM 105 → capture NIC mirror | Done — script on Proxmox host |
| Local detection proof | Done — ET SID `2100498` |
| Suricata → Wazuh integration | **Deferred to KB-044** |
| MSSP alert ingestion adapter | **Deferred to KB-057+** |

### Mirror controls (Proxmox `labhyp`)

```bash
/usr/local/sbin/mssp-kb043-mirror-vm105-to-106.sh enable
/usr/local/sbin/mssp-kb043-mirror-vm105-to-106.sh disable
/usr/local/sbin/mssp-kb043-mirror-vm105-to-106.sh status
# emergency remove:
tc qdisc del dev tap105i0 clsact
```

### Ansible (from VM 112)

```bash
cd /home/secadmin/mssp-automation/ansible
ansible-playbook -i inventory/hosts.yml playbooks/suricata-sensor.yml
ansible-playbook -i inventory/hosts.yml playbooks/suricata-sensor.yml \
  -e suricata_execution_mode=install -e suricata_live_install_approved=true
ansible-playbook -i inventory/hosts.yml playbooks/suricata-sensor.yml \
  -e suricata_execution_mode=validate
```

---

## 8. What KB-043 changes (and must not)

### Changes

- `docs/KB043_SURICATA_SENSOR_DEPLOYMENT_PLAN.md` (this file)
- `scripts/kb043_validate_suricata_sensor_deployment_plan.sh`
- `ansible/roles/suricata_sensor/`
- `ansible/playbooks/suricata-sensor.yml`
- `ansible/inventory/hosts.yml` (SSH access for VM 106)
- `CONTEXT.md`, `docs/AI_PROMPT_LEDGER.md`

### Must not change

- `backend-api/`, `frontend-customer/`, `frontend-admin/`
- `postgres/init/`, `docker-compose.yml`, `.env`

---

## 9. Validation

```bash
cd /opt/mssp-control
chmod +x scripts/kb043_validate_suricata_sensor_deployment_plan.sh
./scripts/kb043_validate_suricata_sensor_deployment_plan.sh
```

Expected final line:

```text
KB-043 SURICATA SENSOR DEPLOYMENT PLAN VALIDATION PASSED
```

Rollback: disable/remove `tc` mirror; stop/delete VM 106 and `vmbr-capture` if needed. `vmbr0`, VM 105, and VM 101 remain unchanged.
