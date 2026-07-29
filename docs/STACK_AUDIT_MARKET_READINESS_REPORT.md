# STACK_AUDIT_MARKET_READINESS_REPORT.md

**Title:** MSSP / Open XDR Control Plane — Architecture, Security & Production-Readiness Stack Audit  
**Scope:** `/opt/mssp-control` (FastAPI backend, Admin `:3000`, Customer `:3001`, adapters, EDR KB-083/084, audit KB-085)  
**Method:** Static review of routes, services, SQL patterns, deploy scripts, and frontends (no new runtime changes)  
**Date:** 2026-07-29  
**Baseline reference:** KB-035 validated UI; KB-083/084 EDR lifecycle; KB-085 audit enrichment  

---

## Executive summary

The platform has a **solid multi-tenant foundation** on customer APIs (`require_tenant_match` + `tenant_id` in queries), **deliberate customer-safe labeling**, and a **coherent EDR action model** wired to Wazuh Active Response and Shuffle. It is **not yet market-ready for HA cloud** without addressing **Windows/Linux execution parity**, **real object storage for forensics**, **connection pooling and async action dispatch**, **audit completeness**, and **removal of lab-only defaults** (hardcoded IPs, TLS-off Wazuh client, in-process threading).

---

## 1. Critical vulnerabilities & bugs (must fix before cloud launch)

### 1.1 Multi-tenant isolation & RBAC

| Finding | Severity | Evidence |
|--------|----------|----------|
| **Customer API tenant isolation is consistently enforced** on `/customer/*` routes via `require_tenant_match` and `WHERE tenant_id = %s` | Strength (reduces risk) | `backend-api/app/api/routes/customer.py` |
| **Customer cross-tenant ID guessing returns 404** (not 403) for wrong `short_code` | Strength | `app/api/dependencies.py` `require_tenant_match` |
| **EDR read/write paths scope by tenant** (`edr_action_status`, process tree, deep-dive SQL) | Strength | `app/api/routes/edr.py` |
| **Customer `customer_admin` can execute destructive EDR actions** (`ISOLATE_HOST`, `KILL_PROCESS`, etc.) when entitled — confirm this matches contractual SOC model; there is no secondary approval or SOC co-sign | **High (policy)** | `edr_actions.py` `CUSTOMER_ACTION_ROLES`, `ALLOWED_CUSTOMER_ACTIONS` |
| **`soc_analyst` cannot execute EDR writes** (only `platform_admin`, `soc_manager`, `customer_admin`) but **can read** EDR deep-dive/metrics if UI exposes `/api/v1/edr` | Medium | `assert_can_execute_action` vs open `get_current_user` on GET EDR |
| **Public Linux agent install URLs** (`/v1/agent-install/{code}/{token}/linux.sh`) are **unauthenticated** by design; token leakage = anyone can pull tenant installer script | **High** if tokens emailed/logged | `public_agent_install.py`, `agent_install_repo.py` |
| **Forensic upload/download use HMAC tokens only (no session)** — token bound to `artifact_id` + `tenant_id` + expiry; **Bearer not required** | Medium (token leakage = data access) | `edr.py` upload/download; `edr_forensics_storage.py` |
| **EDR callback + forensics complete** authenticate via **single shared API key** (`SOC_SYNC_API_KEY` / `EDR_CALLBACK_API_KEY`); compromise allows **forging success/failure for any `execution_id`** | **High** | `edr.py` `_require_callback_auth` |
| **Admin user lifecycle (create/update/password) lacks audit events** in `user_management.py` | Medium (compliance) | No `audit_from_user` in KB-014 user routes |
| **Most privileged actions omit `source_ip`** in audit (only login captures IP from `Request`) | Medium | `auth.py` vs `audit_from_user` elsewhere |

**Spoofing test (design review):** A `customer_admin` sending another tenant’s `tenant_short_code` on EDR execute gets **`PermissionError` → 403** (`assert_can_execute_action`). A customer fetching another tenant’s `execution_id` gets **404** (tenant filter on `edr_action_executions`). **Audit logs** for customers are filtered `WHERE al.tenant_id = %s` — cross-tenant read **blocked**.

### 1.2 EDR action loop & engine execution

