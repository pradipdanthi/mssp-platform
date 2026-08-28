# Tier Deliverability & Reality Check

**Product:** Kevantic NikTiar™ MSSP Control Plane  
**Repository:** `/opt/mssp-control`  
**Audit date:** 2026-08-28  
**Marketing reference:** [kevantic.com](https://www.kevantic.com/) tier matrix (`website-niktiar/services.html`)  
**Code baseline:** `fcc60b9` + **Phase 7 tier enforcement** (migration `046_subscription_tier.sql`, `tier_enforcement.py`, `tests/test_tier_enforcement.py`)  
**Live environment:** VM 100 (`APP_ENV=development`, `mssp-backend-api` container)

> **2026-08-28 update:** `subscription_tier` (`SILVER`/`GOLD`/`PLATINUM`) is now enforced in backend middleware on tier-gated routes. Entitlement bundles sync from tier on tenant create/patch. Apply migration `046_subscription_tier.sql` before production use.

---

## 1. Executive Deliverability Scorecard

Scores reflect **this audit's tier definitions** (Silver = Cloud/Identity ITDR, Gold = Core MDR & containment, Platinum = Full MXDR & deep analytics), not the marketing site's Bronze→Platinum ladder alone. Each feature is weighted equally within its tier.

| Tier | Features audited | ✅ Fully deliverable | ⚠️ Partial / needs wiring | ❌ Mock / not deliverable | **Deliverability %** |
|------|-----------------:|---------------------:|--------------------------:|-------------------------:|---------------------:|
| **Silver** (Cloud & Identity / ITDR) | 12 | 9 | 2 | 1 | **75%** |
| **Gold** (Core MDR & Active Containment) | 11 | 6 | 4 | 1 | **55%** |
| **Platinum** (Full MXDR & Deep Analytics) | 14 | 5 | 5 | 4 | **36%** |
| **Platform-wide** (cross-tier foundations) | 37 | 22 | 9 | 6 | **59%** |

### Tier enforcement (Phase 7 — now in code)

| Item | Status |
|------|--------|
| `tenants.subscription_tier` enum column | ✅ Migration `046_subscription_tier.sql` |
| Tier → entitlement bundle sync | ✅ `subscription_tier_service.py` |
| Route middleware `require_subscription_tier` | ✅ `app/api/middleware/tier_enforcement.py` |
| Silver/Gold/Platinum route guards | ✅ Okta/AD, ITDR, EDR, vuln/EASM, NDR, DFIR, hunts |
| Customer portal tier badges | ✅ `tierConfig.ts`, `TierUpgradeBadge`, nav locks |
| Log archiver startup | ✅ `start_log_archiver_worker()` in `main.py` |
| Daily/continuous vuln cadence | ✅ `greenbone_cadence` extended |

---

### How to read the percentages

- **75% Silver** — Identity ingest APIs, threat detections, portal MFA, and ITDR UI are production-grade code with passing tests. Gaps are multi-tenant M365 Graph wiring.
- **55% Gold** — Core SOC ingest, AI veto/failover, and EASM are operational. Gaps are vuln pipeline data freshness and EDR callback hardening.
- **36% Platinum** — Individual modules (MISP, process-tree, hunt API) exist, but **live NDR signal, retrospective hunts, ClickHouse OLAP, and full-packet NDR** are not proven in this deployment.

### Critical cross-tier finding (updated)

**`subscription_tier` is now enforced in code** (Phase 7). `tenants.subscription_tier` drives entitlement bundles and API route guards. Operators must apply migration `046_subscription_tier.sql` and set each tenant's tier via admin tenant PATCH/create. Remaining gaps are **live sensor/VM wiring**, not missing tier abstractions.

---

## 2. Comprehensive Readiness Matrix

**Legend:**  
✅ **FULLY DELIVERABLE** — Tested code, working endpoints, DB/UI integrated, operable today with standard ops config.  
⚠️ **PARTIALLY DELIVERABLE** — Code exists; needs VM wiring, env secrets, manual entitlement toggles, or has known honesty/scale gaps.  
❌ **MOCK / NOT DELIVERABLE** — Stub, synthetic seed, dead code path, or capability not implemented.

---

### 2.1 Silver Tier — Cloud & Identity (ITDR)

| # | Feature (audit scope) | Status | Evidence | Blockers before paid sale |
|---|----------------------|--------|----------|---------------------------|
| S1 | `POST /api/v1/telemetry/okta` ingest | ✅ | `app/api/v1/identity_ingest.py`; 10 tests in `test_identity_telemetry.py` | Set `IDENTITY_TELEMETRY_API_KEY`; deploy Okta log forwarder per tenant |
| S2 | `POST /api/v1/telemetry/ad` ingest (4624/4625/4768/4769) | ✅ | Same module; AD event filter + `process_ad_event()` | Deploy AD event forwarder; appliance or agent key + `X-Tenant-ID` |
| S3 | Parse → `security_alerts` persistence | ✅ | `emit_identity_alert()` → `INSERT INTO security_alerts` with advisory-lock dedup | None (code complete) |
| S4 | MFA fatigue detection | ✅ | `detect_mfa_fatigue()` — >3 failures in 5 min then success | In-process event window not shared across API replicas (Redis/DB backlog recommended for HA) |
| S5 | Impossible travel detection | ✅ | `detect_impossible_travel()` — subnet/country/haversine within 30 min | Same in-process store caveat; needs sustained Okta/AD login volume |
| S6 | Kerberoasting (4769 + RC4 `0x17`) | ✅ | `detect_kerberoasting()` excludes machine accounts (`$`) | Requires DC forwarding 4769 events to `/telemetry/ad` |
| S7 | Customer ITDR portal visibility | ✅ | `frontend-customer/src/pages/ItdrPage.tsx`; `EntitlementGate require="cloud_identity_protection"` | Enable `cloud_identity_protection_enabled` per tenant |
| S8 | TOTP MFA setup wizard (`valid_window=1`) | ✅ | `MfaSetupPage.tsx` + `mfa_service.verify_mfa_code(window=1)` | None |
| S9 | 8 hashed single-use recovery codes | ✅ | `044_mfa_recovery_codes.sql`; `generate_recovery_codes()` / `consume_recovery_code()` | None |
| S10 | Redis login rate-limit (5 / 15 min) | ✅ | `login_rate_limit.py`; Redis live in compose | Fails open if Redis down (documented behavior) |
| S11 | M365 / Entra ITDR Graph sync | ⚠️ | `itdr_service.py` + `itdr_graph_client.py` (real OAuth2 client) | **No Azure creds configured** (`AZURE_TENANT_ID` blank); **single global app** — not per-customer admin consent; `_allow_lab_sample_seed()` false → returns empty (fail-closed, good integrity) |
| S12 | "Silver tier" auto-provisioning | ❌ | No `silver` enum in DB or API; `tenant_entitlement_defaults.py` is à la carte | Build tier→bundle mapper or runbook for manual entitlement assembly |

**Marketing alignment (kevantic.com Silver = "Advanced Sec"):** Site promises weekly Aegis scans, daily IOC sync, standard triage, included Edge Node, endpoint telemetry, hold-until-unisolate. **ITDR/Okta/AD/Kerberoasting are not listed on Silver** — they are an add-on module. Selling "Silver = Cloud & Identity ITDR" is an **internal packaging choice** not reflected on the public tier table.

| Marketing claim (Silver column) | Code reality | Status |
|--------------------------------|--------------|--------|
| Weekly vulnerability scans | `greenbone_cadence` accepts `weekly` | ✅ Achievable via entitlement |
| Daily IOC sync | MISP client live; needs `misp_enabled` | ⚠️ MISP VM healthy; not tied to Silver tier |
| Standard IR triage | SOC alerts/incidents + AI triage | ✅ |
| Endpoint telemetry | Wazuh ingest + customer alerts UI | ✅ |
| Hold-until-unisolate | EDR isolate with callback | ✅ (same as Gold) |
| Cloud Identity / Okta / AD | Phase 6 APIs + engine | ✅ Code; ⚠️ ops wiring |

---

### 2.2 Gold Tier — Core MDR & Active Containment

| # | Feature (audit scope) | Status | Evidence | Blockers before paid sale |
|---|----------------------|--------|----------|---------------------------|
| G1 | Wazuh instant ingress hook | ✅ | `POST /integrations/soc/hooks/wazuh/{token}`; 3 live `wazuh` alerts in DB | `WAZUH_INGRESS_TOKEN` configured; agents forwarding |
| G2 | Tenant resolution on ingest | ✅ | Agent-group binding; no silent DEMO fallback | Per-tenant Wazuh group binding must exist |
| G3 | `POST /v1/edr/actions/execute` | ⚠️ | `edr_actions.py` — isolate/kill/block-hash/forensics | **0 rows** in `edr_action_executions` today; re-prove on Windows agent |
| G4 | Verified isolate callback | ✅ | Hold-until-unisolate; KB-091 live proof on agent `006` (historical) | Re-run isolate demo; per-execution callback token still open (C7) |
| G5 | Kill process / block hash | ⚠️ | Dispatched-only proof for kill; block-hash is text denylist not WDAC | Do not sell block-hash as enterprise enforcement |
| G6 | Pre-LLM whitelist veto (`check_pre_llm_whitelist_veto`) | ✅ | 6/6 tests in `test_ai_triage.py`; skips Ollama at 100% confidence | None |
| G7 | Ollama `qwen2.5:7b` + 3s health probe | ✅ | `probe_ollama_health()` returned **True** (~11ms) against VM 115 | `AI_ALERT_BASE_URL` must stay reachable |
| G8 | Rule-based triage fallback | ✅ | `build_rule_based_triage_result()` when Ollama down | None |
| G9 | Vuln sync `/integrations/vuln/sync` | ⚠️ | Route + auth live; scan-complete timestamps exist | **`vulnerabilities` table = 0 rows** — VM 109 agent may not be posting findings |
| G10 | EASM sync `/integrations/easm/sync` | ✅ | **12 findings** in `tenant_easm_findings`; customer `EasmPage.tsx` | Confirm scan cadence for production tenants |
| G11 | Customer portal vuln/EASM views | ⚠️ | UI wired to real APIs | VMaaS portal empty until vuln agent repopulates data |
| G12 | Marketing "Daily automated scans" (Gold) | ❌ | `greenbone_cadence` only allows `weekly` \| `monthly` \| `off` | **Cannot sell daily scans without schema change** |

**Marketing alignment (kevantic.com Gold = "Enterprise NDR"):** Site promises daily scans, DeepSight NDR, live Apex Orchestrator, HA appliance pair, guided remediation.

| Marketing claim (Gold column) | Code reality | Status |
|------------------------------|--------------|--------|
| Daily automated vuln scans | Cadence enum caps at weekly | ❌ |
| NikTiar™ DeepSight NDR | `zeek_enabled` + NDR module | ⚠️ Classifier real; **0 suricata/zeek alerts** in DB |
| Live Apex Orchestrator (Shuffle/SOAR) | Shuffle + Redis retry queue | ✅ |
| HA appliance pair | Appliance provisioning exists | ⚠️ Ops/infra; no self-service HA UI |
| Guided remediation | TheHive + recommendations | ✅ |
| Spectre DFIR Triage | Velociraptor bridge configured | ⚠️ See Platinum DFIR rows |

---

### 2.3 Platinum Tier — Full MXDR & Deep Analytics

| # | Feature (audit scope) | Status | Evidence | Blockers before paid sale |
|---|----------------------|--------|----------|---------------------------|
| P1 | Suricata/Zeek source tagging | ⚠️ | `detect_ingress_source_tool()` in `soc_sync.py` | **Never fired live** — all 3 alerts are `wazuh` only |
| P2 | NDR customer/admin APIs | ✅ | `/customer/ndr/{short_code}/*`, `/admin/ndr/.../sync` | Enable `zeek_enabled` |
| P3 | NDR live sensor events | ❌ | 6 `tenant_ndr_events` rows, **all** `source=analysis_adapter` (stale lab seed) | Purge synthetic NDR data; wire Suricata/Zeek → Wazuh → SOC hook |
| P4 | Full-packet NDR (marketing) | ❌ | Flow metadata only in schema; no pcap store/retrieval | **Not implemented** — downgrade marketing to "flow-level NDR" |
| P5 | Live process tree (`/v1/edr/telemetry/process-tree`) | ✅ | `build_process_forest()` — Sysmon/Osquery normalization | Requires endpoint telemetry volume |
| P6 | Forensic artifact upload/download | ✅ | `PUT/GET /v1/edr/forensics/upload|download/{artifact_id}` | S3/local storage configured per deploy |
| P7 | Hunt results callback | ✅ | `POST /api/v1/telemetry/hunt-results` → `retrospective_service.apply_hunt_result()` | Requires NikTiar™ Edge or cloud datalake with Parquet |
| P8 | Retrospective zero-day hunts E2E | ❌ | `retrospective_hunt_jobs` = **0 rows** | Never exercised end-to-end in this deployment |
| P9 | MISP integration | ✅ | VM 108 healthy; IOCs in DB with `source=misp` | Enable `misp_enabled` per tenant |
| P10 | ThreatLens NLP | ⚠️ | `threatlens_nlp.py` — regex/heuristic IOC extraction | Marketed as "AI NLP"; technically deterministic, not LLM |
| P11 | ClickHouse OLAP adapter | ⚠️ | `ClickHouseAnalyticsAdapter` — **`is_configured()=False`** | `CLICKHOUSE_HOST` not in compose or `.env`; always PostgreSQL fallback |
| P12 | Async log archiver (`.jsonl.gz`) | ❌ | `log_archiver.py` exists; **`start_log_archiver_worker()` never called** from `main.py` | Wire startup hook + `LOG_ARCHIVER_ENABLED=true` + volume mount |
| P13 | Live memory DFIR (Platinum marketing) | ⚠️ | Velociraptor bridge healthy; `endpoint_forensics_service` seeds fabricated collections on bridge failure | Ungated synthetic fallback; some collections stuck `RUNNING` / 0 bytes |
| P14 | 15-min SLA + automated containment | ❌ | SLA is contractual/ops; auto-close opt-in only (`ENABLE_AUTO_CLOSE_LOW_RISK=false`) | Do not sell "autonomous SOC" as unsupervised AI |

**Marketing alignment (kevantic.com Platinum = "Full Autonomous SOC"):**

| Marketing claim (Platinum column) | Code reality | Status |
|----------------------------------|--------------|--------|
| DeepSight NDR (Full Packet) | No packet capture pipeline | ❌ |
| Custom threat feeds | MISP + manual IOC ingest | ⚠️ Partial |
| 15-min SLA + automated Apex containment | Manual SOC approval; opt-in auto-close | ❌ |
| Live memory & process tree DFIR | Process tree real; memory collections mixed/stuck | ⚠️ |
| Dedicated high-throughput cluster | Infra/ops concern | ⚠️ Not software-gated |
| 90-day retrospective zero-day sweeps | Hunt pipeline unproven (0 jobs) | ❌ |
| Continuous scanning + remediation | No continuous vuln remediation automation | ❌ |

---

### 2.4 Cross-tier platform foundations (all tiers)

| Feature | Status | Notes |
|---------|--------|-------|
| Multi-tenant RLS (`mssp_app`, migration 042) | ✅ | Force RLS on alerts/incidents/vulnerabilities |
| Appliance 3-tier auth (`X-Appliance-ID` + API key) | ✅ | SHA-256 hashed keys; constant-time compare |
| EDR 3-tier agent→tenant ownership | ✅ | Asset → alert history → Wazuh group |
| Customer IDOR protection (404 on mismatch) | ✅ | `require_tenant_match()` |
| Password never echoed in 422 errors | ✅ | Global validation sanitizer |
| Entitlement-gated customer modules | ✅ | `EntitlementGate` + `tenant_entitlements` |
| Tier-based auto-provisioning | ❌ | Manual per-flag only |
| Demo tenant full catalog | ✅ | `ALPHAWINCORP-6VS2` → `DEMO_FULL_ENTITLEMENTS` |

---

## 3. Technical Blockers by Tier (Must-Fix Before Selling)

### Silver (Cloud & Identity ITDR)

| Priority | Blocker | Resolution |
|----------|---------|------------|
| **P0** | No tier SKU provisioner | Add `tenant_tier` or sales runbook mapping Silver → `{cloud_identity_protection_enabled, enforce_mfa, ...}` |
| **P0** | M365 Graph not configured | Set `AZURE_TENANT_ID/CLIENT_ID/CLIENT_SECRET`; implement **per-tenant** admin-consent app registration |
| **P1** | Okta/AD forwarders not deployed | Document and ship connector agents calling `/api/v1/telemetry/okta` and `/ad` |
| **P1** | Identity detection state in-process only | Move `_EVENT_STORE` to Redis for multi-replica API |
| **P2** | ITDR portal empty for real tenants | Run Graph sync or ingest Okta/AD events before customer go-live |

### Gold (Core MDR & Active Containment)

| Priority | Blocker | Resolution |
|----------|---------|------------|
| **P0** | "Daily scans" not supported in code | Add `daily` to `greenbone_cadence` enum + scan scheduler, **or** change Gold marketing to weekly |
| **P0** | Vuln pipeline empty (`vulnerabilities` = 0) | Restore VM 109 Nuclei/Vuls agent posting to `/integrations/vuln/sync` |
| **P1** | EDR executions table empty | Re-prove isolate/kill on enrolled Windows agent; document in customer onboarding |
| **P1** | Shared EDR callback API key | Implement per-execution HMAC callback tokens (KB-091 C7) |
| **P2** | Block-hash not real enforcement | Relabel in UI/docs as "IOC denylist" until WDAC/AppLocker integration |

### Platinum (Full MXDR & Deep Analytics)

| Priority | Blocker | Resolution |
|----------|---------|------------|
| **P0** | Zero live Suricata/Zeek alerts | Deploy sensors on VM 106 path; validate `source_tool=suricata|zeek` in DB |
| **P0** | NDR customer data is synthetic | Delete `analysis_adapter` seed rows; fail-closed empty state until live import |
| **P0** | Full-packet NDR claimed but not built | Remove "Full Packet" from Platinum copy **or** build pcap pipeline |
| **P0** | Retrospective hunts never run | Execute one E2E hunt (Edge `hunt-results` or cloud datalake) before selling 90-day sweeps |
| **P1** | ClickHouse not deployed | Provision ClickHouse VM; set `CLICKHOUSE_HOST` in `.env` |
| **P1** | Log archiver dead code | Call `start_log_archiver_worker()` in `main.py` startup |
| **P1** | DFIR synthetic fallback ungated | Add `APP_ENV` gate to `endpoint_forensics_service` like NDR; remove fabricated "memory snapshot" rows |
| **P2** | 15-min SLA / autonomous SOC language | Reposition as **analyst-owned** SOC with AI assist (matches code honesty) |

---

## 4. Final Verdict — What to Sell Today vs. Stage

### ✅ Safe to sell today (with standard ops runbook)

These capabilities are **code-complete, tested, and operable** when entitlements are manually enabled and external VMs are wired:

| Capability | Typical tier mapping | Confidence |
|------------|-------------------|------------|
| Multi-tenant SOC portal (alerts, incidents, audit) | Bronze+ | High |
| Wazuh endpoint log ingest + customer-safe alerts | Bronze+ | High |
| Hold-until-unisolate host containment (verified callback) | Silver+ | High (re-prove per estate) |
| TOTP MFA + recovery codes + login rate-limiting | All portal users | High |
| AI Tier-1 triage with pre-LLM veto + Ollama failover | Gold+ (SOC internal) | High |
| EASM external attack surface monitoring | Add-on / Gold+ | High (12 live findings) |
| MISP threat intelligence IOC sync | Add-on / Silver+ | High |
| Okta + AD identity telemetry ingest APIs | ITDR add-on / Silver (internal) | High (connector deploy required) |
| MFA fatigue, impossible travel, Kerberoasting detections | ITDR add-on | High (needs event volume) |
| PostgreSQL RLS tenant isolation | Platform-wide | High |
| NikTiar™ Edge appliance ingest + heartbeat | Silver+ | High |

### ⚠️ Sell only with explicit caveats / professional services

| Capability | Caveat to disclose |
|------------|-------------------|
| M365 / Entra ITDR module | Single-tenant Graph app today; per-customer consent flow required for scale |
| Vulnerability management (VMaaS) | Pipeline proven historically but **currently empty** — verify VM 109 agent before go-live |
| NDR (DeepSight) | Flow-level enrichment only; **no live Suricata/Zeek alerts** in current DB |
| EDR kill / block-hash | Kill is dispatch-only; block-hash is denylist file, not OS enforcement |
| ThreatLens "AI NLP" | Regex-based IOC extraction, not LLM |
| Process tree / DFIR upload | Real endpoints; requires Sysmon/Osquery telemetry on endpoints |
| Weekly (not daily) vuln scans | Backend cannot schedule daily until cadence enum extended |

### ❌ Do not sell until staged (future release)

| Capability | Why |
|------------|-----|
| **Platinum "Full Autonomous SOC"** as unsupervised AI | Auto-close disabled by default; analysts own decisions |
| **15-minute response SLA** | Contractual; not enforced in software |
| **Full-packet NDR** | Not implemented |
| **90-day retrospective zero-day sweeps** | 0 hunt jobs executed E2E |
| **ClickHouse OLAP analytics at scale** | Adapter exists; no ClickHouse deployment |
| **Automated log archival to `.jsonl.gz`** | Worker not started in application lifecycle |
| **Daily / continuous vuln scanning (Gold/Platinum marketing)** | Cadence enum + automation missing |
| **HA appliance pair / dedicated cluster** as self-service | Infra provisioning playbook only |
| **Live memory DFIR packages** as downloadable artifacts | Mixed synthetic/stuck jobs; download path incomplete for some collection types |

---

## 5. Recommended Tier Repositioning (Honest Packaging)

Until blockers are cleared, align sales packaging with **what the control plane can prove**:

| Tier | Sell as… | Enable in code (manual entitlements) | Do not claim yet |
|------|----------|--------------------------------------|------------------|
| **Silver** | Mid-market MDR + portal MFA + optional ITDR connectors | `wazuh_siem`, `thehive_mode=full`, `enforce_mfa`, `cloud_identity_protection_enabled`, weekly `greenbone_cadence`, `misp_enabled` | Fully autonomous ITDR for multi-tenant M365 without Graph setup |
| **Gold** | Enterprise MDR + SOAR + weekly VMaaS + flow NDR | Above + `shuffle_mode=standard`, `zeek_enabled`, `greenbone_enabled`, `velociraptor_enabled`, `continuous_compliance_enabled` | Daily scans, full-packet NDR, guaranteed sub-15-min SLA |
| **Platinum** | Mission-critical MDR + TI + DFIR + hunt-ready platform | Above + `external_attack_surface_enabled`, custom MISP feeds, Edge hunt callback, priority SOC runbook | Autonomous SOC, live memory DFIR at scale, ClickHouse OLAP, 90-day hunts without E2E proof |

---

## 6. Live Environment Snapshot (2026-08-28)

| Check | Result |
|-------|--------|
| `APP_ENV` | `development` |
| `security_alerts` by `source_tool` | `wazuh`: 3 |
| `tenant_ndr_events` | 6 (all `analysis_adapter`) |
| `vulnerabilities` | 0 |
| `tenant_easm_findings` | 12 |
| `retrospective_hunt_jobs` | 0 |
| `edr_action_executions` | 0 |
| Ollama VM 115 health | **Healthy** |
| ClickHouse configured | **No** |
| ITDR lab seed allowed | **No** (fail-closed) |
| NDR lab seed allowed | **No** |
| Unit tests (identity + AI + MFA) | **37 passed** |

---

## 7. Appendix — Audit Methodology

1. **Static code review** — `backend-api/app/`, `frontend-admin/`, `frontend-customer/`, `postgres/init/`, `docker-compose.yml`, `website-niktiar/`.
2. **Live DB queries** — `mssp-postgres` container (`security_alerts`, `tenant_ndr_events`, `vulnerabilities`, `tenant_easm_findings`, `retrospective_hunt_jobs`, `edr_action_executions`).
3. **Runtime probes** — `probe_ollama_health()`, `ClickHouseAnalyticsAdapter.is_configured()`, `_allow_lab_sample_seed()` flags inside `mssp-backend-api`.
4. **Unit test execution** — `test_identity_telemetry`, `test_ai_triage`, `test_auth_mfa` (37 tests, all OK).
5. **Marketing cross-check** — [kevantic.com](https://www.kevantic.com/) homepage + `website-niktiar/services.html` tier matrix.

---

*This report should be refreshed after: (1) tier provisioner implementation, (2) VM 109 vuln agent restoration, (3) live Suricata/Zeek alert proof, (4) first successful retrospective hunt job, (5) ClickHouse + log archiver wiring.*
