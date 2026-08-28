# Enterprise Readiness & Gap Audit Report

**Organization:** Kevantic NikTiar™ MSSP Platform  
**Repository:** `/opt/mssp-control`  
**Audit date:** 2026-08-28  
**Mode:** Read-only architecture discovery — no code or configuration changes were made  
**Scope:** Codebase, `postgres/init` migrations (001–040), FastAPI backend, admin/customer frontends, appliance templates (VM 199), VM 100–115 inventory and live VM 100 resource snapshot

---

## Document control

| Field | Value |
|-------|-------|
| Report ID | ERGA-2026-08-28 |
| Git commit at audit | `2ec0eb0` |
| Golden appliance snapshot | `kb110-gitreleasesync-202608280309` |
| Prepared by | Architecture discovery audit (automated + manual verification) |

---

## Executive summary

The platform has a **solid multi-tenant product schema** and **consistent customer-route isolation** via `require_tenant_match()`, but **enterprise readiness is not yet complete**. Isolation is application-layer only (no Postgres RLS), upstream engines (Wazuh/TheHive/Shuffle) are largely **shared infrastructure with soft logical separation**, NDR/threat-hunting data fidelity has **known gaps**, and AI SOC assist has **good post-LLM guardrails** but **no pre-LLM deterministic bypass**.

| Area | Maturity | Top risk |
|------|----------|----------|
| Multi-tenancy (DB + customer API) | Medium–High | No RLS; EDR `agent_id` IDOR on shared Wazuh Manager |
| Engine segregation (Wazuh/TheHive/Shuffle) | Low–Medium | Shared Manager/webhook/workflow; tag-only TheHive fallback |
| IAM / ITDR | Low–Medium | JWT-only, no MFA/SSO; ITDR = Entra only; no Okta/GWS/4624 pipeline |
| Data pipeline / retention | Low | No retention jobs; NDR often seeded; no OLAP on VM 100 |
| AI SOC assist safety | Medium | Good normalization + opt-in auto-close; no pre-LLM hash veto; VM 115 SPOF |

---

## 1. Multi-tenancy & data isolation

### 1.1 PostgreSQL schema & `tenant_id` enforcement

#### What exists today

| Table | `tenant_id` | Enforcement |
|-------|-------------|-------------|
| `security_alerts` | `NOT NULL` FK → `tenants` | Indexed `(tenant_id, status)` — `001_mssp_core_schema.sql` |
| `incidents` | `NOT NULL` FK | Indexed `(tenant_id, status)` |
| `vulnerabilities` | `NOT NULL` FK | Unique `(tenant_id, source_platform, external_finding_id)` — `004_kb069_vulnerabilities.sql` |
| `alert_ai_triage_cache` | `NOT NULL` FK | Unique `(alert_id, content_hash)`; index `(tenant_id, updated_at)` — `038_alert_ai_triage_cache.sql` |
| `alert_suppressions` | Nullable (by design) | `scope='global'` is cross-tenant; `tenant`/`host` scopes require `tenant_id` — `037_alert_suppressions.sql` |

**Isolation model:** Query-level only. Every customer route resolves `tenants.short_code` → `tenant_id`, calls `require_tenant_match()` (`backend-api/app/api/dependencies.py`), then filters `WHERE tenant_id = %s`. SOC roles (`platform_admin`, `soc_manager`, `soc_analyst`) are intentionally cross-tenant.

#### What is missing

- **No Row Level Security (RLS)** anywhere in `postgres/init/` — zero `CREATE POLICY` / `ENABLE ROW LEVEL SECURITY` found.
- **Single shared DB role** via `psycopg` pool (`app/db/session.py`) — no `SET app.tenant_id` session context.
- **Defense-in-depth gap:** one missed `WHERE tenant_id` clause = full cross-tenant exposure with no DB backstop.

### 1.2 Shared tables / cache leak surfaces

| Component | Risk | Detail |
|-----------|------|--------|
| `alert_ai_triage_cache` reads | Low (today) | Cache lookup uses `alert_id + content_hash` without `tenant_id` filter (`ai_tier1_triage.py`). Safe only because callers pre-validate alert ownership. |
| `alert_suppressions` global scope | By design | SOC-managed global suppressions affect all tenants — intentional. |
| `ai_tier1_triage` cross-tenant FP signal | SOC-only | `global_same_rule` counts FPs across tenants — admin path only. |
| Redis AI queue | Low | Jobs carry explicit `tenant_id`; no shared keyspace without tenant prefix. |