| Finding | Severity | Evidence |
|--------|----------|----------|
| **State machine is partial:** `pending` → `executing` → `success`/`failed`/`verified`; callbacks map `timeout` → `failed`; **no background sweeper** for rows stuck in `executing` | **High** | `edr_actions.py`; no cron/worker |
| **Wazuh Active Response invoked synchronously inside HTTP request** (`run_active_response` + `authenticate()` per call, 20s timeout) — **blocks worker** under load or slow manager | **High** | `edr_actions.py`, `wazuh_client.py` |
| **Windows vs Linux AR scripts are not symmetric** | **Critical for mixed estates** | See below |
| **Shuffle webhook failures** for forensics can leave execution `failed` but artifact `awaiting_upload` — manual cleanup | Medium | `execute_edr_action` COLLECT_FORENSICS |
| **Isolate “verification”** only checks agent **manager status active**, not true network isolation | Medium | `verify_isolation_state` |

**Active Response script parity (`deploy/wazuh-active-response/`):**

| Action | Linux-oriented implementation | Windows gap |
|--------|------------------------------|-------------|
| `mssp-isolate-host` | **iptables** OUTPUT chain | **No Windows firewall / WFP script** — Windows agents will not isolate correctly |
| `mssp-kill-process` | **`os.kill` / SIGKILL** (POSIX) | **Not valid on Windows agents** |
| `mssp-block-hash` | Appends to **local text file** on agent | No AppLocker/WDAC/SRP integration; file-only |

**Un-isolate:** Uses same `mssp-isolate-host` with `arguments=["delete"]` — **Linux only**.

### 1.3 Forensic storage

| Finding | Severity | Evidence |
|--------|----------|----------|
| **`storage_backend()` can return `s3` but `write_upload` / `read_download` only implement local disk** | **Critical (HA)** | `edr_forensics_storage.py` |
| **Upload handler reads entire body into memory** (`await request.body()`), up to `EDR_FORENSICS_MAX_BYTES` (default 512MB) — **OOM risk** per request | **High** | `edr.py` `edr_forensics_upload` |
| **Object keys are tenant-scoped** `{tenant_id}/{endpoint_id}/{ts}_{artifact_id}.zip` with path traversal checks | Strength | `object_key_for`, `local_path_for_key` |
| **Presigned URLs are HMAC-based API URLs**, not AWS S3 presigned PUT/GET — naming in product docs may oversell “direct-to-S3” | Medium | `build_upload_url` |
| **Signing secret defaults to JWT secret** — key rotation couples auth + forensics | Medium | `_signing_secret()` |
| **Deep-dive returns download URLs to authenticated users** without re-checking role beyond tenant; URLs are time-limited HMAC | Low–Medium | `edr_incident_deep_dive` |

### 1.4 Ingestion & reliability

| Finding | Severity | Evidence |
|--------|----------|----------|
| **Wazuh instant ingress** runs DB work synchronously then **`threading.Thread` to Shuffle** — **not durable**; lost on process crash; **not HA-safe** (duplicate forwards if multiple API instances) | **High** | `soc_sync.py` `wazuh_instant_ingress` |
| **Fail-closed tenant mapping** on Wazuh ingress when group cannot resolve | Strength | `soc_sync.py` / provisioner |
| **Appliance ingest** uses transaction + **advisory lock** for dedupe | Strength | `appliance_alert_ingest.py` |
| **No global EPS rate limit** on `/integrations/soc/*` or Wazuh hook | **High at scale** | No middleware/rate limiter found |

### 1.5 Cryptography & transport

| Finding | Severity | Evidence |
|--------|----------|----------|
| **Wazuh API TLS verification off by default** (`WAZUH_API_VERIFY_TLS=false`) | **High in cloud** | `wazuh_client.py` `_ssl_context` |

---

## 2. Operational bottlenecks & scale limits (EPS & database pool)

### 2.1 Database access model

- **No SQLAlchemy connection pool** — each `fetch_*` opens a **new psycopg connection** and closes it (`app/db/session.py` `db_conn()`).
- Under concurrent dashboards + ingest + EDR, expect **Postgres connection churn**, latency spikes, and risk of **max_connections** exhaustion before CPU.
- **Recommendation class:** PgBouncer or pooled engine; bound FastAPI workers × connections.

### 2.2 Telemetry & process trees

