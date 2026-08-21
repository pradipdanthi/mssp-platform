# End-to-End Platform Gap Analysis

**Classification:** Internal — executive diagnostic (not a certification report)  
**Subject:** Kevantic MSSP Control Plane (`/opt/mssp-control`)  
**Roles applied:** Independent Principal Cyber Security Auditor · Enterprise Solutions Architect · Lead Software Engineer  
**Audit date:** 2026-08-21  
**Method:** Static inspection of live source, Compose, SQL, Admin/Customer UIs, website copy, appliance CLI, golden-image bake path, and Active Response packs. Secrets files were not opened. No penetration test or live exploit was performed.  
**Related prior work:** `docs/audit/ISO27001-OWASP-COMPLIANCE-REPORT.md` (2026-08-19 secure-coding pass); this document is a broader architecture / compliance / market-honesty review and **does not replace** that SAST report.

**Scope inspected**

- `backend-api/` (FastAPI, adapters, RBAC, compliance, EDR, ingest)
- `frontend-admin/`, `frontend-customer/`
- `website-junexis/`
- `kevantic-appliance/` (CLI, licensing, bake, engine jobs)
- `deploy/wazuh-active-response/`
- `mssp-appliance-builder/` (spot-check of provision path)
- `postgres/init/`, `docker-compose.yml`, `deploy/environments/`

---

## 1. Executive summary

The platform is a **real multi-tenant MSSP control plane**, not a re-skinned engine dashboard. Customer APIs consistently enforce tenant isolation (wrong tenant → **404**). Endpoint isolate/un-isolate on Windows is fail-closed (hold until Un-isolate). The appliance Edge Node model (raw logs stay local; metadata/high-severity forward) is a genuine architectural differentiator. Secrets are file-backed; `JWT_SECRET` fails closed if unset.

It is **not** ready to be sold as an attested ISO 27001 / PCI-DSS / HIPAA *product*. Continuous Compliance scorecards are **Wazuh SCA-derived** and mapped to CIS / ISO 27001 / PCI-DSS / NIST by **policy-name heuristics**. There is **no HIPAA scoring engine**. The public website still advertises HIPAA scorecards. Identity (ITDR) and some vuln paths can still **seed synthetic findings** when live adapters return empty — that is an integrity problem if a paying customer sees them as live threats.

**Overall platform readiness score: 69 / 100**

| Lens | Score | Meaning |
|------|------:|---------|
| Tenant isolation & customer data leakage | 92 | Production-grade fail-closed design |
| Secure coding (OWASP / ISO A.8.28) | 84 | Strong; prior SAST pass still holds |
| EDR isolate / un-isolate honesty | 82 | Windows hold-until-unisolate is real; timeout-as-success remains a honesty leak |
| Appliance Edge Node + JWS licensing | 80 | Golden 199 baked 2026-08-21; signed entitlements required |
| Authentication (ISO A.5.15) | 72 | bcrypt + JWT + RBAC; **no MFA, no lockout, no refresh-token rotation** |
| Secrets / TLS defaults | 68 | File secrets good; Wazuh TLS verify defaults **off** |
| Audit completeness (PCI Req 10 / HIPAA §164.312) | 52 | Login audited; many privileged mutations are not |
| HA / SPOF / scale | 42 | Single Postgres, Redis, in-process workers, SSH tunnel to VM 114 |
| Compliance CaaS vs marketing claims | 48 | Real SCA data; not a control library; HIPAA claimed, not implemented |
| **Composite (weighted)** | **69** | Capable on-prem MSSP **ops** platform; not a certified GRC product |

**Verdict:** Safe to operate as an on-prem / hybrid MSSP **control plane** for current tenants if marketing copy is honest and Graph/scanner adapters are live. **Do not** take HIPAA, PCI-DSS, or ISO 27001 *customers* on the basis of portal scorecards until the Top 5 actions below are done.

---

## 2. Compliance matrix

Legend: **C** = control present and evidenced in code · **P** = partial / heuristic · **G** = gap · **N/A** = not claimed as a certified QSA/HIPAA assessment of *this* lab.

### 2.1 ISO/IEC 27001:2022 Annex A (selected)

