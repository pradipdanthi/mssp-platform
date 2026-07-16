# KB-059 — Multi-Cluster Capacity and Customer Placement

Status: Implemented (pending validation/commit).  
Module type: **Planning / documentation only** — no runtime code, schema, compose, or `.env` changes.

Builds on: `docs/KB037_CLUSTER_APPLIANCE_REGISTRY_PLANNING.md`, `docs/KB038_TENANT_DEPLOYMENT_MODE_PLANNING.md`, and `docs/KB036_MSSP_PLATFORM_ARCHITECTURE_ROADMAP.md` (Phase 12).  
Related: KB-040/041 (Wazuh cluster deploy), KB-057 (live integration), KB-060 (ops runbooks).

---

## 1. Purpose

Define **multi-cluster capacity planning** and a **customer (tenant) placement algorithm sketch** so MSSP operators can assign cloud/hybrid tenants to shared SOC clusters safely and predictably.

This KB documents:

- Capacity dimensions on `soc_clusters` (agents, EPS, storage, retention)
- Placement rules for `primary_cluster_id` (KB-037 / KB-038)
- Admin-only assignment workflow and customer safety boundaries
- Explicit rule: **no fixed customer count** per cluster

**No runtime implementation** in KB-059. Schema and admin APIs remain future modules.

---

## 2. Current baseline

| Area | Status |
|---|---|
| `soc_clusters` table | Planned in KB-037 — not implemented |
| Tenant `primary_cluster_id` | Planned in KB-037 — not implemented |
| Tenant `deployment_mode` | Planned in KB-038 — not implemented |
| Capacity enforcement | Design only |
| Placement automation | Design only (this KB) |
| SOC stack / multi-cluster lab | Not deployed |

---

## 3. Capacity model (`soc_clusters`)

Reuse KB-037 field design. Capacity is measured by **resource budgets**, not by “N customers per cluster.”

| Dimension | Planned fields / signals | Why it matters |
|---|---|---|
| **Agents** | `max_agents`, `current_agent_count` | Endpoint/agent load on Wazuh Manager |
| **EPS** | `eps_budget`, measured EPS (future worker) | Ingest and rule-evaluation pressure |
| **Storage** | `storage_gb_budget`, optional GB/day estimate | Indexer/OpenSearch disk |
| **Retention** | `retention_days` | Storage growth over time |
| **Health / status** | `status`, `sync_health_status` | Only `active` clusters accept new tenants |
| **Isolation / region** | `region_label`, admin notes | Optional affinity (compliance, latency) — admin policy |

### 3.1 Hard rules

- **No fixed customer count** — never encode “exactly 10 tenants per cluster” (or any hardcoded tenant quota) as the primary capacity rule.
- A cluster may host **many small** tenants or **few large** tenants; placement depends on agent/EPS/storage headroom.
- When headroom is insufficient → set cluster `status = full` (or `maintenance`) and place **new** tenants on another `active` cluster (or provision a new cluster — KB-040/041 / KB-060).
- Capacity JSON, internal URLs, and budgets are **admin-only** — never customer portal.

### 3.2 Headroom sketch (planning formula)

Future worker or admin API may compute:

```text
agent_headroom   = max_agents - current_agent_count
eps_headroom     = eps_budget - current_eps
storage_headroom = storage_gb_budget - current_storage_gb

eligible = status == 'active'
       AND agent_headroom   >= estimated_new_agents
       AND eps_headroom     >= estimated_new_eps
       AND storage_headroom >= estimated_new_storage_gb
```

Estimated new demand comes from onboarding questionnaire / admin input (agent count, expected EPS, retention needs) — not from customer self-service.

---

## 4. Tenant placement and `primary_cluster_id`

### 4.1 When placement applies (KB-038)

| `deployment_mode` | `primary_cluster_id` | Placement |
|---|---|---|
| `cloud` | **Required** | Must assign to eligible `active` cluster |
| `hybrid` | **Required** | Same — primary cloud cluster for cloud-path processing |
| `on_prem` | **Must be NULL** | No shared cluster placement |

### 4.2 Placement algorithm sketch (admin / future automation)

Input: tenant id, `deployment_mode`, estimated agents/EPS/storage, optional `region_label` preference.