- **Every qualifying Wazuh alert** can insert into `edr_process_events` and update `security_alerts.raw_event` (**large JSONB**) — **storage growth** unbounded without retention job.
- **Process tree API** loads **all** `raw_event` blobs for an incident (`load_incident_raw_events`) plus normalized rows — **memory scales with incident size**, not paginated.
- **Tree build** indexes by `ProcessGuid` then **PID fallback** without timestamp window enforcement on PID collision (comment mentions window; code assigns parent if PID matches) — **wrong-tree risk** on busy hosts.
- **Missing ProcessGuid:** fallback to `parent_pid` / `pid` only — acceptable for v1, degrades on PID reuse.
- **Indexes present:** `idx_edr_process_events_tenant_alert`, `(tenant_id, process_guid)` — good for point lookups; large incident scans still heavy.

### 2.3 Redis

- Redis used for **`/health` ping only** — **not** a job queue, rate limiter, or distributed lock for ingest/EDR.
- **Horizontal scale** of `backend-api` replicas will **not** coordinate through Redis today.

### 2.4 Event loop / workers

- Synchronous `urllib` Wazuh calls inside `async`-capable app (EDR routes are **sync def**) — blocks Uvicorn worker for full Wazuh round-trip.
- Forensic **async** upload still buffers full body in RAM.

### 2.5 Network / syslog appliances

- Taxonomy classifies `network_appliance` / syslog-style sources at read time (`soc_alert_taxonomy.py`); appliance ingest path stores **normalized safe fields** without requiring agent ID (`appliance_alert_ingest.py`).
- **Gap:** Syslog-heavy bursts still hit same DB insert path — **no batching**.

---

## 3. Enterprise market gaps (vendor security assessment)

| Area | Current state | Typical assessor expectation |
|------|---------------|------------------------------|
| **Audit completeness** | Login/logout/password, EDR actions, entitlements changes, some tenant ops | **All** admin mutations, role changes, isolation/kill, policy/entitlement, exports, failed auth — **with IP + user agent** |
| **MFA / SSO** | Email/password JWT only | IdP (SAML/OIDC), MFA enforcement |
| **Secrets management** | File/env secrets on VM 100 | Cloud SM (AWS SM, Vault), rotation runbooks |
| **Rate limiting & abuse** | Minimal | Per-tenant/per-IP limits on auth, ingest, public install |
| **Data retention & purging** | Not centralized in code | Alert/raw_event/forensics retention policies |
| **Encryption at rest** | Postgres volume + local forensics dir | KMS-backed storage, S3 SSE, DB TDE documentation |
| **Windows EDR parity** | Linux AR scripts only | First-class Windows isolate/kill/hash |
| **Real S3 forensics** | Local disk default | Presigned PUT/GET to `s3://…/{tenant_id}/…` with IAM boundary |
| **HA / DR** | Single Compose stack | Multi-AZ API, RDS, ElastiCache, stateless API pods |
| **Observability** | App logging | Metrics (EPS, action latency), tracing, alert on stuck `executing` |
| **Pen test / SBOM** | Not evidenced in repo | Deliverables for enterprise sales |
| **Customer data rights** | No export/erase automation | GDPR-style tooling |
| **SOC2 / ISO mapping** | Partial via audit_logs | Control matrix + gap remediation |

### 3.1 White-label & customer API integrity

| Check | Result |
|-------|--------|
| **`customer_safe_labels.py`** maps engine ids to generic labels | **Pass** |
| **Customer alert APIs** remap `source_tool` → safe `source`; omit `raw_event`, IPs, MITRE internals per route comments | **Pass** (review each new field) |
| **`CustomerEntitlementsPublic`** uses `entitlements_row_to_customer_public` — no `wazuh_*` field names in customer JSON | **Pass** |
| **Customer frontend** (`frontend-customer/src`) — **no matches** for Wazuh/Suricata/Zeek/Shuffle/Greenbone/Velociraptor/TheHive in TS sources scanned | **Pass** |
| **Admin taxonomy labels** include phrasing like “EDR Controllers” — **admin-only** surface | OK if not exposed on `:3001` |
| **EDR deep-dive** exposes `agent_id`, hostname, `sysmon_detail` string to customer roles (viewer strips `local_ip` only) | **Review** for customer contract |
| **Shuffle payload** references `velociraptor_server` internally — not returned on customer portal list APIs | Low |

### 3.2 Customer vs MSSP user separation

| Check | Result |
|-------|--------|
| **Customer user CRUD** under `/customer/.../users` with tenant match | **Pass** (`customer_users.py`) |
| **Platform users** under `/admin/users` — customer roles **403** | **Pass** (`user_management.py`) |
| **Customer cannot call `/admin`** (architecture rule; enforced by nginx + route prefixes) | **Pass** (verify nginx in deploy) |