| Control | Status | Evidence | Gap |
|---------|--------|----------|-----|
| A.5.15 Access control | **P** | RBAC via `require_roles` / `require_tenant_match` (`backend-api/app/api/dependencies.py`). Portal split: Admin staff vs Customer roles. bcrypt passwords (`app/core/security.py`). | No MFA/TOTP on portals. No account lockout after failed logins. Password minimum is 8 characters (`app/schemas/tenants.py`) without complexity or rotation policy. JWT HS256, default 60 minutes, no refresh-token family. |
| A.8.8 Technical vulnerabilities | **P** | Nuclei + Vuls + optional Greenbone CE on VM 109; normalize → Admin triage → customer recommendations. Linux/Windows EDR telemetry. | Scanner engines are not HA. `vmaas_service.py` can **seed sample findings** when live import is empty. Greenbone Enterprise still deferred (KB-077). |
| A.8.12 Data leakage prevention | **C** (customer path) | Customer APIs omit forbidden fields (IPs, raw JSON, credentials). `customer_safe_labels.py` maps engines to NikTiar™ names. Customer frontend has **zero** `/admin` calls. Appliance forwarder sends high/critical **metadata**, not raw packet captures. | SOC roles are cross-tenant by design (large blast radius if a staff token is stolen). Presigned forensics URLs are bearer-less within TTL. |
| A.8.28 Secure coding | **C** | Parameterized SQL; Pydantic `extra="forbid"` on sensitive bodies; Nuclei template path validation in `kevantic-appliance/appliance/jobs/executor.py`; prior 2026-08-19 SAST report: 0 Critical/High remaining. | Lab scripts still pass some passwords on CLI (`scripts/kb070_*`, WinRM helper) — ops-only, not runtime. |
| A.8.15 Logging | **P** | `audit_logs` table + Admin/Customer audit UIs (`audit_service.py`, `audit_logs.py`). Login success/failure written in `auth.py`. | Many privileged writes unaudited (see §3 High). No dedicated SIEM of the **control plane** itself (Compose logs ≠ PCI log review). |
| A.5.23 Cloud services | **P** | Production env templates exist (`deploy/environments/`). Master verifier `--release`. | Runtime `InfraSettings` still defaults to `192.168.0.x` (`app/core/config.py`). Cloud cutover is documented, not executed. |

**ISO scorecards in the Customer portal** are **not** an ISO 27001 ISMS. They are SCA check rollups tagged `ISO_27001` when a Wazuh policy name/key contains “iso” (`sca_compliance_service.py` `FRAMEWORK_ALIASES` / `_policy_frameworks`). That is **indicative hardening**, not Annex A evidence.

### 2.2 PCI-DSS v4.0 (selected)

| Requirement | Status | Evidence | Gap |
|-------------|--------|----------|-----|
| Req 6 — Secure systems/software | **P** | Secure-coding controls above; no exploitable SQLi/command injection found in application runtime. | No documented SDLC gate (SAST in CI on every PR) in this repo beyond validator scripts. Dependency pinning exists (`requirements.txt`); no visible SCA of *control-plane* libraries in CI. |
| Req 8 — Identify users | **P** | Unique portal users, bcrypt, JWT, role split. | No MFA (Req 8.4.2 for access to CDE-equivalent consoles is typically **required**). No lockout (8.3.4-class). |
| Req 10 — Log and monitor | **G / P** | Auth events land in `audit_logs`. Customer audit view is scrubbed. | Credential rotation, activation tokens, delegated user create/delete/password reset, EDR execute, alert/incident triage, appliance job ack — **not consistently audited**. No file-integrity monitoring of the control plane. No 12-month retain/review process encoded. |
| Req 3 — Stored account data | **N/A / C** | Platform is not a cardholder-data environment by design; PAN is not in schema. | If a tenant’s logs ever contain PAN, appliance local retention + customer-safe APIs help, but there is no DLP classifier. |
| Network / CDE segmentation | **P** | Appliance locked egress model (bootstrap then SOC-only) is designed in `kevantic-appliance`. | Lab Compose still publishes Admin/Customer on LAN HTTP. Production TLS is template-driven, not enforced in code when `APP_ENV=production`. |

**PCI scorecards** in the portal = SCA checks whose policy blob contains “pci”. They are **not** a ROC, SAQ, or Req 6/10 evidence pack.

### 2.3 HIPAA Security Rule (selected)