### 1.3 Wazuh (VM 101) tenant mapping

**What exists:**

- Per-tenant agent groups: `tenant_<SHORT_CODE>` via `wazuh_group_for()` — `tenant_engine_provisioner.py`
- Reverse lookup: `resolve_short_code_by_wazuh_group()` joins `tenant_engine_bindings`
- Ingest resolves tenant from Wazuh agent group on webhook/sync paths

**Gaps / risks:**

- **Shared Wazuh Manager** for cloud-mode tenants — one Manager, many `tenant_*` groups. Group membership is organizational, **not enforced at Active Response dispatch time**.
- **Critical IDOR:** `EdrActionExecuteRequest.agent_id` is accepted from `customer_admin` and used verbatim in `_agent_from_context()` (`edr_actions.py:353-354`) **without verifying the agent belongs to the caller's tenant**. A tenant admin who knows another tenant's sequential agent ID (e.g. `"042"`) can trigger **isolate / kill / block-hash** on cloud Manager deployments.
- `_resolve_ar_command()` looks up OS type by `wazuh_agent_id` without `tenant_id` filter — script-selection collision risk across managers.

### 1.4 TheHive (VM 102) tenant mapping

**What exists:**

- Attempts per-tenant org: `MSSP-<SHORT_CODE>` via `thehive_org_for()`
- Fallback: **`tag_only` mode** → shared default org `THEHIVE_DEFAULT_ORG` (default `"MSSP"`) with tenant tag — `thehive_client.py`

**Gap:** When org creation fails (permissions/license), all tenants' cases can live in one TheHive org. Separation is a tag, not TheHive RBAC. Any TheHive user with org access sees all tenant cases.

### 1.5 Shuffle (VM 102) tenant mapping

**What exists:**

- **Single global** `SHUFFLE_WEBHOOK_URL` and workflow name for all tenants — `shuffle_edr_client.py`
- Tenant identity passed only as JSON field `tenant_short_code` in payload

**Gap:** No infrastructure-level isolation. Shuffle workflow logic must filter by field; this codebase cannot enforce Shuffle-side boundaries.

### 1.6 Verdict: multi-tenancy

| Layer | True segregation? |
|-------|-------------------|
| Customer portal API + Postgres queries | Yes (with EDR AR exception above) |
| Postgres RLS | No |
| Wazuh (cloud mode) | Partial — groups yes, AR dispatch no |
| TheHive | Partial — degrades to shared org |
| Shuffle | No — payload tagging only |

---

## 2. Identity & access management (IAM / ITDR)

### 2.1 Platform authentication

**What exists:**

- **JWT (HS256)** via `POST /auth/login` — `backend-api/app/api/routes/auth.py`
- Claims: `role`, `user_type`, `tenant_id`; live DB re-fetch on every request (`get_current_user`)
- **Portal separation enforced:** staff roles → admin portal only; customer roles → customer portal only
- **5 roles** with Postgres CHECK — `002_kb010_auth_rbac.sql`: `platform_admin`, `soc_manager`, `soc_analyst`, `customer_admin`, `customer_viewer`
- **Frontend:** `sessionStorage` tokens, `ProtectedRoute`, live `/auth/me` validation — both frontends
- **Non-JWT auth** for machine paths: appliance API keys, SOC sync keys, install tokens — 9 route files by design

**What is missing:**

| Capability | Status |
|------------|--------|
| MFA | Absent |
| SSO / SAML / OIDC | Absent |
| Rate limiting on `/auth/login` | Absent |

### 2.2 External engine credentials (Wazuh, TheHive, Velociraptor)

**Finding:** Separate native credentials per engine — no unified SSO.

- Wazuh API: server-side `wazuh_api_user` / password secrets
- TheHive: dedicated API user + org context
- Velociraptor: bridge API key (`VELOCIRAPTOR_BRIDGE_API_KEY`) to VM 110 `:8001`
- Customers never receive engine UI logins (by product design)