```
1. If deployment_mode == on_prem:
     set primary_cluster_id = NULL; stop.

2. Load soc_clusters where status = 'active'
     (exclude full, maintenance, planned, provisioning, retired).

3. Filter by capacity headroom (agents, EPS, storage)
     against estimated demand; respect retention policy fit.

4. Optional filter: region_label / isolation policy match.

5. Rank eligible clusters (suggested default order):
     a. Highest combined headroom score
        (normalize agent/EPS/storage remaining fractions)
     b. Prefer clusters already serving fewer large tenants
        only as a soft tie-break — still not a fixed customer count
     c. Prefer matching region_label if set

6. Select top-ranked cluster → propose primary_cluster_id.

7. Admin confirms (or override) → audit log assignment.

8. If no eligible cluster → create/provision new cluster
     (ops: KB-040/041 + KB-060); do not oversubscribe.
```

### 4.3 Reassignment

- Moving a tenant to another cluster is **admin-only**, audited, and out of band for customers.
- Reassignment must re-check headroom on the target cluster.
- Customer portal never shows cluster IDs, codes, or capacity.

---

## 5. Admin workflow (future UI/API)

Builds on KB-037 admin sketch:

| Step | Actor | Action |
|---|---|---|
| 1 | SOC / platform_admin | Create or select `active` cluster with capacity |
| 2 | SOC | Set tenant `deployment_mode` (KB-038) |
| 3 | SOC / automation | Run placement sketch → propose `primary_cluster_id` |
| 4 | SOC | Confirm assignment via admin API |
| 5 | Future adapters | Use cluster metadata for ingestion scope (KB-057+) |

Proposed endpoints remain under `/admin/...` only (see KB-037 §6). Customer frontend must **never** call `/admin`.

---

## 6. Customer and security boundaries

- Placement and capacity are **admin-only**.
- Customer portal: appliance/asset health and safe summaries only — **no** `primary_cluster_id`, cluster codes, EPS budgets, storage budgets, or retention internals.
- Tenant isolation unchanged: customer APIs filter by caller `tenant_id`; wrong tenant → **404**.
- **No secrets** in this document, Git, or customer responses (no Wazuh passwords, API keys, tokens, Indexer credentials, or connection strings).
- Cluster URLs and credentials stay in `.env` / secret store, referenced by `cluster_code` — never committed.

---

## 7. Links to KB-037 and KB-038

| Topic | Source |
|---|---|
| `soc_clusters` entity and capacity fields | **KB-037** |
| `primary_cluster_id` on tenants (Option A) | **KB-037** |
| `deployment_mode` cloud / on_prem / hybrid routing | **KB-038** |
| When `primary_cluster_id` is required vs NULL | **KB-038** |
| Multi-cluster placement at scale | **This KB (059)** — Phase 12 |

Parent roadmap: `docs/KB036_MSSP_PLATFORM_ARCHITECTURE_ROADMAP.md` Phase 12 (KB-058–060).

---

## 8. Explicit deferrals

| Item | Deferred to |
|---|---|
| Schema migration for `soc_clusters` / `primary_cluster_id` | Future implementation KB |
| Admin API + UI implementation | Future KB after schema |
| Live capacity worker (EPS/storage rollups) | Future KB + **KB-060** monitoring |
| On-prem appliance template | **KB-058** |
| New physical/virtual cluster provisioning | KB-040/041 + **KB-060** |
| Customer-visible cluster choice | **Out of scope** — never |

---

## 9. Decision summary

| Decision | Choice |
|---|---|
| Capacity basis | Agents, EPS, storage, retention (+ health/region) |
| Fixed customer count | **Never** as primary rule |
| Mapping field | `primary_cluster_id` (KB-037) |
| Mode gating | KB-038 `deployment_mode` |
| Who places tenants | Admin/SOC only (optional assisted ranking) |
| Secrets | None in docs/Git/customer APIs |

---

## 10. Validation

```bash
cd /opt/mssp-control
chmod +x scripts/kb059_validate_multi_cluster_capacity_customer_placement.sh
./scripts/kb059_validate_multi_cluster_capacity_customer_placement.sh
```

Expected success line:

```text
KB-059 MULTI-CLUSTER CAPACITY CUSTOMER PLACEMENT VALIDATION PASSED
```

---

## 11. What KB-059 changes (and must not)

### Changes (documentation only)

- `docs/KB059_MULTI_CLUSTER_CAPACITY_CUSTOMER_PLACEMENT.md` (this file)
- `scripts/kb059_validate_multi_cluster_capacity_customer_placement.sh`

### Must not change

- `backend-api/`, `frontend-customer/`, `frontend-admin/` runtime code
- `postgres/init/`, `docker-compose.yml`, `.env`
- No container restarts, no SOC tool installs, no VM 101–111 creation in this module