| Standard | Status | Evidence | Gap |
|----------|--------|----------|-----|
| §164.312(a) Access control | **P** | Unique users, RBAC, tenant 404. | No MFA. Emergency access / auto-logoff policy not encoded beyond JWT expiry. |
| §164.312(b) Audit controls | **G** | Partial `audit_logs`. | Insufficient coverage of ePHI-adjacent actions (containment, user provisioning, token issue). No HIPAA-specific audit report. |
| §164.312(c) Integrity | **P** | Parameterized DB; appliance JWS license verify; forensics HMAC. | ITDR `_seed_events_for_config` inserts **synthetic** identity events when Graph returns 0 (`itdr_service.py` ~474–501). That violates integrity of “security incident” records if shown to a healthcare customer. |
| §164.312(d) Authentication | **P** | Password + JWT. | No MFA; no session binding. |
| **HIPAA scorecard product** | **G** | Website/pitch claim HIPAA scorecards. | `CUSTOMER_FRAMEWORKS = ("CIS", "ISO_27001", "PCI_DSS", "NIST")` — **HIPAA is absent** from `sca_compliance_service.py`. Customer `CompliancePage.tsx` has no HIPAA tab. Only a vuln-request dropdown label exists (`VulnerabilitiesPage.tsx`). |

**Bottom line:** You can *support* a HIPAA-covered client’s SOC operations (tenant isolation, local logs, audit-ish trails). You **cannot** honestly sell “HIPAA scorecards” or “HIPAA reporting” as a built-in CaaS module today.

### 2.4 Simulated / stubbed metrics (integrity)

| Module | Live path | Stub / seed path | Customer-visible risk |
|--------|-----------|------------------|------------------------|
| Continuous Compliance (SCA) | `wazuh_client.list_sca_policies/checks` → Postgres | Empty estate → 0% and `sync_status=empty` (honest) | **Low** — empty is labelled |
| Framework % | Keyword map from SCA policy names | Not a control-by-control ISO/PCI/HIPAA library | **High** if sold as attested readiness |
| ITDR | Microsoft Graph when `AZURE_*` set | `_seed_events_for_config` if Graph missing or empty | **High** — synthetic incidents look real |
| Vuls/Nuclei adapter (`vmaas_service.py`) | Live import when present | `_seed_sample_findings` when import empty | **High** if customer vuln dashboard uses adapter path |
| Admin Incident “Trigger orchestration” | — | `window.alert` only (`IncidentDrawer.tsx`) | **Medium** — fake SOAR affordance |
| ITDR Graph | Token cache in `itdr_graph_client.py` | Waiting on Azure app secrets | Documented; still a live gap |

SCA itself is **not simulated**. The **mapping** of SCA → ISO/PCI/NIST percentages **is heuristic**. HIPAA scores **do not exist**.

---

## 3. Prioritized pitfalls and drawbacks

### Critical (do not sell / ship copy as-is)

| ID | Finding | Evidence | Remediation |
|----|---------|----------|-------------|
| C-1 | **Public site claims HIPAA (and “real-time PCI/ISO/HIPAA scorecards”) that the product cannot generate.** | `website-junexis/index.html` (meta + body), `platform.html`, `solutions.html`, `portal.html`, `services.html`; pitch deck `docs/pitch-deck/notebooklm-source-deck.md`. Backend: `CUSTOMER_FRAMEWORKS` has no HIPAA. | Strip HIPAA from website/pitch **or** implement a real HIPAA Security Rule control library with evidence objects. Until then, scorecards must be labelled “CIS/ISO/PCI/NIST **hardening indicators from endpoint configuration assessment**, not a certification.” |
| C-2 | **ITDR sync writes synthetic identity threats into the tenant database when live Graph yields zero events.** | `backend-api/app/services/itdr_service.py` `sync_tenant_itdr`: `live = _import_graph_events_for_config`; `else: _seed_events_for_config`. Samples include impossible travel / MFA fatigue with RFC 5737 IPs. | Fail closed: if Graph is unconfigured, return `sync_status=empty` and **do not insert** demo events in `APP_ENV=production`. Gate sample seeder behind an explicit `ITDR_ALLOW_SAMPLE_ADAPTER=true` lab flag. Surface `source` on Admin UI; never imply live Entra on Customer UI unless `source=microsoft_graph`. |