SOC staff needing raw engine consoles use independent logins per tool.

### 2.3 ITDR / identity provider ingestion

| Provider | Status | Evidence |
|----------|--------|----------|
| Microsoft Entra ID (M365) | Live | `itdr_graph_client.py` — Graph `signIns` + `directoryAudits`; `024_cloud_itdr_identity.sql` |
| AWS IAM / CloudTrail | DB placeholder only | Provider enum exists; no adapter |
| GCP IAM | DB placeholder only | No adapter |
| Okta | Absent | Keyword in taxonomy only |
| Google Workspace | Absent | No Admin/Reports API collector |
| Windows 4624/4625/4720/4728/4732 | Absent | Only 4688 (process creation) in telemetry scripts; lone 4625 in demo seed |

**ITDR event types implemented (Entra):** `IMPOSSIBLE_TRAVEL`, `MFA_BYPASS_ATTEMPT`, `ROGUE_ADMIN_ASSIGNED`, `EXTERNAL_MAIL_FORWARDING`, `SUSPICIOUS_LOGIN`

**Production behavior:** fail-closed — no synthetic events when Graph returns empty (`APP_ENV=production`).

---

## 3. High-throughput data pipeline & retention

### 3.1 PostgreSQL design (VM 100)

**What exists:**

- 40 sequential SQL init files — no Alembic/Flyway; applied via Docker `initdb.d`
- JSONB on alerts: `raw_event`, `win_eventdata`, `wazuh_full_log`, `mitre_mapping` — `040_wazuh_telemetry_columns.sql`
- Extracted scalar columns for hot fields: `hash_sha256`, `process_guid`, `parent_process`, etc. with partial btree indexes
- No GIN indexes on JSONB — ad-hoc JSON path hunting is unindexed
- No table partitioning — `security_alerts`, `audit_logs`, `tenant_ndr_events` grow as flat heaps

**Live lab sizing (VM 100):** ~17 MB total DB; `security_alerts` ≈ 1 row post-purge. Schema not battle-tested at production volume.

### 3.2 Zeek / Suricata / NDR (VM 106 → 101 → 100)

**Intended path:** VM 106 (Suricata + Zeek) → Wazuh agent → Wazuh Manager (101) → webhook → `soc_sync.py` → Postgres

**Critical fidelity gap:** `_normalize_wazuh_alert()` hardcodes `source_tool="wazuh"` (`soc_sync.py:278`) for all webhook alerts. NDR service filters `source_tool IN ('suricata','zeek')` (`ndr_service.py`) — never matches real ingress.

**Consequence:** `sync_tenant_ndr()` often finds zero real NDR rows and seeds 6 fabricated sample events with synthetic flow/byte metrics. Customer NDR dashboard can show demo data, not live sensor telemetry.

**Appliance-side alternative (not on VM 100):** `kevantic-appliance/appliance/datalake/archiver.py` — ZSTD Parquet + DuckDB + SQLite index, 365-day retention with disk-quota enforcement. Edge-local, not centralized.

### 3.3 Retention policies

| Policy | Implemented? |
|--------|--------------|
| Postgres row purge (alerts, audit, NDR) | No |
| `wazuh_retention_days` entitlement | Display/billing only |
| Wazuh Indexer retention | Not managed by control plane |
| Appliance datalake Parquet | Yes — 365d + 90% disk threshold |
| DR backup retention | Yes — 7 local + GDrive copies |

### 3.4 Infrastructure feasibility — ClickHouse / OLAP on VM 100

**Live VM 100 resources (measured 2026-08-28):**

| Resource | Value |
|----------|-------|
| RAM | 7.7 GB total, ~4.3 GB available |
| vCPU | 4 |
| Disk `/` | 166 GB, 62 GB free (62% used) |
| Docker stack | Postgres ~34 MB, Redis ~6 MB, API ~19 MB |

**Assessment:**

| Option | Feasibility |
|--------|-------------|
| ClickHouse colocated on VM 100 | Not recommended — insufficient RAM |
| ClickHouse on dedicated VM (≥16–32 GB RAM) | Feasible architecturally; zero ClickHouse code exists |
| DuckDB + Parquet (appliance pattern) | Feasible for edge; already in KB-093E |

