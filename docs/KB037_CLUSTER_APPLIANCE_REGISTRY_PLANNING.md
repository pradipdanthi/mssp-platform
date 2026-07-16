# KB-037 — Cluster and Appliance Registry Planning

Status: Validated (pending tag).  
Branch: `kb037-cluster-appliance-registry-planning`  
Module type: **Planning / documentation only** — no runtime code, schema, compose, or `.env` changes.

Parent roadmap: `docs/KB036_MSSP_PLATFORM_ARCHITECTURE_ROADMAP.md` (Phase 3).

---

## 1. Purpose

Design the **cluster registry** and **appliance registry extensions** needed before MSSP can onboard customers onto shared SOC clusters or on-prem appliances at scale.

This KB produces an **approved planning document** only. Schema migrations, admin APIs, and UI come in **later KB modules** after this plan is validated and committed.

**Deferred to KB-038:** tenant `deployment_mode` (`cloud` / `on-prem` / `hybrid`) and routing rules per mode.

---

## 2. Current baseline (what exists today)

| Area | Status |
|---|---|
| `tenants` table | Exists — no `deployment_mode`, no `cluster_id` |
| `appliances` table | Exists — tenant-scoped; registration/heartbeat (KB-016) |
| Admin appliance APIs | KB-015/017 — detail, patch, tokens, credentials |
| Customer appliance APIs | KB-023/035 — safe list + detail |
| Cluster concept | **Does not exist** — no table, no API, no UI |
| SOC stack | **Not deployed** — design only |

Existing `appliances` is the foundation for **appliance registry extensions**. Do not replace it — extend it.

---

## 3. Cluster registry — proposed entity

### 3.1 Table name (proposed)

`soc_clusters` — created in a **future schema KB**, not in KB-037.

### 3.2 Purpose

Register each **shared MSSP SOC / Wazuh cluster** (lab: VM 101 `wazuh-stack`; production: dedicated cluster VMs).

A cluster may serve **multiple tenants** based on **capacity**, not a fixed customer count.

### 3.3 Proposed fields (admin-only visibility)

| Field | Type / notes |
|---|---|
| `id` | UUID primary key |
| `cluster_code` | Short unique code (e.g. `SOC-EU-01`) — admin reference |
| `cluster_name` | Human label |
| `status` | `planned`, `provisioning`, `active`, `maintenance`, `full`, `retired` |
| `region_label` | Optional site/region label (not customer-facing) |
| `max_agents` | Capacity: agent count budget |
| `current_agent_count` | Rolled up from assigned tenants/appliances (maintained by future worker or on-write) |
| `eps_budget` | Events per second budget (numeric) |
| `storage_gb_budget` | Index/storage budget |
| `retention_days` | Log retention policy for this cluster |
| `wazuh_manager_url` | **Admin-only** — env/config reference, never customer API, never Git |
| `wazuh_indexer_url` | **Admin-only** — same rules |
| `sync_health_status` | `healthy`, `degraded`, `unknown`, `offline` |
| `last_health_check_at` | Timestamp |
| `notes` | **Admin-only** internal notes |
| `created_at`, `updated_at` | Standard audit |

### 3.4 Capacity rules (must not be violated in implementation)

- Capacity planning uses: **agents**, **EPS**, **GB/day**, **retention**, **performance**, **isolation** — **not** a hardcoded number of customers (e.g. not “exactly 10 customers per cluster”).
- When `current_agent_count` (and/or EPS/storage thresholds) approach limits → mark cluster `full` or `maintenance` and assign **new tenants to a new cluster**.
- Cluster assignment is an **admin/SOC operation** — customers never choose or see cluster internals.

### 3.5 Forbidden in customer-facing APIs

- Cluster IDs, cluster codes, internal URLs
- Wazuh/Indexer credentials
- Raw capacity JSON blobs
- Internal admin notes

---

## 4. Tenant ↔ cluster mapping (design only)

### 4.1 Proposed approach

**Option A (recommended for v1):** nullable `primary_cluster_id UUID REFERENCES soc_clusters(id)` on `tenants`.

- Cloud-path tenants get a cluster assignment.
- On-prem-only tenants: `NULL` (KB-038 will formalize via `deployment_mode`).
- Hybrid: primary cluster + on-prem appliances (KB-038).

**Option B (future scale):** join table `tenant_cluster_assignments` for multi-cluster or migration history — defer unless needed.

KB-037 recommends **Option A** for first implementation KB.

### 4.2 Assignment workflow (future admin UI/API)

1. SOC creates or selects active cluster with available capacity.
2. SOC assigns tenant → cluster (admin only).
3. Future Wazuh adapter uses cluster metadata to scope ingestion (KB-057+).
4. Reassignment (tenant move to new cluster) is admin-only, audited — not in KB-037 scope.

---

## 5. Appliance registry extensions

Extend existing `appliances` table in a **future schema KB** — do not duplicate a second appliance table.

### 5.1 Proposed new columns