No Critical *exploitable* IDOR, SQLi, or customer cross-tenant read was found in this pass.

### High

| ID | Finding | Evidence | Remediation |
|----|---------|----------|-------------|
| H-1 | **Wazuh API TLS verification defaults to off**, with no production fail-closed. | `wazuh_client.py` `_ssl_context()` uses `WAZUH_API_VERIFY_TLS` default `"false"`; `CERT_NONE`. Production *example* env sets `true`, but code does not require it when `APP_ENV=production`. MITM on Manager API = forged AR / stolen token. | If `APP_ENV=production` (or `WAZUH_API_VERIFY_TLS` unset in prod), **refuse to start** unless verify is true. Add assertion to `verify_platform_state.py`. |
| H-2 | **Audit coverage is too thin for PCI Req 10 / HIPAA audit controls.** | `write_audit_event` used on login (`auth.py`). Missing or inconsistent on: `appliance_management.py` (rotate credential, activation token create/revoke), `delegated_user_management_v1.py` (create/update/delete/reset password), `alert_incident_triage.py`, `edr.py` execute, `admin_ai_chat.py`. `write_audit_event` swallows DB errors (`audit_service.py` except → `error: True`) — silent audit loss. | Central middleware or service-layer hook: every mutating admin/customer/EDR/appliance route writes audit **before** return. Fail the request (or dead-letter) if audit insert fails in production. Include `source_ip`. |
| H-3 | **Shared engine callback key can forge EDR success for any execution.** | `edr.py` `_require_callback_auth` accepts `EDR_CALLBACK_API_KEY` **or** `SOC_SYNC_API_KEY`. One leaked key impersonates all endpoints. | Per-appliance or per-execution HMAC (already used for forensics URLs). Rotate; stop aliasing SOC sync key as EDR callback. |
| H-4 | **Appliance AR timeout is acknowledged as success (`ok=True`), which can mark isolation “isolated” without `applied=true`.** | `register_ops.py` `_is_transient_ar_failure` + `_run_local_ar` returns `(True, "... timeout; confirm on endpoint")`. `edr_actions.py` treats missing `applied` as not-false → `isolation_status='isolated'`. Execution *text* stays honest; **table status does not**. | Return `success=False` or a distinct `success=unknown` / `applied=null` and **never** promote `edr_endpoint_isolation.isolation_status` until endpoint callback `applied=true`. |
| H-5 | **`customer_admin` can isolate/kill/block without SOC co-sign.** | `edr_actions.py` `ALLOWED_CUSTOMER_ACTIONS`. Contractual model may want this; for regulated estates it is a dual-control gap (ISO A.5.15 / SOX-like). | Entitlement flag `customer_containment_requires_soc_approval`; default **on** for HIPAA/PCI tenants. |
| H-6 | **Vuls/Nuclei path can seed sample CVEs.** | `vmaas_service.py` `_seed_sample_findings` when live import empty. | Same pattern as C-2: lab flag only; production empty state. |
| H-7 | **Admin UI hardcodes lab TheHive URL and a non-functional SOAR button.** | `frontend-admin/src/components/IncidentDrawer.tsx` (~73, 137–159): `https://192.168.0.212` and `window.alert`. | Drive URL from `VITE_CASE_CONSOLE_URL`; wire Shuffle webhook or hide the button until live. |

### Medium