---

## 4. Current architectural strengths (where the platform shines)

1. **Fail-closed customer tenancy** — wrong tenant → **404** on customer routes; parameterized SQL throughout inspected modules.
2. **Clear adapter boundary** — engines normalize into `security_alerts`, `incidents`, entitlements; customer UI uses capability language.
3. **EDR domain model** — executions, isolation registry, forensic artifacts, process events, telemetry counters — **schema-ready** (`014`/`015` migrations).
4. **Defense in depth on forensics paths** — HMAC tokens with expiry, purpose separation (`upload` vs `download`), object-key traversal guard.
5. **Ingest deduplication** — advisory locks for appliance and SOC sync paths reduce duplicate incident noise.
6. **Tenant engine provisioning** — Wazuh groups / TheHive org wiring with audit hooks on provision (`tenant_engine_provisioner.py`).
7. **RBAC layering** — `require_roles` for admin writes; `get_current_user` + tenant match for customer reads.
8. **Production-oriented frontends** — nginx static builds, Docker Compose separation of API/DB/Redis/UI.
9. **Documented AR scripts** — repeatable deploy via `scripts/kb083_deploy_wazuh_edr_ar.sh` for Linux lab path.
10. **Audit schema enrichment** — `actor_email`, `actor_role`, `action_status`, `resource_*` columns (KB-085) ready for SIEM export.

---

## Pillar-by-pillar scorecard (qualitative)

| Pillar | Readiness (lab → cloud) | Notes |
|--------|-------------------------|-------|
| **1. Multi-tenant & RBAC** | **B** | Customer paths strong; audit gaps; public install + callback keys |
| **2. EDR action loop** | **C** | Sync Wazuh, no timeout worker, Windows gap |
| **3. Telemetry & process trees** | **C+** | Works for moderate volume; memory/DB growth risks |
| **4. Forensic storage** | **D+** | Local-only; in-memory upload; S3 flag unused |
| **5. White-label** | **A-** | Customer API/UI discipline good; watch new endpoints |
| **6. HA / cloud migration** | **D** | Stateful disk, hardcoded IPs, no pool, thread fan-out |

---

## Recommended remediation sequence (no code in this audit)

1. **P0:** Windows AR scripts or disable Windows actions in UI until parity; async EDR dispatch queue; stuck-action reconciler.  
2. **P0:** Implement real S3 (or compatible) forensics + streaming upload; remove full-body buffer.  
3. **P0:** Postgres pooling + connection limits; load test ingest EPS target.  
4. **P1:** Expand audit to all admin/customer mutations; attach `source_ip` + `User-Agent` via middleware.  
5. **P1:** Replace `threading.Thread` Shuffle forward with Redis/RQ (or SQS) worker; idempotency keys.  
6. **P1:** Rate limits on auth, ingress, public agent install; rotate install tokens; shorten TTL.  
7. **P2:** Enable Wazuh TLS verify in production; separate forensics signing key from JWT.  
8. **P2:** Retention jobs for `raw_event`, `edr_process_events`, forensic objects.  
9. **P2:** Environment-driven URLs — remove `192.168.0.201/211` defaults from runtime fallbacks.

---

## Files inspected (representative)

- `backend-api/app/api/routes/customer.py`, `edr.py`, `auth.py`, `audit_logs.py`, `customer_users.py`, `user_management.py`, `entitlements.py`, `soc_sync.py`, `appliance_alert_ingest.py`
- `backend-api/app/api/dependencies.py`
- `backend-api/app/services/edr_actions.py`, `edr_forensics_storage.py`, `edr_process_tree.py`, `edr_ingress.py`, `edr_metrics.py`, `wazuh_client.py`, `audit_service.py`, `customer_safe_labels.py`, `soc_alert_taxonomy.py`
- `backend-api/app/db/session.py`
- `deploy/wazuh-active-response/*`
- `postgres/init/014_kb083_edr_actions.sql`, `015_kb084_edr_lifecycle_forensics.sql`
- `frontend-customer/src` (engine name grep)

---

## Intentionally unchanged by this audit

No application code, configuration, or infrastructure was modified. This document is diagnostic only.

**Next step when you approve:** Prioritize a **P0 implementation KB** (e.g. HA hardening + Windows EDR parity + S3 forensics) with validation scripts per existing KB workflow.
