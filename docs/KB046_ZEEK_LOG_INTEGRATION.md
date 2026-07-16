# KB-046 — Zeek Log Integration

Status: Implemented (pending validation/commit).  
Branch: `kb039-kb060-platform-roadmap-execution`  
Module type: **Planning / documentation only** — no runtime code, schema, compose, or `.env` changes.

Builds on: `docs/KB045_ZEEK_SENSOR_DEPLOYMENT_PLAN.md`, `docs/KB036_MSSP_PLATFORM_ARCHITECTURE_ROADMAP.md`, `docs/KB037_CLUSTER_APPLIANCE_REGISTRY_PLANNING.md`, and Wazuh stack plans **KB-040/041**.

---

## 1. Purpose

Define how **Zeek logs** from VM 107 integrate with the **Wazuh stack** on VM 101 so network metadata becomes indexed, searchable, and available to future MSSP adapters — parallel to Suricata integration (KB-044).

This KB is **planning only**. Log shippers, Wazuh rules, and adapter code are **future implementation KBs**.

---

## 2. Current baseline

| Area | Status |
|---|---|
| VM 107 Zeek sensor | **Not deployed** — planned KB-045 |
| VM 101 Wazuh stack | **Not deployed** — planned KB-040/041 |
| Zeek → Wazuh path | **Not configured** |
| Zeek log types | Design assumes `conn.log`, `dns.log`, `http.log`, `ssl.log`, `notice.log` |
| Customer portal | No raw Zeek logs — must remain that way |

---

## 3. Architecture

### 3.1 Target data flow

```
VM 107 Zeek (rotated log files)
  → log shipper / Wazuh agent file monitoring
  → Wazuh Manager VM 101 (decoders / rules)
  → Wazuh Indexer / OpenSearch
  → Future MSSP adapter (KB-057) → normalized PostgreSQL
  → Admin/SOC dashboard → customer-safe portal
```

### 3.2 Integration options (planning)

| Option | Description | Notes |
|---|---|---|
| **A — Wazuh agent file monitoring** | Agent on VM 107 tails Zeek JSON logs | Mirrors KB-044 Suricata pattern |
| **B — Zeek JSON + custom Wazuh rules** | Manager-side rules map Zeek JSON to alerts | Required for actionable MSSP alerts |
| **C — Direct indexer ingest** | Filebeat to OpenSearch | Defer — prefer Wazuh manager path for consistency |

**Recommended for lab v1:** Option A + B — Wazuh agent on VM 107 with Zeek-specific decoders/rules on manager.

### 3.3 What gets normalized (future adapter)

| Zeek signal | Customer-safe projection (examples) |
|---|---|
| `notice.log` | "Unusual DNS volume detected" — no full query lists |
| `conn.log` anomalies | "New external connection pattern" — no full 5-tuple dumps |
| `ssl.log` | "Certificate anomaly" — no raw JA3/hex blobs unless approved |

Full Zeek records remain in **SOC/indexer** — **never** in customer portal.

---

## 4. VM references

| VM | Name | Role in this KB |
|---|---|---|
| **VM 107** | `zeek-sensor` | Zeek log source |
| **VM 101** | `wazuh-stack` | Wazuh Manager + Indexer — log destination |
| **VM 100** | `mssp-control` | Normalized metadata only via future adapter |

---

## 5. Tenant isolation

- Zeek logs on shared infrastructure must be **scoped to tenant** at normalization time.
- Mechanisms (future):
  - Wazuh agent groups / labels per tenant
  - Subnet→tenant mapping configured by admin
  - `tenant_id` on all ingested `security_alerts` rows from adapter (KB-057)
- Customer API: authenticated `tenant_id` filter — cross-tenant ID guess → **404**.
- SOC roles may query raw/indexed Zeek in admin tools — **not** exposed via customer APIs.

---

## 6. Customer portal safety

Customer portal must **never** expose:

- Raw Zeek JSON logs or indexer documents
- **Raw logs** of any kind in customer-facing APIs
- Full connection tables, DNS query lists, HTTP URLs/headers
- PCAP references or file paths on sensor
- Zeek script source, internal rule IDs, or manager URLs

**No secrets** in Git, docs, or customer API responses.

---

## 7. Relationship to prior KBs

| KB | Relationship |
|---|---|
| **KB-036** | Zeek in network detection phase; normalized record model |
| **KB-037/038** | Cluster and deployment mode scope sensor→tenant mapping |
| **KB-040/041** | Wazuh stack prerequisite on VM 101 |
| **KB-044** | Parallel Suricata→Wazuh integration pattern |
| **KB-045** | Zeek sensor on VM 107 must exist and produce logs |
| **KB-049** | High-severity Zeek notices may trigger Shuffle→TheHive workflow |
| **KB-057** | MSSP adapter ingests customer-safe alert summaries |

---

## 8. Explicit deferrals

| Item | Deferred to |
|---|---|
| Wazuh agent install on VM 107 | KB-046 implementation KB |
| Zeek decoder/rules on Wazuh manager | KB-046 implementation KB |
| Log volume / retention tuning | Implementation + KB-060 ops runbook |
| MSSP PostgreSQL ingestion | KB-057 |
| On-prem Zeek log paths | KB-058 |

---

## 9. Decision summary (approved defaults)

| # | Decision | Choice |
|---|---|---|
| D1 | Primary ship path | Wazuh agent file monitoring on VM 107 |
| D2 | Index destination | Wazuh Indexer via manager on VM 101 |
| D3 | Customer visibility | Summaries only — **no raw Zeek logs** |
| D4 | Alert-worthy logs | Prioritize `notice.log` + selected anomalies |
| D5 | Secrets | Env/secret store only — **no secrets** in Git or docs |

---

## 10. What KB-046 changes (and must not)

### Changes

- `docs/KB046_ZEEK_LOG_INTEGRATION.md` (this file)
- `scripts/kb046_validate_zeek_log_integration.sh`

### Must not change

- `backend-api/`, `frontend-customer/`, `frontend-admin/`
- `postgres/init/`, `docker-compose.yml`, `.env`

---

## 11. Validation

```bash
cd /opt/mssp-control
chmod +x scripts/kb046_validate_zeek_log_integration.sh
./scripts/kb046_validate_zeek_log_integration.sh
```

Expected final line:

```text
KB-046 ZEEK LOG INTEGRATION VALIDATION PASSED
```