| ID | Finding | Evidence | Remediation |
|----|---------|----------|-------------|
| M-1 | **Single Postgres + single Redis = control-plane SPOF.** | `docker-compose.yml` one of each; pool max 20 (`db/session.py`). No Patroni/Sentinel. DR backup is **recovery**, not availability. | Document RTO/RPO; add streaming replica + Redis Sentinel (or managed cloud) before multi-customer SLA. |
| M-2 | **AI + Shuffle workers are in-process daemon threads** inside one `backend-api` replica. | `ai_alert_queue.py`, `shuffle_retry_queue.py`, `main.py` startup. Hung thread ≠ `/health` fail. | Split workers to separate Compose services; liveness on queue lag. |
| M-3 | **VM 114 Appliance Management depends on SSH tunnel to VM 100 loopback DB/Redis.** | Compose comments + `appliance-mgmt/docker-compose.yml` `network_mode: host`. Tunnel drop = register/heartbeat outage. | Dedicated private network or local replica; health check on tunnel. |
| M-4 | **Lab IPs as runtime defaults.** | `InfraSettings` (`config.py` 67–79); CORS `_DEFAULT_ORIGINS`; `applianceGateway.ts` `http://192.168.0.224:8000`; MISP/Velociraptor client defaults. | Empty default in production images; fail start if required URL unset. |
| M-5 | **SCA→framework % is keyword matching, not a control catalog.** | `_normalize_frameworks` / `_policy_frameworks` / `_guess_severity` in `sca_compliance_service.py`. Severity guessed from title words (“password”, “rdp”). | Maintain a versioned control map (CIS 8 / ISO A.x / PCI 4.0) and show “indicative” until mapped. |
| M-6 | **No portal MFA, lockout, or refresh-token rotation.** | `security.py`, `auth.py`. Failed logins audited but unlimited. | Add TOTP for staff first; lockout after N failures; rotate refresh tokens. |
| M-7 | **Forensics default storage is local disk on VM 100.** | `edr_forensics_storage.py` `DEFAULT_STORAGE_ROOT=/var/lib/mssp/forensics`. S3 exists if `EDR_S3_BUCKET` set. | Require object storage in production; encrypt at rest. |
| M-8 | **Public Linux install URL is unauthenticated except secret token in the path.** | `public_agent_install.py`. Token leak (chat, proxy logs) = installer disclosure. | Single-use tokens, short TTL, bind to source IP optional. |
| M-9 | **Synchronous Wazuh authenticate+AR inside HTTP** on some EDR paths (cloud manager). | `wazuh_client.py` / `edr_actions.py`. Appliance path is job-queue (better). | Always queue AR; never block API workers on Manager 120s timeout. |
| M-10 | **Zeek / MISP / Velociraptor** have adapters/playbooks; live lab engines still incomplete vs “full XDR” catalog. | `CONTEXT.md` connected engines vs KB-036 stack. | Honest catalog: ship as “available / pending live” per engine. |
| M-11 | **Golden 199 vs field appliances.** 199 was baked 2026-08-21 (`gaps-attr-linux-api120`). Beta/field nodes need the same AR/timeout/attributions upgrade or they drift. | Bake script vs live 226. | Run field `upgrade_appliance_fleet_reporting.sh` / `sync_appliance_edr_ar_scripts.sh` on every deployed appliance after golden bake. |

### Low

| ID | Finding | Evidence | Remediation |
|----|---------|----------|-------------|
| L-1 | Audit pretty-labels don’t match auth action strings (`AUTH_LOGIN` vs `LOGIN_SUCCESS`). | `audit_logs.py` `ACTION_LABELS` vs `auth.py` | Align enums. |
| L-2 | CORS default allow-list includes lab origins. | `app/core/cors.py` | Empty default in prod. |
| L-3 | `dependencies.py` header comment is stale (says KB-010 routes were unauthenticated). | Top of file | Update comment to match current enforcement. |
| L-4 | Watchdog copy in `endpoint_configs` vs `deploy/` Windows pack hashes match for isolate scripts; extra `.py` helpers in `deploy/windows` are not in the ZIP pack (unused on Windows `.cmd` path). | Hash compare 2026-08-21 | Document or delete unused `.py` AR helpers. |
| L-5 | Ollama/AI chat is a SPOF (VM 115); timeout surfaces as “AI chat unavailable”. | `ai_admin_chat.py`; ops incident 2026-08-21 | Status pill should probe Ollama, not only `AI_CHAT_ENABLED`. |

---

## 4. Core platform strengths and unfair advantages

These are **evidenced**, not marketing adjectives.

1. **NikTiar™ Edge Node / zero-cloud-tax ingestion**  
   Appliance keeps raw alerts locally (`alerts.json` / datalake). KB-093P forwarder sends **high/critical metadata** to the control plane, not full pcaps or raw customer logs on a public API. Customer APIs are capability-labelled (`customer_safe_labels.py`). This is a real data-residency story competitors who ship everything to a multi-tenant SIEM SaaS cannot match without extra contracts.

