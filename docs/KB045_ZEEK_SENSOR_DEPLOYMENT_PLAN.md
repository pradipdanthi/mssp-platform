# KB-045 — Zeek Sensor Deployment Plan (VM 107)

Status: Implemented (pending validation/commit).  
Branch: `kb039-kb060-platform-roadmap-execution`  
Module type: **Planning / documentation only** — no runtime code, schema, compose, or `.env` changes.

Builds on: `docs/KB036_MSSP_PLATFORM_ARCHITECTURE_ROADMAP.md`, `docs/KB037_CLUSTER_APPLIANCE_REGISTRY_PLANNING.md`, `docs/KB038_TENANT_DEPLOYMENT_MODE_PLANNING.md`.

---

## 1. Purpose

Define the **lab deployment plan** for **Zeek network security monitoring** on **VM 107** (`zeek-sensor`) — OS baseline, network tap/SPAN attachment, Zeek packages, log output layout, and health checks — before Zeek log integration (KB-046) and control-plane adapters (KB-057).

This KB is **planning only**. No VM creation, Zeek install, or log shipping in this module.

---

## 2. Current baseline

| Area | Status |
|---|---|
| VM 107 `zeek-sensor` | **Not created** — roadmap placeholder (KB-036) |
| Zeek installation | **Not deployed** |
| Network tap / SPAN | Lab design only — physical/virtual mirror TBD at deploy time |
| Appliance registry | `appliances` exists — sensor VM may register as tenant-scoped appliance (future) |
| Customer portal | No Zeek data — must remain that way |

---

## 3. Architecture

### 3.1 Zeek role in MSSP stack

Zeek provides **protocol-level network visibility** (connections, DNS, HTTP metadata, SSL fingerprints, etc.) complementary to Suricata IDS (KB-043/044). Zeek is **not** a replacement for Wazuh endpoint telemetry.

```
Network SPAN/tap
  → VM 107 Zeek (conn.log, dns.log, http.log, ssl.log, …)
  → KB-046 log integration → Wazuh / indexer path
  → Future MSSP adapter (KB-057) → normalized PostgreSQL
  → Admin/SOC dashboard → customer-safe portal
```

### 3.2 Planned VM specification (lab)

| Item | Planned value |
|---|---|
| VM ID | **107** |
| Hostname | `zeek-sensor` |
| OS | Ubuntu LTS (match lab standard from KB-039 Ansible templates) |
| vCPU / RAM | 2–4 vCPU, 4–8 GB RAM (adjust per traffic in implementation KB) |
| Disk | 40+ GB — Zeek logs are volume-heavy; rotation required |
| Network | Management NIC + **monitor/dedicated capture NIC** (SPAN) |

### 3.3 Zeek deployment components (implementation checklist — not executed in KB-045)

1. Create VM 107 in Proxmox (after KB-039 automation foundation approved).
2. Install Zeek from approved packages or KB-039 playbook.
3. Configure `node.cfg` / `networks.cfg` for lab capture interface.
4. Enable log rotation (`zeekctl` cron or logrotate) — **raw logs stay on sensor / SOC path only**.
5. Register sensor as appliance (optional) with `source_platform = zeek` (KB-037).
6. Document health check: `zeekctl status`, log freshness, capture interface stats.

---

## 4. VM references

| VM | Name | Role |
|---|---|---|
| **VM 107** | `zeek-sensor` | Primary Zeek sensor — **this KB's focus** |
| **VM 101** | `wazuh-stack` | Future log destination (KB-046) |
| **VM 106** | `suricata-sensor` | Sibling network sensor — may share SPAN (coordinate in implementation) |
| **VM 100** | `mssp-control` | Control plane — metadata only, no raw Zeek logs |

---

## 5. Tenant isolation

- Shared lab Zeek may observe **multi-tenant lab traffic** — tenant assignment happens at **normalization/adapter** layer, not by exposing all logs to all customers.
- Future mapping options:
  - Subnet/VLAN → `tenant_id` (admin-configured)
  - Dedicated Zeek instance per high-isolation tenant (production scale — defer)
  - Appliance registration linking sensor to tenant for health/sync metadata
- Customer APIs: tenant-scoped normalized records only — wrong tenant → **404**.

---

## 6. Customer portal safety

Customer portal must **never** expose:

- Raw Zeek logs (`conn.log`, `dns.log`, full HTTP headers, payloads)
- Packet contents or PCAP paths
- Internal sensor hostnames, capture interface names, or Zeek scripts
- Credentials for log shipping or manager APIs

Customers receive **high-level network activity summaries** only when KB-057 defines safe projections.

**No secrets** in Git, docs, or customer API responses.

---

## 7. Relationship to prior KBs

| KB | Relationship |
|---|---|
| **KB-036** | VM 107 placement in enterprise roadmap; Zeek as network monitoring engine |
| **KB-037** | Appliance `source_platform`, `sync_health_status` for sensor registration |
| **KB-038** | Cloud/hybrid tenants use MSSP-hosted sensors; on-prem may run local Zeek (KB-058) |
| **KB-039** | Ansible/inventory templates for VM provisioning |
| **KB-043** | Suricata sensor pattern on VM 106 — parallel network sensor deployment model |
| **KB-046** | Zeek log integration to Wazuh — **next** after sensor plan |
| **KB-057** | Control-plane adapter for normalized network events |

---

## 8. Explicit deferrals

| Item | Deferred to |
|---|---|
| Proxmox VM 107 creation | KB-045 implementation KB (after KB-039) |
| Zeek package install and `zeekctl` config | KB-045 implementation KB |
| SPAN/tap physical wiring | Lab ops at deploy time |
| Zeek → Wazuh log shipping | **KB-046** |
| MSSP alert normalization | **KB-057** |
| Customer network visibility UI | Future customer KB |

---

## 9. Decision summary (approved defaults)

| # | Decision | Choice |
|---|---|---|
| D1 | Sensor VM | VM 107 `zeek-sensor` |
| D2 | Coexistence with Suricata | Same SPAN acceptable in lab; separate VMs (106 vs 107) |
| D3 | Log retention | Local rotation on sensor; long-term storage in indexer path — not control plane |
| D4 | Customer visibility | **No raw Zeek logs** — normalized summaries only |
| D5 | Secrets | Env/secret store only — **no secrets** in Git or docs |

---

## 10. What KB-045 changes (and must not)

### Changes

- `docs/KB045_ZEEK_SENSOR_DEPLOYMENT_PLAN.md` (this file)
- `scripts/kb045_validate_zeek_sensor_deployment_plan.sh`

### Must not change

- `backend-api/`, `frontend-customer/`, `frontend-admin/`
- `postgres/init/`, `docker-compose.yml`, `.env`
- No VM 107 creation or Zeek install in this KB

---

## 11. Validation

```bash
cd /opt/mssp-control
chmod +x scripts/kb045_validate_zeek_sensor_deployment_plan.sh
./scripts/kb045_validate_zeek_sensor_deployment_plan.sh
```

Expected final line:

```text
KB-045 ZEEK SENSOR DEPLOYMENT PLAN VALIDATION PASSED
```
