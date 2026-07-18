# KB-044 — Suricata to Wazuh Integration

Status: **Live integration completed and validated** — Wazuh agent on VM 106 tails Suricata `eve.json` into Manager VM 101.  
Branch: `kb039-kb060-platform-roadmap-execution`  
Module type: **Infrastructure automation + live integration** — Option A (agent on sensor); safe-default Ansible with preflight gate.

Builds on: `docs/KB036_MSSP_PLATFORM_ARCHITECTURE_ROADMAP.md`, **KB-037**/**KB-038** (cluster registry / deployment automation), **KB-041** (Wazuh live), **KB-043** (Suricata live on VM 106).

---

## 1. Purpose

Forward **Suricata IDS alerts** from VM 106 into the **Wazuh stack** (VM 101) so network detections are searchable alongside endpoint alerts — without exposing raw Suricata logs to the customer portal.

Customer-safe normalization into MSSP Control Plane remains **KB-057**.

---

## 2. Current baseline

| Area | Status |
|---|---|
| VM 106 `suricata-sensor` | **Deployed** — Suricata 7.0.3; `eve.json` active |
| VM 101 `wazuh-stack` | **Deployed** — Wazuh 4.14.6 |
| Suricata → Wazuh path | **Live** — agent **002** `suricata-sensor` monitors `eve.json`; Manager rule **86601** proof |
| `security_alerts` ingestion | Control plane schema exists; live Suricata adapter still KB-057 |
| Customer portal | No raw Suricata data — must remain that way |

---

## 3. Architecture

### 3.1 Target data flow (cloud / lab)

```
Network traffic (VM 105 tc mirror → VM 106 capture NIC)
  → Suricata (eve.json alerts)
  → Wazuh agent on VM 106 (localfile JSON)
  → Wazuh Manager on VM 101
  → Wazuh Indexer / OpenSearch
  → Future MSSP adapter (KB-057) → normalized PostgreSQL
  → Admin/SOC dashboard → customer-safe portal
```

### 3.2 Integration option (implemented)

| Option | Description | Status |
|---|---|---|
| **A — Wazuh agent on sensor VM** | Suricata `eve.json` monitored by Wazuh agent on VM 106 | **Implemented** |
| B — Remote syslog | Deferred | Not used |
| C — Filebeat / custom shipper | Deferred | Not used |

### 3.3 Normalization alignment (KB-036)

| Field concept | Source |
|---|---|
| `tenant_id` | Assigned via agent group / tenant mapping (**KB-037**, **KB-038**) — never from client-supplied IDs alone |
| `source_platform` | `suricata` (network) + `wazuh` (transport/index path) |
| `alert` | Normalized summary — signature, severity, category — **not** full `eve.json` to customers |
| `sync_health_status` | Sensor + manager health rolled up per appliance/cluster |

---

## 4. VM references

| VM | Name | Role in this KB |
|---|---|---|
| **VM 101** | `wazuh-stack` | Wazuh Manager receives Suricata-derived events |
| **VM 106** | `suricata-sensor` | Suricata + Wazuh agent (`suricata-sensor`) |

---

## 5. Tenant isolation

- Suricata events on shared lab infrastructure must be **tagged to the correct tenant** before they appear in customer-facing records.
- Mapping mechanisms (future implementation): Wazuh agent groups/labels, VLAN→tenant mapping, appliance `tenant_id` linkage.
- Customer APIs: filter by authenticated user's `tenant_id` — wrong tenant → **404**.
- **No cross-tenant** alert visibility unless SOC role explicitly spans tenants.

---

## 6. Customer portal safety

Customer portal must **never** expose:

- Raw Suricata `eve.json`, packet payloads, or full rule metadata
- **Raw logs** of any kind in customer-facing APIs
- Raw Wazuh alerts or indexer documents
- Source/destination IPs unless explicitly approved in a future safe-design KB
- Sensor internal hostnames, cluster URLs, or credentials

Customers see **normalized, plain-English summaries** only (future KB-057 adapter).

**No secrets** in Git, docs, or customer API responses.

---

## 7. Relationship to prior KBs

| KB | Relationship |
|---|---|
| **KB-036** | Enterprise architecture — network sensors feed Wazuh cluster |
| **KB-041** | Wazuh Manager live on VM 101 |
| **KB-042** | Agent enrollment pattern reused (passwordless authd) |
| **KB-043** | Suricata sensor live and producing `eve.json` |
| **KB-057** | Live adapter into `security_alerts` |

---

## 8. Live execution and remaining deferrals

| Item | Status |
|---|---|
| Ansible `suricata_wazuh` role (safe default = **preflight**) | Live |
| Wazuh agent 4.14.6 on VM 106 as `suricata-sensor` | Live |
| `localfile` JSON monitor for `/var/log/suricata/eve.json` | Live |
| Tenant→agent-group mapping admin UI | Deferred |
| MSSP control-plane Suricata adapter | **KB-057** |
| Shuffle/TheHive forwarding | **KB-049** |

### Ansible (from VM 112)

```bash
cd /home/secadmin/mssp-automation/ansible
ansible-playbook -i inventory/hosts.yml playbooks/suricata-wazuh.yml
ansible-playbook -i inventory/hosts.yml playbooks/suricata-wazuh.yml \
  -e suricata_wazuh_execution_mode=enroll \
  -e suricata_wazuh_live_enroll_approved=true
ansible-playbook -i inventory/hosts.yml playbooks/suricata-wazuh.yml \
  -e suricata_wazuh_execution_mode=validate
```

---

## 9. Decision summary (approved defaults)

| # | Decision | Choice |
|---|---|---|
| D1 | Primary integration path (lab) | **Option A** — Wazuh agent on VM 106 tailing `eve.json` |
| D2 | Destination | Wazuh Manager on VM 101 |
| D3 | Customer visibility | Normalized summaries only — **no raw Suricata logs** |
| D4 | Tenant scoping | Agent groups / admin mapping — not client parameters |
| D5 | Secrets | Env/secret store only — **no secrets** in Git or docs |

---

## 10. What KB-044 changes (and must not)

### Changes

- `docs/KB044_SURICATA_WAZUH_INTEGRATION.md` (this file)
- `scripts/kb044_validate_suricata_wazuh_integration.sh`
- `ansible/roles/suricata_wazuh/`
- `ansible/playbooks/suricata-wazuh.yml`
- `CONTEXT.md`, `docs/AI_PROMPT_LEDGER.md`

### Must not change

- `backend-api/`, `frontend-customer/`, `frontend-admin/`
- `postgres/init/`, `docker-compose.yml`, `.env`

---

## 11. Validation

```bash
cd /opt/mssp-control
chmod +x scripts/kb044_validate_suricata_wazuh_integration.sh
./scripts/kb044_validate_suricata_wazuh_integration.sh
```

Expected final line:

```text
KB-044 SURICATA WAZUH INTEGRATION VALIDATION PASSED
```