2. **Fail-closed multi-tenancy**  
   `require_tenant_match` → **404**. Ingest tenant_id comes from the **authenticated appliance row**, never from client JSON (`appliance_alert_ingest.py` + `endpoint_asset_resolve.py`). Hostname collision cannot attach Tenant B’s asset to Tenant A.

3. **Hold-until-Un-isolate EDR (Windows)**  
   `mssp-isolate-host.ps1`: default-deny firewall, Manager 1514/1515 + DHCP/loopback only, watchdog, **ignores Wazuh timed delete**. Golden VM 199 (snapshot `gaps-attr-linux-api120`, git `3db10f3`) checksum-matches current git AR pack. This is a productized containment story, not a lab iptables one-liner.

4. **Containment honesty (mostly)**  
   Dispatch ≠ verified. Endpoint `applied=true` is required before “Verified”. Customer never sees raw engine JSON. (Honesty leak is H-4 timeout→success; fixable without changing the model.)

5. **Cryptographic appliance licensing**  
   Ed25519 JWS, `iss=kevantic-license`, unsigned `apply_entitlements` rejected, hourly `kevantic-license-enforce.timer`, pubkey baked on 199. Catalogue engines stay idle until a signed license. This is a commercial control most OSS MSSP stacks lack.

6. **Two-portal product, one system of record**  
   FastAPI + PostgreSQL is the product. Wazuh/TheHive/Shuffle/Suricata/Nuclei are adapters. Admin `:3000` / Customer `:3001` nginx production builds. This is the architecture that survives a later cloud move (KB-094 pack + `verify_platform_state.py`).

7. **Brand / OSS compliance hygiene**  
   `ATTRIBUTIONS.md` + baked `/usr/share/doc/kevantic/ATTRIBUTIONS.txt`. Verifier CHECK 6. Customer/Admin TSX must not render upstream engine brands.

8. **Parameterized everything + fail-closed JWT**  
   No default JWT secret. Secrets as 0600 files under `.secrets/` bind-mounted read-only.

**Competitive positioning (truthful):** “On-prem Edge Node + our control plane + hold-until-unisolate + signed entitlements.”  
**Not truthful (yet):** “Automated HIPAA/PCI/ISO certification scorecards” or “always-on live Entra ITDR” without Graph credentials.

---

## 5. Immediate action plan (Top 5 before market launch)

| # | Action | Owner surface | Done when |
|---|--------|---------------|-----------|
| 1 | **Honesty pass on compliance & ITDR.** Remove HIPAA from `website-junexis/` and pitch until a real control pack exists. Disable ITDR/Vuls sample seeders unless `APP_ENV=lab` (or explicit flags). Label portal scores “configuration assessment indicators.” | Website + `itdr_service.py` + `vmaas_service.py` + Compliance UI copy | No synthetic events in production DB; legal/marketing review sign-off |
| 2 | **Production TLS fail-closed.** Refuse API start if `APP_ENV=production` and `WAZUH_API_VERIFY_TLS` is not true. Empty-out lab IP defaults in `InfraSettings` / CORS / `applianceGateway.ts` / `IncidentDrawer.tsx`. | `wazuh_client.py`, `config.py`, frontends, `verify_platform_state.py` | Verifier assertion; cloud `.env` cannot silently MITM |
| 3 | **Audit completeness.** Instrument credential rotation, activation tokens, user lifecycle, EDR execute, triage, AI chat. Fail closed if audit insert fails in production. Align action enums. | `audit_service.py` + listed route modules | PCI Req 10 sample: every privileged mutation has a row with actor, tenant, IP, outcome |
| 4 | **Containment status honesty.** AR timeout / 3021 must not set `isolation_status=isolated`. Optional SOC co-sign for customer-initiated isolate. Split EDR callback key from SOC sync key. | `register_ops.py`, `edr_actions.py`, `edr.py` | Table status matches endpoint `applied` |
| 5 | **Availability story.** Write RTO/RPO for single-node Postgres/Redis; or add replica. Move AI/Shuffle off the API process. MFA for `platform_admin` / `soc_*`. | Compose + auth + runbook | SLA sheet a prospect can sign without lying |

**Do not block launch on:** Zeek/MISP/Velociraptor if catalog cards say “roadmap”; Greenbone Enterprise (KB-077 deferred); full ISO certification of the *company* (separate ISMS program).

---

## 6. Architecture notes (SPOF / scale)

