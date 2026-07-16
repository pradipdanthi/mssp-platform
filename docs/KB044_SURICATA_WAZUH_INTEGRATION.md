# KB-044 — Suricata to Wazuh Integration

Status: Implemented (pending validation/commit).  
Branch: `kb039-kb060-platform-roadmap-execution`  
Module type: **Planning / documentation only** — no runtime code, schema, compose, or `.env` changes.

Builds on: `docs/KB036_MSSP_PLATFORM_ARCHITECTURE_ROADMAP.md`, `docs/KB037_CLUSTER_APPLIANCE_REGISTRY_PLANNING.md`, `docs/KB038_TENANT_DEPLOYMENT_MODE_PLANNING.md`, and **KB-043** Suricata Sensor Deployment Plan (VM 106).

---

## 1. Purpose

Define how **Suricata IDS/IPS alerts** from the lab sensor VM flow into the **Wazuh stack** (VM 101) so network detections become searchable, correlatable, and available to future MSSP adapters — without exposing raw Suricata logs to customers.

This KB is **planning only**. Live Suricata→Wazuh wiring, agent enrollment, and control-plane ingestion are **future implementation KBs**.

---

## 2. Current baseline

| Area | Status |
|---|---|
| VM 106 `suricata-sensor` | **Not deployed** — planned in KB-043 |
| VM 101 `wazuh-stack` | **Not deployed** — planned in KB-040/041 |
| Suricata → Wazuh path | **Not configured** — design only |
| `security_alerts` ingestion | Control plane schema exists; no live Suricata adapter |
| Customer portal | No raw Suricata data — must remain that way |

---

## 3. Architecture

### 3.1 Target data flow (cloud / lab)

```
Network traffic (SPAN/mirror or lab tap)
  → VM 106 Suricata (eve.json alerts)
  → Wazuh Manager on VM 101 (log collector / integration)
  → Wazuh Indexer / OpenSearch
  → Future MSSP adapter (KB-057) → normalized PostgreSQL
  → Admin/SOC dashboard → customer-safe portal
```

### 3.2 Integration options (planning — choose one at implementation)

| Option | Description | Notes |
|---|---|---|
| **A — Wazuh agent on sensor VM** | Suricata `eve.json` monitored by Wazuh agent on VM 106 | Common lab pattern; agent reports to VM 101 manager |
| **B — Remote syslog** | Suricata alerts forwarded via syslog to Wazuh manager | Requires syslog parsing rules on manager |
| **C — Filebeat / custom shipper** | Ship `eve.json` to indexer path | Defer unless agent path insufficient |

**Recommended for lab v1:** Option A — Wazuh agent on VM 106 tailing Suricata `eve.json` with Suricata decoder/rules on manager.

### 3.3 Normalization alignment (KB-036)

| Field concept | Source |
|---|---|
| `tenant_id` | Assigned via agent group / tenant mapping (KB-037/038) — never from client-supplied IDs alone |
| `source_platform` | `suricata` (network) + `wazuh` (transport/index path) |
| `alert` | Normalized summary — signature, severity, category — **not** full `eve.json` to customers |
| `sync_health_status` | Sensor + manager health rolled up per appliance/cluster |

---

## 4. VM references

| VM | Name | Role in this KB |
|---|---|---|
| **VM 101** | `wazuh-stack` | Wazuh Manager receives Suricata-derived events; Indexer stores them |
| **VM 106** | `suricata-sensor` | Suricata generates `eve.json` alerts — source of network IDS events |

VMs are **roadmap placeholders** until KB-040/041 (Wazuh) and KB-043 (Suricata sensor) are implemented.

---

## 5. Tenant isolation

- Suricata events on shared lab infrastructure must be **tagged to the correct tenant** before they appear in customer-facing records.
- Mapping mechanisms (future implementation):
  - Wazuh **agent groups** or **labels** per tenant
  - Network segment / VLAN → tenant mapping (admin-configured)
  - Appliance `tenant_id` linkage for sensor VMs registered as appliances (KB-037 extensions)
- Customer APIs: filter by authenticated user's `tenant_id` — wrong tenant → **404**.
- **No cross-tenant** alert visibility in admin queries unless SOC role explicitly spans tenants.

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
| **KB-036** | Enterprise architecture — network sensors feed Wazuh cluster, adapters normalize to control plane |
| **KB-037** | Cluster registry — Suricata path scoped to assigned `soc_cluster` |
| **KB-038** | `deployment_mode` — cloud/hybrid tenants use shared sensor+cluster path; on-prem may use local Suricata (KB-058) |
| **KB-040/041** | Wazuh stack must exist on VM 101 before integration |
| **KB-043** | Suricata sensor on VM 106 must be deployed and producing `eve.json` |
| **KB-057** | Live adapter ingests normalized alerts into `security_alerts` |

---

## 8. Explicit deferrals

| Item | Deferred to |
|---|---|
| Wazuh manager Suricata decoder/rules install | KB-044 implementation KB (after KB-040/041 + KB-043) |
| Wazuh agent on VM 106 | KB-044 implementation KB |
| Tenant→agent-group mapping admin UI | Future admin KB |
| MSSP control-plane Suricata adapter | KB-057 |
| On-prem Suricata integration | KB-058 appliance template |
| Shuffle/TheHive forwarding of Suricata alerts | KB-049 |

---

## 9. Decision summary (approved defaults)

| # | Decision | Choice |
|---|---|---|
| D1 | Primary integration path (lab) | Wazuh agent on VM 106 tailing `eve.json` |
| D2 | Destination | Wazuh Manager on VM 101 |
| D3 | Customer visibility | Normalized summaries only — **no raw Suricata logs** |
| D4 | Tenant scoping | Agent groups / admin mapping — not client parameters |
| D5 | Secrets | Env/secret store only — **no secrets** in Git or docs |

---

## 10. What KB-044 changes (and must not)

### Changes

- `docs/KB044_SURICATA_WAZUH_INTEGRATION.md` (this file)
- `scripts/kb044_validate_suricata_wazuh_integration.sh`

### Must not change

- `backend-api/`, `frontend-customer/`, `frontend-admin/`
- `postgres/init/`, `docker-compose.yml`, `.env`
- No live Suricata or Wazuh deployment in this KB

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
