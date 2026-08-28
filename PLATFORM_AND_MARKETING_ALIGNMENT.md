# Platform & Marketing Alignment Audit

**Product:** Kevantic NikTiar™ MSSP Control Plane  
**Repository:** `/opt/mssp-control`  
**Audit date:** 2026-08-28  
**Live API:** `https://api.kevantic.com`  
**Marketing site:** [https://www.kevantic.com/](https://www.kevantic.com/)  
**Latest commit baseline:** Phase 7 — `subscription_tier` enforcement across API, DB, and customer portal

> **2026-08-28 update:** Backend tier middleware is active. `SILVER`/`GOLD`/`PLATINUM` on `tenants` drives entitlement bundles and returns `403` on under-tier API access. Customer portal shows tier in header and upgrade badges on locked modules.

---

## 1. Executive Summary

Kevantic operates a **production multi-tenant MSSP control plane** on VM 100 comprising five Docker services (`mssp-postgres`, `mssp-redis`, `mssp-backend-api`, `mssp-frontend-admin`, `mssp-frontend-customer`), a FastAPI backend with 40+ route modules, PostgreSQL 16 with 45 schema migrations, and integrations to Wazuh, Suricata, Zeek, TheHive, Shuffle, Greenbone/Nuclei, MISP, Velociraptor, Azure Graph, and a local Ollama LLM tier on VM 115.

### Seven development phases (KB-111 + EDR foundation)

| Phase | Theme | Key deliverables | Evidence |
|------:|-------|------------------|----------|
| **0** | Endpoint / EDR | Wazuh agent telemetry, FIM, active response (isolate/kill/block-hash), 3-tier agent→tenant ownership, forensics upload | `app/api/routes/edr.py`, `app/services/edr_actions.py`, `tests/test_edr_agent_tenant.py` |
| **1** | Network NDR | Suricata & Zeek `source_tool` tagging on SOC ingress, NDR customer/admin APIs, production seed gating | `app/api/routes/soc_sync.py` (`detect_ingress_source_tool`), `app/services/ndr_service.py`, `tests/test_ndr_ingest.py` |
| **2** | Tenant isolation & retention | PostgreSQL RLS (`mssp_app` role), batched 90-day retention purge, IDOR-safe 404 on cross-tenant access | `postgres/init/042_enable_rls.sql`, `041_retention_purge.sql`, `app/db/session.py`, `tests/test_db_rls.py` |
| **3** | MFA & identity controls | TOTP (`valid_window=1`), 8 hashed single-use recovery codes, mandatory first-login MFA wizard, Redis login rate-limit (5/15 min), admin MFA reset/enforce | `043_user_mfa.sql`, `044_mfa_recovery_codes.sql`, `mfa_service.py`, `login_rate_limit.py`, `tests/test_auth_mfa.py` |
| **4** | AI SOC assist | Local Ollama `qwen2.5:7b`, pre-LLM whitelist veto gate, 3s health probe + rule-based fallback | `ai_tier1_triage.py`, `tests/test_ai_triage.py` |
| **5** | Data scaling & archival | `tenant_daily_alert_counts` matview, ClickHouse OLAP adapter, async gzip JSONL archiver | `045_analytics_views.sql`, `analytics_service.py`, `log_archiver.py`, `tests/test_analytics.py` |
| **6** | Identity telemetry | Okta System Log + AD Windows Event ingest, MFA fatigue / impossible travel / Kerberoasting detection | `app/api/v1/identity_ingest.py`, `identity_threat_engine.py`, `tests/test_identity_telemetry.py` |

### Deployed services snapshot

| Layer | Components | Status |
|-------|------------|--------|
| **Control plane API** | FastAPI on `:8000` → `api.kevantic.com` via Cloudflare | Live |
| **Admin portal** | React/Vite SOC console (`:3000`) — tenants, users, MFA admin, alerts, incidents, EDR, AI assistant | Live |
| **Customer portal** | React/Vite tenant portal (`:3001`) — MFA wizard, dashboards, entitlements, ITDR/NDR/EASM modules | Live |
| **Data plane** | PostgreSQL 16 + Redis 7 (loopback-bound) | Live |
| **Detection engines** | Wazuh (VM 101), Suricata/Zeek via ingress, TheHive/Shuffle (VM 102), vuln scanners (VM 109) | Live |
| **AI tier** | Ollama on VM 115 (`AI_ALERT_BASE_URL`, model `qwen2.5:7b`) | Live (with health failover) |

**Maturity verdict:** The codebase delivers **Level 3–4 co-managed MDR / emerging MXDR** — multi-tenant SOC operations, endpoint containment, network NDR tagging, cloud/on-prem identity telemetry, AI-assisted triage, and analytics scaling. Marketing on kevantic.com is **largely aligned** on managed-service positioning and hybrid edge architecture, but **under-represents** several newly shipped technical differentiators (Okta/AD connectors, Kerberoasting/MFA-fatigue detections, pre-LLM veto gate, ClickHouse OLAP path, PostgreSQL RLS depth).

---

## 2. Phase-by-Phase Technical Inventory

### Phase 0 — Endpoint / Host (Wazuh EDR)

| Capability | Implementation |
|------------|----------------|
| Agent log & FIM ingest | Wazuh Manager → `POST /integrations/soc/hooks/wazuh/{token}` → `security_alerts` |
| Normalized appliance alerts | `POST /appliance/alerts`, `POST /api/v1/telemetry/ingest` |
| EDR actions | `POST /v1/edr/actions/execute` — isolate, unisolate, kill, block-hash |
| Verified callback | `POST /v1/edr/actions/callback` (public: `api.kevantic.com/v1/edr/actions/callback`) |
| Live telemetry | `GET /v1/edr/telemetry/processes/live`, `GET /v1/edr/telemetry/process-tree` |
| Forensics | `PUT/GET /v1/edr/forensics/upload|download/{artifact_id}` |
| **3-tier agent authorization** | `validate_agent_tenant_ownership()` — (1) `protected_assets`, (2) `security_alerts` history, (3) Wazuh agent group vs `tenant_engine_bindings` |

### Phase 1 — Network NDR (Suricata & Zeek)

| Capability | Implementation |
|------------|----------------|
| Source tagging | `detect_ingress_source_tool()` in `soc_sync.py` — `suricata`, `zeek`, or `wazuh` fallback |
| NDR product APIs | `/customer/ndr/{short_code}/...`, `/admin/ndr/{tenant_ref}/sync` |
| Hunt callbacks | `POST /api/v1/telemetry/hunt-results` (NikTiar™ Edge contract) |
| Production gating | Lab-only synthetic NDR seeds blocked when `APP_ENV=production` |

### Phase 2 — Tenant Isolation & Security

| Capability | Implementation |
|------------|----------------|
| PostgreSQL RLS | `mssp_app` role (`NOBYPASSRLS`); policies on `security_alerts`, `incidents`, `vulnerabilities` |
| Session GUCs | `app.current_tenant` / `app.current_role` per transaction via `set_db_session_context()` |
| IDOR protection | `require_tenant_match()` returns **404** (not 403) for cross-tenant customer access |
| Retention | `purge_expired_tenant_data(retention_days=90)` batched deletes |
| Appliance auth | `X-Appliance-ID` + `X-Appliance-API-Key` — SHA-256 hashed keys, `hmac.compare_digest` |
| Password safety | Global 422 sanitizer redacts passwords/tokens from validation errors (`error_handlers.py`) |

### Phase 3 — Multi-Factor Authentication & Identity Controls

| Capability | Implementation |
|------------|----------------|
| TOTP engine | Custom SHA1/HMAC, 6-digit, 30s period, **`valid_window=1`** (±30s drift) |
| Recovery codes | **8** single-use codes, SHA-256 hashed in `platform_users.mfa_recovery_codes` |
| Mandatory MFA | `tenants.enforce_mfa` (default TRUE); first-login `/mfa-setup` wizard (customer portal) |
| Login rate-limit | Redis: **5 failed attempts / 15-minute** block per IP + email |
| Admin GUI | `MfaManageModal.tsx` — 1-click reset (`POST /admin/users/{id}/mfa/reset`) and enforce (`/mfa/enforce`) |
| Auth endpoints | `/auth/login`, `/auth/mfa/authenticate`, `/auth/mfa/complete-setup`, recovery-code path |

### Phase 4 — AI SOC Assist Pipeline

| Capability | Implementation |
|------------|----------------|
| Local LLM | Ollama on VM 115 — default model **`qwen2.5:7b`** (`AI_ALERT_MODEL`) |
| Tier-1 triage | `run_tier1_triage()` — DB-grounded enrichment, attack-chain correlation, queue routing |
| **Pre-LLM veto gate** | `check_pre_llm_whitelist_veto()` — trusted SHA256 hashes, prior FP history, suppression patterns → skips Ollama at 100% confidence |
| Health probe | `probe_ollama_health()` — **3-second** `GET /api/tags` timeout |
| Failover | Unhealthy Ollama → `build_rule_based_triage_result()` (no 502/504 to SOC) |
| Customer summaries | `ai_alert_analysis.py` — plain-English fields, COALESCE-only (never overwrites SOC text) |
| Admin AI chat | `/admin/ai/chat` (KB-096, env-gated) |

### Phase 5 — Data Scaling & Archival

| Capability | Implementation |
|------------|----------------|
| Matview | `tenant_daily_alert_counts` — daily counts by tenant/source/severity |
| Refresh | `refresh_tenant_analytics_views()` — concurrent refresh when populated |
| Indexes | `(tenant_id, created_at DESC)`, `(tenant_id, source_tool, severity)` |
| ClickHouse OLAP | `ClickHouseAnalyticsAdapter` — HTTP JSONEachRow; falls back to PostgreSQL when unhealthy/unconfigured |
| Log archiver | `log_archiver.py` — async worker exports aged alerts to **`.jsonl.gz`** under `LOG_ARCHIVE_DIR` |

### Phase 6 — Cloud & On-Prem Identity Telemetry

| Capability | Implementation |
|------------|----------------|
| Okta ingest | `POST /api/v1/telemetry/okta` — System Log events (MFA, session start, etc.) |
| AD ingest | `POST /api/v1/telemetry/ad` — Event IDs **4624, 4625, 4768, 4769** |
| Auth | `Authorization: Bearer` or `X-Agent-API-Key` + `X-Tenant-ID`; or appliance API-key pair |
| **MFA fatigue** | `detect_mfa_fatigue()` — >3 MFA failures in 5 min then success → `severity=high` |
| **Impossible travel** | `detect_impossible_travel()` — distinct subnets/locations <30 min apart → `critical` |
| **Kerberoasting** | `detect_kerberoasting()` — Event 4769 + RC4 `0x17` on non-machine SPN → `critical` |
| Alert emission | `security_alerts` with `source_tool` `okta` or `active_directory` |

---

## 3. API & Ingestion Endpoint Map (`api.kevantic.com`)

Public hostname routes to the `mssp-backend-api` container. Grouped by traffic type.

### 3.1 Public / unauthenticated

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/` | Service metadata |
| `GET` | `/health` | API + Postgres + Redis health |
| `GET` | `/docs` | OpenAPI (dev/lab) |
| `POST` | `/auth/login` | Password login (+ MFA challenge routing) |
| `POST` | `/auth/mfa/*` | MFA setup, authenticate, complete-setup |
| `GET` | `/auth/roles` | Role catalog |
| `GET` | `/v1/agent-install/{short_code}/{token}/linux.sh` | Public Linux agent one-liner |
| `POST` | `/v1/edr/actions/callback` | Endpoint AR callback (isolate/kill verify) |
| `POST` | `/integrations/soc/hooks/wazuh/{token}` | Instant Wazuh dual-path ingress |

### 3.2 Agent / appliance / integration ingest (machine auth)

| Method | Path | Auth | Payload |
|--------|------|------|---------|
| `POST` | `/appliance/register` | Activation token | Appliance onboarding |
| `POST` | `/appliance/heartbeat` | `X-Appliance-ID` + `X-Appliance-API-Key` | Heartbeat |
| `POST` | `/appliance/alerts` | Appliance API key | Normalized safe alerts |
| `POST` | `/api/v1/telemetry/ingest` | Appliance API key | Kevantic Edge anonymized alerts |
| `POST` | `/api/v1/telemetry/hunt-results` | Appliance API key | Retrospective hunt hits |
| `POST` | `/api/v1/telemetry/okta` | Bearer / `X-Agent-API-Key` + `X-Tenant-ID` (or appliance key) | Okta System Log JSON |
| `POST` | `/api/v1/telemetry/ad` | Bearer / `X-Agent-API-Key` + `X-Tenant-ID` (or appliance key) | Windows Security events |
| `POST` | `/integrations/soc/sync` | `X-SOC-Sync-Key` | Shuffle/TheHive normalized sync |
| `POST` | `/integrations/vuln/sync` | `X-Vuln-Sync-Key` | Vulnerability scan results |
| `POST` | `/integrations/easm/sync` | `X-EASM-Sync-Key` | External attack surface findings |
| `PUT` | `/v1/edr/forensics/upload/{artifact_id}` | Appliance / integration token | Forensic artifact chunks |

### 3.3 SOC / admin (JWT — `platform_admin`, `soc_manager`, `soc_analyst`)

| Prefix | Key capabilities |
|--------|------------------|
| `/admin` | Dashboard, tenants, appliances, alerts, incidents, assets, reports, notifications |
| `/admin/users` | User CRUD, **`/mfa-status`**, **`/{id}/mfa/reset`**, **`/{id}/mfa/enforce`** |
| `/admin/alerts`, `/admin/incidents` | Triage, bulk ops, AI triage |
| `/admin/tenants` | Tenant CRUD, engine provision, delegated users |
| `/admin/ndr`, `/admin/vulnerabilities`, `/admin/compliance` | Engine sync & management |
| `/admin/ai/chat` | SOC Q&A assistant |
| `/v1/edr` | EDR execute, metrics, incident deep-dive |
| `/v1/suppressions` | Alert suppression rules |

### 3.4 Customer portal (JWT — `customer_admin`, `customer_viewer`)

| Prefix | Key capabilities |
|--------|------------------|
| `/customer/dashboard/{short_code}` | Tenant dashboard |
| `/customer/alerts/{short_code}` | Safe alert list + AI triage view |
| `/customer/incidents/{short_code}` | Incident timeline |
| `/customer/compliance/{short_code}` | CIS/SCA scorecards |
| `/customer/ndr/{short_code}` | Network detection events |
| `/customer/itdr/{short_code}` | Cloud identity threats (M365/Entra adapter) |
| `/customer/easm/{short_code}` | Attack surface |
| `/customer/forensics/{short_code}` | Endpoint forensics |
| `/customer/users/{short_code}` | Delegated user management |
| `/customer/entitlements/{short_code}` | Service tier / feature gates |

### 3.5 Telemetry source → ingest path diagram

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────────┐
│ Wazuh Agents    │────▶│ SOC Wazuh Hook   │────▶│ security_alerts     │
│ (Endpoint/FIM)  │     │ /hooks/wazuh/*   │     │ source_tool=wazuh   │
└─────────────────┘     └──────────────────┘     └─────────────────────┘
┌─────────────────┐     ┌──────────────────┐              │
│ Suricata / Zeek │────▶│ Same SOC ingress │──────────────┤
│ (NDR sensors)   │     │ (tagged suricata/│              │
└─────────────────┘     │  zeek)           │              ▼
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────────┐
│ NikTiar™ Edge   │────▶│ /telemetry/ingest│────▶│ security_alerts     │
│ Node            │     │ (appliance key)  │     │ + hunt-results      │
└─────────────────┘     └──────────────────┘     └─────────────────────┘
┌─────────────────┐     ┌──────────────────┐              │
│ Okta System Log │────▶│ /telemetry/okta  │──┐           │
└─────────────────┘     └──────────────────┘  │  identity_threat_engine
┌─────────────────┐     ┌──────────────────┐  │  (MFA fatigue, travel)
│ AD Domain Ctrl  │────▶│ /telemetry/ad    │──┘           ▼
│ (4624–4769)     │     └──────────────────┘     ┌─────────────────────┐
└─────────────────┘                            │ security_alerts     │
┌─────────────────┐     ┌──────────────────┐     │ okta / active_dir   │
│ M365 / Entra    │────▶│ ITDR Graph sync  │────▶│ tenant_cloud_       │
│ (Graph API)     │     │ /admin/itdr/sync │     │ identity_events     │
└─────────────────┘     └──────────────────┘     └─────────────────────┘
```

---

## 4. Matrix: What We Built in Code vs. What We Say on Kevantic.com

| Capability | In code (2026-08-28) | On kevantic.com | Alignment |
|------------|----------------------|----------------|-----------|
| **24/7 Managed Detection & Response** | Full SOC workflow: alerts → incidents → TheHive/Shuffle; customer portal visibility | "24/7 Cloud SOC hunts, contains, and publishes live scorecards" | ✅ Aligned (operational claim) |
| **MDR across Host** | Wazuh EDR, isolate/kill AR, process tree, forensics | "NikTiar™ Core Telemetry", "Endpoint Telemetry", "Spectre DFIR" | ✅ Aligned |
| **MDR across Network** | Suricata + Zeek ingress tagging, NDR module, DeepSight branding | "NikTiar™ DeepSight NDR" (Gold+) | ✅ Aligned (product naming > engine names) |
| **MDR across Cloud Identity** | ITDR (M365/Entra Graph), **new Okta ingest**, **AD Windows events** | ITDR add-on: "M365 impossible travel & rogue mail rule tracking" only | ⚠️ **Partial** — Okta/AD/on-prem AD not mentioned |
| **AI Tier-1 triage** | Ollama `qwen2.5:7b`, enrichment, queue routing, customer plain-English summaries | "AI links related signals", "drafts business impact… reviewed by analysts" | ✅ Aligned |
| **Deterministic FP filtering** | `check_pre_llm_whitelist_veto()` — hash/FP/suppression veto before LLM | "Machine-speed correlation" (generic) | ⚠️ **Under-marketed** — veto gate not named |
| **Ollama health failover** | 3s probe + rule-based fallback | Not mentioned | ⚠️ **Under-marketed** |
| **Enterprise multi-tenant isolation** | PostgreSQL RLS + app-layer 404 IDOR + short_code routing | "tenant-isolated", "leadership-ready portal" | ✅ Aligned (mechanism not detailed) |
| **Compliance readiness** | CIS/SCA compliance module, continuous framework indicators on site | CIS · ISO 27001 · PCI-DSS · HIPAA · NIST on all tiers | ✅ Aligned |
| **Zero plain-text password exposure** | 422 validation sanitizer redacts passwords/tokens globally | Not explicitly stated | ⚠️ **Gap** — add security architecture bullet |
| **100% data sovereignty / edge** | NikTiar™ Edge Node, local ingest, encrypted alert egress | Flagship messaging throughout | ✅ Aligned |
| **MFA fatigue detection** | `detect_mfa_fatigue()` → `security_alerts` | Not mentioned | ❌ **Missing from marketing** |
| **Kerberoasting detection** | Event 4769 + RC4 `0x17` on non-machine SPNs | Not mentioned | ❌ **Missing from marketing** |
| **Impossible travel (Okta + AD)** | Dual-source `detect_impossible_travel()` | M365 impossible travel only (ITDR add-on) | ⚠️ **Partial** — broaden to Okta/AD |
| **ClickHouse OLAP scaling** | `ClickHouseAnalyticsAdapter` with PG fallback | Not mentioned | ⚠️ **Under-marketed** (enterprise scale story) |
| **Log archival (.jsonl.gz)** | `log_archiver.py` batched export before purge | "365+ days local retention" (edge) | ⚠️ **Partial** — control-plane archival not described |
| **Redis login rate-limiting** | 5 failures / 15 min per IP + email | Not mentioned | ⚠️ **Under-marketed** (portal security) |
| **Mandatory MFA + recovery codes** | Tenant `enforce_mfa`, 8 hashed recovery codes, admin reset | Not mentioned on homepage | ⚠️ **Gap** — enterprise access control story |
| **PostgreSQL RLS (`mssp_app`)** | Force RLS on core tenant tables | Not mentioned | ⚠️ **Under-marketed** (compliance/audit audiences) |
| **Service tiers (Bronze–Platinum)** | Entitlements + service catalog in control plane | Detailed pricing table on site | ✅ Aligned |
| **Hold-until-unisolate containment** | EDR isolate with verified callback | Explicit on site | ✅ Aligned |
| **Threat intel / retrospective hunts** | ThreatLens, hunt-results API, MISP integration path | "90-day retrospective zero-day sweeps" | ✅ Aligned |

### Summary score

| Category | Count |
|----------|------:|
| ✅ Fully aligned | 12 |
| ⚠️ Partial / under-marketed | 10 |
| ❌ Missing from marketing | 2 |

---

## 5. Marketing Copy Recommendations

Priority-ordered updates for [kevantic.com](https://www.kevantic.com/) to reach **100% sync** with the August 2026 platform build.

### 5.1 High priority — add net-new differentiators

**ITDR / Cloud & Identity Protection module** — replace or extend current copy:

> **Current:** "M365 impossible travel & rogue mail rule tracking."  
> **Recommended:** "Cloud and on-premises identity threat detection across **Microsoft Entra ID**, **Okta**, and **Active Directory** — including impossible-travel correlation, **MFA fatigue / push-bombing** detection, and **Kerberoasting** (RC4 TGS) alerts — with analyst-reviewed escalation to your portal."

**AI SOC section** — add deterministic layer:

> "Before any AI model runs, Kevantic applies a **deterministic false-positive veto gate** — trusted file hashes, prior analyst dismissals, and active suppression rules can resolve noise instantly at 100% confidence. When our local AI tier is unavailable, **rule-based triage failover** keeps the SOC queue moving — no analyst downtime."

**Security architecture** (new subsection under "Managed service model" or "Control plane"):

> "**Defense-in-depth tenant isolation:** PostgreSQL row-level security, per-tenant API scoping, and cross-tenant access controls that fail closed. Portal authentication supports **mandatory MFA**, **single-use recovery codes**, and **Redis-backed brute-force protection** (5 failed logins → 15-minute lockout). Passwords and secrets are never echoed in API error responses."

### 5.2 Medium priority — sharpen existing claims

| Page section | Recommendation |
|--------------|----------------|
| **Capability catalog → ITDR** | Add Okta + AD connector icons/bullets; link to "hybrid identity" deployment diagram |
| **Enterprise NDR (Gold)** | Note Suricata signature + Zeek protocol correlation (without exposing engine brands to customers — use "DeepSight" language) |
| **Data sovereignty** | Mention control-plane **compressed long-term archival** for compliance retention beyond hot PostgreSQL windows |
| **Platinum tier** | Reference **OLAP-ready analytics scaling** (ClickHouse-backed hunt queries with PostgreSQL fallback) for high-volume tenants |
| **Four subscription tiers table** | Add row: **Portal MFA enforcement** — Silver+ (or All tiers) with tenant policy |

### 5.3 Low priority — documentation / sales enablement

1. **Sales engineering one-pager:** API ingest map (Section 3 of this document) for prospects evaluating sovereign edge vs. direct SOC stream.
2. **Identity connector datasheet:** `POST /api/v1/telemetry/okta` and `/ad` payload examples, auth headers, and detection rule catalog.
3. **Update internal gap doc:** `docs/PLATFORM_GAP_ANALYSIS_AND_MATURITY_REPORT.md` (dated 2026-07-31) predates Phases 2–6 — refresh maturity rating from Level 3 → **Level 3.5–4** given RLS, MFA, AI veto, identity telemetry, and analytics scaling.
4. **Fix naming consistency:** Internal docs reference "Kestrel Cyber" in places; public brand is **Kevantic NikTiar™** — align internal reports on next doc pass.

### 5.4 Claims to keep (accurate today)

- "You are not buying an AI product to operate yourself" — AI proposes, analysts decide (`ai_tier1_triage` never auto-closes by default).
- "Only encrypted high-priority alerts leave the boundary" — matches appliance ingest + SOC sync design.
- "Hold-until-unisolate host containment with verified endpoint callback" — matches EDR AR implementation.
- "Continuous CIS · ISO 27001 · PCI-DSS · HIPAA · NIST indicators" — matches compliance module + customer scorecards.

### 5.5 Claims to avoid until further work

| Claim | Reason |
|-------|--------|
| "Full autonomous SOC" as unsupervised AI | Auto-close is opt-in (`ENABLE_AUTO_CLOSE_LOW_RISK`, default false) |
| "Full packet capture" on Silver | NDR packet depth is tier/entitlement-gated; verify per-tenant provisioning in sales |
| Zeek/MISP/Velociraptor as universally live | Entitlement flags exist; confirm VM wiring per deployment |

---

## 6. Test & Deploy Verification

| Check | Result |
|-------|--------|
| Unit tests | **73 passed** (`python -m unittest discover tests` in `mssp-backend-api`) |
| Phase 6 commit | `fcc60b9` on `origin/main` |
| Container | `mssp-backend-api` rebuilt and restarted on VM 100 (2026-08-28) |
| Golden VM 199 bake | Not required (control-plane-only changes) |

---

## 7. Appendix — Frontend Feature Map

| App | Path | Feature |
|-----|------|---------|
| `frontend-admin` | `/users` | MFA status, reset, enforce (`MfaManageModal.tsx`) |
| `frontend-admin` | `/alerts`, `/incidents` | SOC triage, AI assist panel, bulk actions |
| `frontend-admin` | `/ai-assistant` | Admin AI chat |
| `frontend-customer` | `/mfa-setup` | Mandatory 3-step MFA wizard + recovery codes |
| `frontend-customer` | `/itdr`, `/ndr`, `/easm` | Entitlement-gated security modules |
| `frontend-customer` | `/compliance` | Continuous framework indicators |
| `frontend-shared` | `KevanticLogin.tsx` | Shared branded login widget |

---

*This report is generated from repository inspection and the live kevantic.com homepage (v1.2.0). Re-run after major platform releases or website content updates.*