```
Customers ──► nginx :3000/:3001 ──► FastAPI :8000 ──► Postgres (1) + Redis (1)
                                      │
                    ┌─────────────────┼─────────────────┐
                    ▼                 ▼                 ▼
              VM 101 Wazuh      VM 102 TheHive     VM 114 Appl. Mgmt
              VM 106 Suricata   VM 109 scanners    (SSH tunnel to 100)
              VM 115 Ollama (optional AI)
              VM 199 golden (stopped clone source)
```

- **SPOF:** VM 100 (API+DB+UI), Postgres volume, Redis, SSH tunnel for 114, Ollama for AI chat.  
- **Scale:** sync Wazuh HTTP in request path; single AI consumer thread; DB pool 20. Fine for tens of tenants; not fine for hundreds without splitting workers and adding PgBouncer + read replica.  
- **Resilience (good):** isolate firewall state is **local on the endpoint** (survives Manager outage). Appliance forwarder backs off. Redis queues retry then dead-letter.

---

## 7. Tenant isolation & leakage (attestation)

| Check | Result |
|-------|--------|
| Customer mismatch | **404** (`require_tenant_match`) |
| Customer SQL | `tenant_id = %s` from server-resolved tenant, not client |
| Customer UI → `/admin` | **None** |
| Appliance ingest tenant | From verified appliance credentials only |
| Asset link | `WHERE tenant_id = %s` on wazuh_agent_id and hostname |
| EDR customer execute other tenant | Denied |
| Forensics URL | HMAC binds `purpose\|artifact_id\|tenant_id\|exp` |
| Raw logs on customer portal | Forbidden field set + capability labels |
| Edge raw logs | Local Manager/datalake; public endpoints do not expose `raw_event` |

**Residual (by design):** `platform_admin` / `soc_manager` / `soc_analyst` are cross-tenant. Protect those accounts as production crown jewels (MFA — currently missing).

---

## 8. Scoring method (so this is not a vanity number)

Weighted domains (§1 table). Deductions applied for: HIPAA copy (C-1), synthetic ITDR (C-2), TLS default (H-1), audit holes (H-2), callback key (H-3), timeout-as-isolated (H-4), no MFA (M-6), single-node HA (M-1/M-2). Credits for: tenant 404, Edge Node, JWS license, Windows hold-until-unisolate, parameterized SQL, customer-safe labels.

A **90+** score would require: MFA + lockout, production TLS fail-closed, complete audit, no sample seeders, HA Postgres, honest website, Graph-live ITDR, and a real (even slim) HIPAA/PCI control map with evidence export.

---

## 9. Files most relevant to remediations

- `backend-api/app/services/itdr_service.py` — sample seeder  
- `backend-api/app/services/vmaas_service.py` — sample CVEs  
- `backend-api/app/services/sca_compliance_service.py` — framework heuristics  
- `backend-api/app/services/wazuh_client.py` — TLS  
- `backend-api/app/core/config.py` — lab IP defaults  
- `backend-api/app/services/audit_service.py` + mutating routes  
- `backend-api/app/api/routes/edr.py` — callback auth  
- `kevantic-appliance/cli/kevantic-cli/kevantic_cli/register_ops.py` — AR timeout  
- `backend-api/app/services/edr_actions.py` — isolation_status  
- `frontend-admin/src/components/IncidentDrawer.tsx` — lab TheHive / fake SOAR  
- `frontend-admin/src/config/applianceGateway.ts` — lab gateway  
- `website-junexis/*.html` — HIPAA claims  
- `deploy/wazuh-active-response/windows/mssp-isolate-host.ps1` — containment (strength)

---

## 10. Auditor statement

This is an **independent-style code and architecture diagnostic**, not an ISO 27001 certification, PCI QSA ROC, or HIPAA legal opinion. Findings are tied to files inspected on 2026-08-21 against git `3db10f3` (plus uncommitted bake-script/docs changes in the working tree). Live exploit testing was out of scope.

**Sign-off recommendation:** Proceed to market as a **hybrid MSSP control plane with Edge Node containment**, with the Top 5 closed or explicitly accepted in a dated risk register. Do not proceed to market as a **compliance-certification or HIPAA CaaS product** until C-1 and C-2 are closed.

---

*End of report.*
