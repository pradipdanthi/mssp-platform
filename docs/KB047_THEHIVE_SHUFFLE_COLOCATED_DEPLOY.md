# KB-047/048 — TheHive + Shuffle Co-located Deploy (VM 102)

Status: **Live install completed** — TheHive + Shuffle on VM 102 (`thehive_shuffle` / `192.168.0.212`, **16 GB**).  
Auto-ticket wiring (Wazuh → Shuffle → TheHive) is **ready for first-login configuration** (KB-049).  
Branch: `kb039-kb060-platform-roadmap-execution`

---

## 1. Purpose

Provide **SOC ticketing (TheHive)** and **automation (Shuffle)** on **one lab VM** so high-severity detections can become cases automatically — without spending two VMs of RAM.

---

## 2. Live baseline

| Item | Value |
|---|---|
| VM ID | **102** |
| Proxmox name | `thehive-shuffle` (qm DNS-safe) |
| Ansible / SSH alias | `thehive_shuffle` |
| IP | `192.168.0.212` |
| RAM / vCPU / disk | **16 GB** / 4 / 80 GB |
| TheHive UI | `http://192.168.0.212:9000` |
| Shuffle UI | `http://192.168.0.212:3001` |
| Separate VM 103 | **Deferred** (Shuffle co-located) |
| Wazuh Indexer reuse | **No** — TheHive uses its own Cassandra (lab) |

---

## 3. Architecture

```
Wazuh / Suricata alerts (VM 101)
  → Shuffle webhook (VM 102 :3001)
  → TheHive case API (VM 102 :9000)
  → Future MSSP adapter (KB-057) → customer-safe incidents
```

Cortex, MISP enrichment, and Zeek are deferred.

---

## 4. Customer safety

- TheHive and Shuffle are **SOC-only** — never customer-facing.
- No raw case JSON, playbook logs, or API keys in the customer portal.
- **No secrets in Git** — first-login admin passwords are set in the browser only.

---

## 5. Ansible

```bash
cd /home/secadmin/mssp-automation/ansible
ansible-playbook -i inventory/hosts.yml playbooks/case-soar.yml
ansible-playbook -i inventory/hosts.yml playbooks/case-soar.yml \
  -e case_soar_execution_mode=install \
  -e case_soar_live_install_approved=true
ansible-playbook -i inventory/hosts.yml playbooks/case-soar.yml \
  -e case_soar_execution_mode=validate
```

Safe default: `preflight`. Live install requires explicit approval flag.

---

## 6. First-login (required before auto-tickets)

1. Open TheHive → create admin account  
2. Open Shuffle → create admin account  
3. Then configure KB-049: Shuffle workflow + TheHive API key + Wazuh integration webhook  

---

## 7. Must not change

- `backend-api/`, `frontend-customer/`, `frontend-admin/`
- `postgres/init/`, `docker-compose.yml`, `.env`