**Prerequisites before OLAP:**

1. Fix `source_tool` tagging at ingest
2. Implement Postgres retention
3. Size OLAP host separately or upgrade VM 100 to ≥16 GB RAM

---

## 4. AI SOC assist reliability & deterministic guardrails

### 4.1 Architecture

| Pipeline | Host | Trigger | Timeout default |
|----------|------|---------|-----------------|
| Tier-1 triage (`ai_tier1_triage.py`) | VM 115 Ollama | On-demand (alert detail) | 8s → HTTP 504 |
| Alert analysis (`ai_alert_analysis.py`) | VM 115 | Redis queue (KB-092) | 90s; silent skip |
| SOC triage draft (`ai_soc_triage.py`) | VM 115 | Redis queue (KB-096) | 90s; retry up to 4× |
| Appliance local filter (`local_ai_filter.py`) | Appliance Ollama | Pre-forward gate (KB-108) | 60s; fail-open default |

Frontends (`lib/ai-triage.ts`) never call Ollama directly.

### 4.2 Failure handling

| Failure mode | Tier-1 | KB-092/096 | Appliance filter |
|--------------|--------|------------|-------------------|
| Ollama timeout | HTTP 504 | Log + skip; retry | Forward (fail-open) |
| Invalid JSON | HTTP 502 | Log + skip | Forward |
| VM 115 down | User error | No enrichment | Forward |

**Normalization bias (safe):** unknown verdict → `SUSPICIOUS`; invalid confidence → `50.0`; never auto-executes `ISOLATE_AGENT`.

### 4.3 Pre-LLM deterministic checks

**Exists (feeds prompt, does NOT skip LLM):**

- `compute_pre_score_hints()` — LOLBin names, temp paths, cmdline flags
- `_matches_known_fp_pattern()` — signed-path heuristics, prior FP history
- VirusTotal hash lookup — 2s timeout, enrichment only

**Missing:**

- No hash whitelist / known-good binary database that skips Ollama
- No pre-LLM veto gate — every uncached alert hits the 7B model

### 4.4 Auto-close safety

- `ENABLE_AUTO_CLOSE_LOW_RISK` defaults `false`
- When enabled: requires verdict `BENIGN_FALSE_POSITIVE`, confidence ≥ 95, low severity, `_matches_known_fp_pattern()` true
- Writes audit event; never auto-isolates

### 4.5 VM 115 (mssp-ai) reliability

- Documented SPOF — prior RAM starvation at 7.6 GB
- No health probe in admin UI for Ollama reachability
- No failover / secondary model host

---

## 5. Infrastructure feasibility matrix (VMs 100–115)

| VM | Role | Enterprise-ready for scale? | Notes |
|----|------|----------------------------|-------|
| 100 | Control plane | Partial | 7.7 GB RAM tight for OLAP; no retention automation |
| 101 | Wazuh | Partial | Shared Manager for cloud tenants |
| 102 | TheHive + Shuffle | Partial | Shared org/webhook risk |
| 106 | Suricata + Zeek | Partial | `source_tool` collapse breaks NDR |
| 108 | MISP bridge | OK for IOC feed | Not full MISP |
| 109 | Vuln + EASM scanners | OK | Off control plane |
| 110 | Velociraptor | OK (Linux) | Windows client manual |
| 112 | Ansible | OK | DR-included |
| 114 | Appliance mgmt | OK | SSH tunnel to VM 100 DB |
| 115 | Ollama (mssp-ai) | Partial | SPOF |
| 199 | Golden appliance | OK | kb110 bake at `2ec0eb0` |

---

## 6. Open-source backend engines (reference)

| NikTiar™ capability | Backend engines | VM |
|---------------------|-----------------|-----|
| Core Telemetry | Wazuh, Fluent Bit | 101, appliances |
| DeepSight NDR | Suricata, Zeek | 106 |
| Aegis Scanning | Nuclei, Vuls, Greenbone GVM | 109 |
| Apex Orchestrator | TheHive, Shuffle | 102 |
| Spectre Forensics | Velociraptor | 110 |
| Cloud & Identity (ITDR) | Microsoft Graph (Entra) | Control plane adapter |
| AI SOC Assist | Ollama (`qwen2.5:7b`) | 115, appliances |

