# KB-038 — Tenant Deployment Mode Model Planning

Status: Implemented (pending validation/commit).  
Branch: `kb038-tenant-deployment-mode-planning`  
Module type: **Planning / documentation only** — no runtime code, schema, compose, or `.env` changes.

Builds on: `docs/KB037_CLUSTER_APPLIANCE_REGISTRY_PLANNING.md` and `docs/KB036_MSSP_PLATFORM_ARCHITECTURE_ROADMAP.md`.

---

## 1. Purpose

Define the **tenant deployment mode model** (`cloud` / `on_prem` / `hybrid`) and the **routing rules** that govern:

- When a tenant uses a shared SOC cluster (KB-037 `primary_cluster_id`)
- When a tenant uses on-prem appliances only
- How hybrid tenants combine both paths
- What data may sync to MSSP Control Plane (metadata only — never raw logs to customers)
- Admin onboarding workflow and customer visibility boundaries

This KB is **planning only**. Schema migrations and admin APIs are **future KB modules**.

---

## 2. Current baseline

| Area | Status |
|---|---|
| `tenants` table | Exists — no `deployment_mode`, no `primary_cluster_id` |
| KB-037 cluster design | `soc_clusters` + `primary_cluster_id` planned — not implemented |
| KB-037 appliance extensions | `deployment_role`, `cluster_id`, `source_platform`, `sync_health_status` planned |
| Customer portal | No deployment-mode UI |
| SOC stack | Not deployed — rules are design for future implementation |

---

## 3. Proposed tenant field: `deployment_mode`

Future column on `tenants` (implementation KB after KB-038):

```text
deployment_mode TEXT NOT NULL DEFAULT 'cloud'
  CHECK (deployment_mode IN ('cloud', 'on_prem', 'hybrid'))
```

### 3.1 Mode definitions

| Mode | Description |
|---|---|
| **`cloud`** | Tenant is served by MSSP **shared SOC/Wazuh cluster**. Detection and log processing occur in MSSP-hosted infrastructure. |
| **`on_prem`** | Customer policy requires logs to **remain on-premises**. Local appliance/stack processes data; only **safe metadata** syncs to control plane. |
| **`hybrid`** | **Combined** model: on-prem retention/processing **plus** cloud cluster path and/or central metadata sync under one tenant. |

### 3.2 Default

- **Lab/demo default:** `cloud` (simplest onboarding for DEMO tenants).
- Production onboarding: admin selects mode explicitly during tenant create/update.

---

## 4. Routing rules per deployment mode

### 4.1 Cloud (`deployment_mode = cloud`)

| Rule | Requirement |
|---|---|
| `primary_cluster_id` | **Required** — must reference an `active` cluster with available capacity (KB-037) |
| Appliances | Cloud collectors/agents; `deployment_role = cloud_collector`; optional `cluster_id` |
| Raw logs | Stay in SOC cluster — **never** in customer portal |
| Metadata to control plane | Normalized alerts, incidents, asset/appliance health, recommendations, reports |

### 4.2 On-prem (`deployment_mode = on_prem`)

| Rule | Requirement |
|---|---|
| `primary_cluster_id` | **Must be NULL** — no shared cloud cluster assignment |
| Appliances | At least one `on_prem_appliance` expected before tenant marked fully active |
| `deployment_role` | `on_prem_appliance` |
| Raw logs | **Never leave customer site**; **never** in customer portal |
| Metadata to control plane | Safe summaries only: alert/incident summary, health, recommendations, report summary, case reference |

### 4.3 Hybrid (`deployment_mode = hybrid`)

| Rule | Requirement |
|---|---|
| `primary_cluster_id` | **Required** — primary cloud cluster for cloud-path processing |
| Appliances | **Both** allowed: `on_prem_appliance` + `cloud_collector` (optional `hybrid_edge`) |
| Raw logs | On-prem portion stays local; cloud portion in cluster — **never** raw logs to customer portal |
| Metadata to control plane | Merged normalized records under single `tenant_id` |

---

## 5. Appliance `deployment_role` (finalize KB-037 TBD)

| Value | Used when |
|---|---|
| `cloud_collector` | `cloud` or `hybrid` — agent/collector on customer endpoints feeding cloud cluster |
| `on_prem_appliance` | `on_prem` or `hybrid` — local appliance at customer site |
| `hybrid_edge` | `hybrid` only — optional edge node (document for future; not required v1) |

### Cross-validation rules (future admin API enforcement)

| Tenant mode | Allowed appliance roles | Cluster on appliance |
|---|---|---|
| `cloud` | `cloud_collector` | Should match tenant `primary_cluster_id` when set |
| `on_prem` | `on_prem_appliance` | Must be NULL |
| `hybrid` | `cloud_collector`, `on_prem_appliance`, optionally `hybrid_edge` | `cluster_id` set only on cloud-path appliances |

---

## 6. Data flow summary

### Cloud

```
Customer endpoints / Wazuh agents
  → assigned soc_cluster (KB-037)
  → Wazuh Indexer / OpenSearch
  → Shuffle / TheHive (future)
  → MSSP adapters → normalized PostgreSQL
  → Admin/SOC dashboard → customer-safe portal
```

### On-prem

```
Customer log sources
  → on-prem appliance (local Wazuh/stack)
  → local retention
  → safe metadata sync API → MSSP Control Plane
  → Admin/SOC dashboard → customer-safe portal
```

