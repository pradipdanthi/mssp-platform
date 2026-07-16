# KB-043 — Suricata Sensor Deployment Plan (VM 106)

Status: Implemented (pending validation/commit).  
Branch: `kb039-kb060-platform-roadmap-execution`  
Module type: **Planning / documentation only** — no VM creation, no Suricata install.

Builds on: `docs/KB036_MSSP_PLATFORM_ARCHITECTURE_ROADMAP.md`, `docs/KB037_CLUSTER_APPLIANCE_REGISTRY_PLANNING.md`, `docs/KB038_TENANT_DEPLOYMENT_MODE_PLANNING.md`, and `docs/KB039_DEPLOYMENT_AUTOMATION_FOUNDATION.md`.

---

## 1. Purpose

Define the **deployment plan** for **VM 106 (`suricata-sensor`)** — the lab network IDS/IPS sensor that feeds network threat detection into the MSSP SOC pipeline.

Suricata alerts will eventually integrate with Wazuh (KB-044) and normalize into MSSP Control Plane records. This KB is **planning only**.

---

## 2. VM reference

| Field | Value |
|---|---|
| **VM ID** | 106 |
| **Hostname** | `suricata-sensor` |
| **Placeholder IP** | `192.168.0.216` |
| **Ansible group** | `network_sensors` |
| **Status** | **Not deployed** |

### Role

| Function | Notes |
|---|---|
| Suricata IDS/IPS | Network traffic inspection |
| EVE JSON alerts | SOC processing — not customer raw export |
| SPAN/mirror or inline tap | Lab network design — document in ops runbook |

---

## 3. Relationship to KB-036 / KB-037 / KB-038 / KB-039

| KB | Relevance |
|---|---|
| **KB-036** | VM 106 in lab layout; Suricata listed in enterprise stack; cloud data flow includes network sensors |
| **KB-037** | Sensor may register as appliance with `source_platform = suricata`, `deployment_role = cloud_collector` when cloud-path |
| **KB-038** | Cloud/hybrid: sensor alerts feed shared cluster path. On-prem: local sensor stays on-site; metadata only to control plane |
| **KB-039** | Inventory placeholder under `network_sensors` group |

---

## 4. Provisioning plan (deferred)

### 4.1 VM sizing (lab baseline)

| Resource | Lab minimum |
|---|---|
| vCPU | 2 |
| RAM | 8 GB |
| Disk | 100 GB |
| NICs | 2 recommended (mgmt + monitor/span) |
| OS | Ubuntu 22.04 LTS |

### 4.2 Deployment steps (future KB execution)

1. Provision VM 106 on Proxmox
2. Install Suricata + ruleset (emerging threats or approved feed)
3. Configure `suricata.yaml` for monitor interface
4. Enable EVE JSON alert output
5. Validate alert generation with test traffic
6. KB-044: forward/integration to Wazuh
7. Future adapter: normalize to `security_alerts` with tenant scope

---

## 5. Security and no secrets

- Rule feed API keys (if commercial): **Vault only** — no secrets in Git
- Sensor management SSH: key-based, Vault-managed
- No packet captures or raw Suricata logs in customer portal

---

## 6. Customer safety

- Raw Suricata logs and PCAPs: **SOC infrastructure only** — **never** in customer portal
- Customer portal receives **plain-English alert summaries** via normalized records
- Forbidden customer fields: raw JSON, packet captures, internal sensor IPs (unless future safe design), `raw_event`
- On-prem mode: network logs stay local; only safe metadata syncs (KB-038)

---

## 7. Deferred live execution

| Item | Deferred to |
|---|---|
| VM 106 Proxmox creation | Future execution KB |
| Suricata package install | Future execution KB |
| Ansible playbook for Suricata | KB-044 or dedicated install KB |
| Suricata → Wazuh integration | KB-044 |
| MSSP alert ingestion adapter | KB-057+ |

**KB-043 does not create VM 106 or install Suricata.**

---

## 8. What KB-043 changes (and must not)

### Changes

- `docs/KB043_SURICATA_SENSOR_DEPLOYMENT_PLAN.md` (this file)
- `scripts/kb043_validate_suricata_sensor_deployment_plan.sh`

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