Platform infrastructure: PostgreSQL 16, Redis 7, FastAPI, nginx, Docker Compose (VM 100).

---

## 7. Key technical challenges & risks (prioritized)

### P0 — Security / tenancy

1. **EDR `agent_id` IDOR** — validate agent belongs to caller's tenant before AR dispatch (`edr_actions.py`, `edr.py`).
2. **No Postgres RLS** — add policies on core tenant tables as defense-in-depth.

### P1 — Data fidelity & compliance

3. **NDR synthetic data** — fix `source_tool` hardcoding; gate sample seed behind non-production.
4. **No retention enforcement** — implement purge jobs; document Wazuh Indexer lifecycle.
5. **TheHive tag-only fallback** — detect and alert on shared-org mode.

### P1 — IAM / ITDR

6. **No MFA/SSO** — enterprise blocker.
7. **ITDR single-provider** — Okta, GWS, AWS, Windows logon events missing.

### P2 — Scale & analytics

8. **JSONB without GIN** — hunting at scale will table-scan.
9. **ClickHouse on VM 100** — not feasible at current RAM.
10. **No table partitioning** — archival needed before high volume.

### P2 — AI safety & ops

11. **No pre-LLM deterministic gate** — add hash/rule short-circuit.
12. **VM 115 SPOF** — health probe + failover plan.
13. **`alert_ai_triage_cache`** — add `tenant_id` to cache read WHERE.

### P3 — Engine isolation

14. **Shuffle single webhook** — per-tenant workflows.
15. **Wazuh cloud-mode AR** — enforce group membership at execution.

---

## 8. What is solid today (strengths)

- Consistent `tenant_id` FK discipline across core tables
- `require_tenant_match()` + 404 anti-enumeration on customer routes
- Machine auth separated from user JWT
- Portal role separation enforced server- and client-side
- AI never auto-isolates; auto-close opt-in with hard gates
- Scanners kept off VM 100
- Golden appliance (VM 199) at `kb110-gitreleasesync-202608280309` / `2ec0eb0`
- Entra ID ITDR is real Graph ingestion in production mode

---

## 9. Recommended remediation sequencing

| Phase | Focus | Effort |
|-------|-------|--------|
| 0 | Fix EDR `agent_id` tenant validation | Small, critical |
| 1 | Fix `source_tool` ingest + disable NDR sample seed in prod | Medium |
| 2 | Postgres retention jobs + RLS policies | Medium |
| 3 | MFA/SSO + login rate limiting | Large |
| 4 | Pre-LLM deterministic FP gate + VM 115 health probe | Medium |
| 5 | Dedicated OLAP VM or VM 100 RAM upgrade | Large |
| 6 | Okta/GWS/Windows identity ingest adapters | Large |

---

## 10. Key file references

| Area | Path |
|------|------|
| Core schema | `postgres/init/001_mssp_core_schema.sql` |
| AI triage cache | `postgres/init/038_alert_ai_triage_cache.sql` |
| Telemetry columns | `postgres/init/040_wazuh_telemetry_columns.sql` |
| Tenant match guard | `backend-api/app/api/dependencies.py` |
| EDR actions | `backend-api/app/services/edr_actions.py` |
| SOC sync / ingest | `backend-api/app/api/routes/soc_sync.py` |
| NDR service | `backend-api/app/services/ndr_service.py` |
| Tier-1 AI triage | `backend-api/app/services/ai_tier1_triage.py` |
| ITDR Graph client | `backend-api/app/services/itdr_graph_client.py` |
| Tenant engine mapping | `backend-api/app/services/tenant_engine_provisioner.py` |
| TheHive client | `backend-api/app/services/thehive_client.py` |
| Shuffle EDR client | `backend-api/app/services/shuffle_edr_client.py` |
| Appliance datalake | `kevantic-appliance/appliance/datalake/archiver.py` |
| Attributions | `ATTRIBUTIONS.md` |
| VM inventory | `docs/MSSP_IP_PROXMOX_INVENTORY.md` |

---

*End of report — ERGA-2026-08-28*