| Column | Purpose |
|---|---|
| `deployment_role` | `cloud_collector` \| `on_prem_appliance` \| `hybrid_edge` (exact enum TBD in KB-038) |
| `cluster_id` | Optional FK → `soc_clusters` — set for cloud-path appliances tied to a cluster |
| `source_platform` | Normalization hint: `wazuh`, `on_prem_bundle`, etc. — aligns with KB-036 record model |
| `sync_health_status` | `healthy`, `degraded`, `unknown`, `offline` — metadata sync to control plane |
| `last_sync_at` | Last successful metadata sync timestamp |

### 5.2 Reuse existing columns (no change)

- `tenant_id`, `appliance_name`, `site_name`, `status`, heartbeat fields
- `appliance_api_key_*` (KB-016) — never exposed to customers
- Registration/heartbeat APIs (KB-016) — extend behavior in future KBs, do not break

### 5.3 Customer portal (unchanged safety)

Customer APIs continue to expose **only** KB-023/035 safe fields. New registry columns are **admin-only** unless explicitly projected in a customer-safe shape later.

---

## 6. Future admin API sketch (not implemented in KB-037)

Document for implementation KB(s). All under `/admin`, RBAC per existing patterns.

| Method | Path (proposed) | Purpose |
|---|---|---|
| GET | `/admin/clusters` | List clusters (safe admin fields) |
| POST | `/admin/clusters` | Create cluster (`platform_admin`) |
| GET | `/admin/clusters/{cluster_id}` | Cluster detail + capacity summary |
| PATCH | `/admin/clusters/{cluster_id}` | Update status, capacity budgets, labels |
| GET | `/admin/clusters/{cluster_id}/tenants` | Tenants assigned to cluster |
| PATCH | `/admin/tenants/{tenant_id}/cluster-assignment` | Assign/reassign primary cluster |
| GET | `/admin/appliances/{appliance_id}` | **Extend** existing detail with registry fields |

**No DELETE** — use `status = retired` / `full` (consistent with KB-015 appliance pattern).

**Credentials:** cluster connection secrets live in **`.env` or secret store only** — referenced by `cluster_code` in config, never stored in customer-visible responses or Git.

---

## 7. Normalization alignment (KB-036)

Control plane records should carry:

| Concept | Cluster/appliance link |
|---|---|
| `tenant` | Existing |
| `source_platform` | Appliance `source_platform`; cluster for cloud ingestion scope |
| `sync_health_status` | On cluster and appliance |
| `asset`, `alert`, `incident`, etc. | Future adapters attach `cluster_id` or `appliance_id` internally — admin only |

Customers see normalized, tenant-scoped, safe projections only.

---

## 8. Security and tenant isolation

- Cluster registry APIs: **admin/SOC roles only** — same RBAC tier as tenant/appliance admin.
- Customer APIs: **no cluster fields** — tenant isolation unchanged (`require_tenant_match`, 404 on mismatch).
- Never return: Wazuh passwords, API keys, `appliance_api_key_hash`, activation tokens, internal URLs to customers.
- Never commit secrets to Git or documentation. **No secrets** in repo docs, API responses to customers, or customer portal.

---

## 9. Explicit deferrals

| Item | Deferred to |
|---|---|
| Tenant `deployment_mode` (cloud/on-prem/hybrid) | **KB-038** |
| SQL migrations / new tables | Future implementation KB after KB-037/038 plans approved |
| Admin API implementation | Future KB after schema |
| Admin UI for clusters | Future KB |
| Live Wazuh cluster on VM 101 | KB-040/041 |
| Customer portal cluster visibility | Out of scope — customers see appliance posture only |

---

## 10. Recommended implementation sequence (after KB-037)

1. **KB-037** — this planning doc (validate, commit, tag)
2. **KB-038** — tenant deployment mode planning
3. **Future KB** — schema migration: `soc_clusters` + tenant `primary_cluster_id` + appliance extensions
4. **Future KB** — admin cluster APIs + validation
5. **Future KB** — admin UI cluster list/assign (if in scope)

---

## 11. Decision summary (approved defaults for planning)

| # | Decision | Choice |
|---|---|---|
| D1 | Cluster table name | `soc_clusters` |
| D2 | Tenant→cluster link (v1) | Nullable `primary_cluster_id` on `tenants` |
| D3 | Appliance registry | Extend `appliances` — no second table |
| D4 | Capacity model | Agents + EPS + storage + retention — not fixed customer count |
| D5 | Customer visibility | No cluster IDs or internal URLs in customer APIs |
| D6 | Deployment mode | **KB-038** — not KB-037 |

---

## 12. What KB-037 changes (and must not)

### Changes

- `docs/KB037_CLUSTER_APPLIANCE_REGISTRY_PLANNING.md` (this file)
- `scripts/kb037_validate_cluster_appliance_registry_planning.sh`
- `docs/AI_PROMPT_LEDGER.md`
- Light note in `CONTEXT.md` (active KB-037 planning)

### Must not change

- `backend-api/`, `frontend-customer/`, `frontend-admin/`
- `postgres/init/`, `docker-compose.yml`, `.env`

---

## 13. Validation

```bash
cd /opt/mssp-control
chmod +x scripts/kb037_validate_cluster_appliance_registry_planning.sh
./scripts/kb037_validate_cluster_appliance_registry_planning.sh
```

Expected final line:

```text
KB-037 CLUSTER APPLIANCE REGISTRY PLANNING VALIDATION PASSED
```