### Hybrid

```
On-prem path (local retention) + cloud path (cluster)
  → each produces normalized tenant-scoped records
  → control plane merges by tenant_id
  → Admin/SOC dashboard → customer-safe portal
```

**Architecture invariant (KB-036):** Control plane consumes normalized records — it does not care which engine produced them.

---

## 7. Admin vs customer visibility

| Field / concept | Admin/SOC | Customer portal |
|---|---|---|
| `deployment_mode` | Yes (full enum) | Optional **safe label only** (e.g. “Cloud-managed SOC”, “On-premises appliance deployment”, “Hybrid deployment”) — no internal codes required in v1 |
| `primary_cluster_id` | Yes | **Never** |
| Cluster name, code, URLs | Yes | **Never** |
| Appliance registry extensions | Yes | Existing safe appliance fields only (KB-035) |
| Raw logs, raw Wazuh/Suricata/Zeek events | Yes (SOC tools — future) | **Never** |
| Sync health | Yes | Safe status labels only if exposed (e.g. “Appliance sync: healthy”) |

**No secrets** in Git, docs, or customer API responses.

---

## 8. Future admin onboarding workflow (document only)

1. **Create tenant** — set `deployment_mode`.
2. **If `cloud` or `hybrid`:** assign `primary_cluster_id` to cluster with capacity (KB-037).
3. **If `on_prem` or `hybrid`:** create activation token → register on-prem appliance (existing KB-015/016 flow).
4. **If `cloud` or `hybrid`:** future agent enrollment to assigned cluster (KB-042+).
5. **Mark tenant active** only when mode-specific minimums met (cluster assigned and/or appliance registered).
6. Future adapters (KB-057) tag all records with `tenant_id` + `source_platform`.

### Future API sketch (not implemented in KB-038)

| Method | Path | Notes |
|---|---|---|
| PATCH | `/admin/tenants/{tenant_id}` | Add `deployment_mode` — `platform_admin` only |
| PATCH | `/admin/tenants/{tenant_id}/cluster-assignment` | From KB-037 — required for cloud/hybrid |
| GET | `/admin/tenants/{tenant_id}/deployment-summary` | Admin view: mode + cluster + appliance counts |

Validation examples (future):

- Reject `cloud` without `primary_cluster_id`
- Reject `on_prem` with non-NULL `primary_cluster_id`
- Reject appliance `cluster_id` on pure `on_prem` tenant

---

## 9. Relationship to KB-037

| KB-037 concept | KB-038 usage |
|---|---|
| `soc_clusters` | Required for `cloud` and `hybrid` |
| `tenants.primary_cluster_id` | Required when mode is `cloud` or `hybrid`; NULL when `on_prem` |
| `appliances.deployment_role` | Must align with tenant `deployment_mode` |
| `appliances.cluster_id` | Set for cloud-path appliances only |
| Capacity model | Unchanged — agents/EPS/storage, not fixed customer count |

---

## 10. Security and compliance notes

- On-prem mode exists for customers whose **policy forbids logs leaving premises** — design must not silently exfiltrate raw logs via metadata sync APIs (future implementation must enforce field allowlists).
- Hybrid mode must document **which fields** may sync centrally — same customer-safe allowlist as on-prem metadata sync.
- Customer portal: **no raw logs**, **no raw JSON**, **no packet captures**, **no cluster internals** (KB-036 customer safety rules apply).

---

## 11. Explicit deferrals

| Item | Deferred to |
|---|---|
| SQL migration for `deployment_mode` / `primary_cluster_id` | Future implementation KB |
| Admin API enforcement | Future KB |
| Customer deployment summary UI | Future KB (optional) |
| Migrating existing DEMO tenants | Future migration KB — do not change live rows in KB-038 |
| Wazuh cluster install | KB-040/041 |
| Metadata sync API for on-prem | KB-058 |

---

## 12. Decision summary (approved defaults)

| # | Decision | Choice |
|---|---|---|
| D1 | Enum values | `cloud`, `on_prem`, `hybrid` |
| D2 | Default for new tenants | `cloud` (lab); admin selects in production |
| D3 | Cloud/hybrid cluster | `primary_cluster_id` required |
| D4 | On-prem cluster | `primary_cluster_id` must be NULL |
| D5 | Customer sees mode | Optional safe label only — no cluster details |
| D6 | Raw logs to customer | **Never** — all modes |

---

## 13. What KB-038 changes (and must not)

### Changes

- `docs/KB038_TENANT_DEPLOYMENT_MODE_PLANNING.md` (this file)
- `scripts/kb038_validate_tenant_deployment_mode_planning.sh`
- `docs/AI_PROMPT_LEDGER.md`
- Light update to `CONTEXT.md`

### Must not change

- `backend-api/`, `frontend-customer/`, `frontend-admin/`
- `postgres/init/`, `docker-compose.yml`, `.env`

---

## 14. Validation

```bash
cd /opt/mssp-control
chmod +x scripts/kb038_validate_tenant_deployment_mode_planning.sh
./scripts/kb038_validate_tenant_deployment_mode_planning.sh
```

Expected final line:

```text
KB-038 TENANT DEPLOYMENT MODE PLANNING VALIDATION PASSED
```
