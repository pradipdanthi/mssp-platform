# Platform Gap Analysis & Market Capability Maturity Report

**Product:** Kestrel Cyber MSSP Control Plane  
**Repository:** `/opt/mssp-control`  
**Audit date:** 2026-07-31  
**Method:** Read-only repository audit (API routes, PostgreSQL schemas, adapters, Admin `:3000` / Customer `:3001` UIs, deploy AR packs, KB docs, prior stack audit). **No feature code written. No deploys in this phase.**  
**Related prior audit:** `docs/STACK_AUDIT_MARKET_READINESS_REPORT.md` (2026-07-29 — HA/security readiness; complementary to this market-capability focus).

**Source of truth hierarchy used:** live routes/schemas → git tags/commits → validation docs → CONTEXT.md / Ops Bible.

---

## 1. Executive Summary & Current Maturity Rating (Level 1–5)

### Rating scale (this report)

| Level | Label | Meaning |
|------:|-------|---------|
| **1** | Basic log collector / SIEM shell | Ingest + store; little triage productization |
| **2** | Managed Detection & Response (MDR) | Multi-tenant alerts/incidents, customer-safe portal, SOC triage |
| **3** | Co-managed Enterprise MDR / emerging MXDR | Endpoint response (isolate/kill), SOAR cases, vuln program, entitlements |
| **4** | Advanced XDR + identity/cloud + continuous exposure | ITDR/M365, EASM, compliance scorecards, hunting workflows |
| **5** | Full-spectrum managed cyber platform | Deception, automated compliance-as-a-service, mature cloud ITDR, enterprise HA |

### Current rating: **Level 3 (solid) — Co-Managed MDR / Emerging MXDR**

**Verdict in one sentence:** You already operate a real multi-tenant MSSP **control plane** (not a re-skinned Wazuh UI) with live detection engines, case/SOAR wiring, vulnerability recommendations, and **Windows host quarantine** with honesty callbacks — but you are **not yet** in the market tier that sells ITDR/M365, external attack-surface programs, CIS/ISO scorecards, or deception as first-class products.

| Strength | Gap that caps the rating |
|----------|---------------------------|
| Admin + Customer portals, RBAC, fail-closed tenancy | No Azure AD / M365 / CloudTrail / GCP audit ingest adapters |
| Wazuh + Suricata + TheHive + Shuffle live | No EASM (subdomain/ASN/public HTTP discovery) product path |
| Nuclei + Vuls + Greenbone CE → promote → customer recommendations | No CIS/SCA / compliance scorecard tables or Customer UI |
| EDR isolate/kill/forensics model + Windows AR pack | No canary/honeypot/deception webhooks or playbooks |
| Entitlements + upgrade requests + monthly reports | Zeek / MISP / Velociraptor still entitlement flags / roadmap, not live engines |

**Market positioning today (honest):** Sell **co-managed endpoint + network detection, incident response, and vulnerability management** with a branded customer portal. Do **not** yet claim full ITDR, continuous external ASM, automated compliance certification readiness, or managed deception without new workstreams.

---

## 2. Detailed Breakdown of Existing Features (What Is Working Today)

### 2.1 Control plane (VM 100 — system of record)

| Component | Evidence | Status |
|-----------|----------|--------|
| FastAPI backend (`backend-api/`) | `app/main.py` includes auth, admin, customer, EDR, SOC sync, vuln, entitlements, appliances, audit | **Live** |
| PostgreSQL | `postgres/init/001_mssp_core_schema.sql` + additive migrations (entitlements, vulns, EDR, assets, install tokens, …) | **Live** |
| Redis | Compose service; used for health (queue/workers still limited) | **Live (underused as job bus)** |
| Admin portal `:3000` | Tenants, users, alerts, incidents, assets, appliances, vulns, recommendations, reports, audit, notifications, dashboard | **Live (nginx build)** |
| Customer portal `:3001` | Dashboard, alerts/incidents (safe), assets/appliances, recommendations, reports, services/entitlements, vulns request UX, users, account, audit (tenant-scoped) | **Live (nginx build)** |
| Tenant isolation | Customer wrong-tenant → **404**; parameterized SQL; `customer_safe_labels.py` strips engine brands | **Working by design** |

### 2.2 Detection & response engines (adapters, not customer UIs)

| Engine | VM / role | Control-plane wiring | Status |
|--------|-----------|----------------------|--------|
| **Wazuh** Manager/Indexer | VM 101 (`192.168.0.211`) | Instant ingress + SOC sync → `security_alerts` / incidents; agent groups; AR for EDR | **Live** |
| **Suricata** | VM 106 | Via Wazuh agent / network path; taxonomy labels as network monitoring | **Live** |
| **TheHive** | VM 102 | Case sync (`soc_sync`); default org `MSSP` | **Live** |
| **Shuffle** | VM 102 | Webhooks from Wazuh ingress / EDR workflows | **Live** |
| **Nuclei + Vuls** | VM 109 `/opt/mssp-vuln-free` | `vuln_sync`, scan-plan agent, Admin promote → recommendations | **Live (primary free vuln stack)** |
| **Greenbone CE** | VM 109 | Adapter + instant puller (KB-068–070); Enterprise deferred (KB-077) | **Live (backup/classic path)** |
| **Zeek** | Roadmap | Entitlement flag `zeek_enabled` / customer “network traffic analysis” | **Not live** |
| **MISP** | Roadmap | Entitlement flag; threat-intel label mapping exists | **Not live** |
| **Velociraptor** | Roadmap | Entitlement flag; forensics label mapping exists | **Not live** |

### 2.3 Product capabilities already productized

1. **Multi-tenant onboarding** — deployment modes (cloud / on-prem / hybrid), entitlements CRUD, engine bindings, contract-ready create (KB-072–075).  
2. **SOC triage** — alerts/incidents, taxonomy, enrichment, customer-visible promotion, recommendations/notifications.  
3. **Customer-safe MDR portal** — no raw engine JSON/IPs/credentials; capability language only.  
4. **Vulnerability program** — scan → normalize (`nuclei`/`vuls`/`greenbone`) → Admin triage → customer recommendations; cadence + upgrade requests.  
5. **Co-managed EDR / MXDR (KB-083/084/091)** — isolate / unisolate / kill / block-hash / forensics model; Windows quarantine AR with `applied`/`released` callbacks; process-tree / telemetry schema.  
6. **Appliance & agent paths** — registration/heartbeat, agent install packages/tokens, network appliance ingest.  
7. **Ops documentation** — Ops Bible v5, KB-036 roadmap, containment honesty (KB-091).

### 2.4 Explicit non-goals already enforced in code/docs

- Customers never get Wazuh / Greenbone / TheHive / Shuffle logins.  
- Scanners do **not** run on the control plane (VM 100).  
- Fail-closed tenant mapping for Wazuh (no DEMO default).

---

## 3. Identified Feature & Tool Gaps (by Market Dimension)

### Dimension 1 — Cloud & Identity Threat Detection (ITDR / M365)

#### What exists today

- Tenant **deployment mode** can be labeled `cloud` with provider enum `aws` | `azure` | `gcp` | `other` (Admin Tenants UI + schemas) — **metadata only**, not log connectors.  
- Alert taxonomy strings mention “azure ad”, “entra”, “okta” as **classification keywords** if such text appears in already-ingested alerts (`soc_alert_taxonomy.py`) — **not** an identity pipeline.  
- `customer_safe_labels.py` has **no** M365 / Entra / CloudTrail source mappings.  
- **No** matches in repo for Office 365 wodles, Microsoft Graph audit, Azure Activity, AWS CloudTrail, or GCP Logging adapters in `backend-api` or Wazuh templates audited.

#### Gaps

| Layer | Missing |
|-------|---------|
| **Ingest** | Connectors for Entra ID / M365 unified audit, Exchange/SharePoint/Teams signals, CloudTrail, GCP Audit Logs; Wazuh cloud modules or equivalent sidecar |
| **Normalize** | `source_platform` values + schemas for identity events (user, session, app consent, mailbox rule, impossible travel) |
| **Store** | Optional `identity_events` / enriched alert fields (actor UPN, tenant AAD id) with tenant_id |
| **Detect** | ITDR correlation rules (token theft, OAuth consent abuse, privileged role changes) |
| **Admin UI** | Identity alert queues, Entra app consent views |
| **Customer UI** | Identity incidents in plain English; no raw Graph payloads |
| **Entitlements** | `identity_threat_detection_enabled` (or similar) separate from endpoint SIEM |
| **Response** | Account disable / session revoke playbooks (Graph) — distinct from host isolate |

#### Market implication

Without this dimension you cannot honestly compete as an **ITDR / M365 MDR** vendor; you remain **endpoint- and network-centric MDR**.

---

### Dimension 2 — External Attack Surface Management (EASM)

#### What exists today

- Vulnerability path is **estate-scoped**: `config/vuln_scan_targets.yml` lists Nuclei URLs/IPs and optional Vuls SSH hosts (lab example: `http://192.168.0.214`).  
- Scan plan builder pulls **protected assets / entitlements** (`vuln_scan_plan_service.py`) — designed for **known internal (or approved) targets**, not internet-wide discovery.  
- Nuclei (ProjectDiscovery) is installed on VM 109 for **template-based vuln checks**, not as an EASM discovery suite (no Amass/httpx/chaos/asnmap product wiring found).  
- Greenbone CE is classic **network vulnerability scanning**, not continuous external ASM.

#### Gaps

| Layer | Missing |
|-------|---------|
| **Discovery tools** | Subdomain enumeration (e.g. OWASP Amass / ProjectDiscovery), DNS/HTTP probing (httpx), port/service map for **public** ranges only |
| **Data model** | `external_assets` / `attack_surface_findings` (domain, subdomain, IP, cert, tech fingerprint, first/last seen) per `tenant_id` |
| **Scheduling** | Customer-approved **domain allowlist** + cadence; legal scope gate (already hinted in vuln config comments) |
| **APIs** | Admin CRUD for monitored domains; customer read-only surface map; promote findings → recommendations |
| **UI** | Customer “External exposure” page; Admin triage for new internet-facing services |
| **SOAR** | Shuffle playbook: new critical exposure → case + notify |

#### Market implication

Current vuln stack ≈ **VM/vuln management on known assets**. EASM is a **different product** (discover unknown internet exposure continuously).

---

### Dimension 3 — Automated Compliance & Hardening (CaaS)

#### What exists today

- **Reactive** security: alerts, incidents, recommendations, monthly reports, audit logs.  
- Customer vulnerability page collects **compliance_drivers** (ISO 27001, PCI DSS, etc.) on **upgrade requests** — intake preferences, **not** scored controls.  
- Wazuh **SCA / CIS Benchmark** results are **not** modeled in control-plane schemas (no `sca_*` / `compliance_controls` tables in `postgres/init/`).  
- No Customer Portal “Compliance Readiness Scorecard” page or Admin control-mapping UI found.  
- Prior stack audit notes **SOC2 / ISO mapping** as partial via `audit_logs` only.

#### Gaps

| Layer | Missing |
|-------|---------|
| **Collection** | Wazuh SCA (or OpenSCAP/osquery) ingest → normalized findings per asset/tenant |
| **Mapping** | Control matrix: CIS / ISO 27001 / PCI-DSS / NIST CSF ←→ technical checks |
| **Scoring** | Per-tenant readiness %, trend, exception/waiver workflow |
| **DB** | `compliance_frameworks`, `compliance_controls`, `compliance_assessments`, `compliance_findings` |
| **Admin UI** | Framework coverage, failed controls, assign remediation → recommendations |
| **Customer UI** | Executive scorecard + plain-English gaps (no raw CIS XML) |
| **Evidence** | Export packs for auditors (retain vs customer-safe views) |

#### Market implication

You can support **compliance conversations** via vulns/recommendations/reports, but you cannot sell **Automated Compliance / Hardening as a Service** until SCA→scorecard exists.

---

### Dimension 4 — Managed Deception & Threat Hunting (Canary / Honeypots)

#### What exists today

- High-fidelity **endpoint** signals via Sysmon/process trees and **network** via Suricata.  
- Containment: isolate host / kill process (Windows AR pack matured in KB-091).  
- **Zero** repository matches for canarytokens, honeypot, deception, honey-token, Thinkst, etc.  
- No dedicated deception webhook route beside generic SOC sync / appliance ingest.  
- No Shuffle playbook artifacts in-repo for deception → isolate/lockout.

#### Gaps

| Layer | Missing |
|-------|---------|
| **Sensors** | Canarytokens / fake shares / fake AD creds / decoy documents / low-interaction honeypots |
| **Ingest** | Signed webhook `POST /integrations/deception/events` (tenant-mapped, fail-closed) |
| **Normalize** | Alert class `deception_trigger` with max severity / auto-promote policy |
| **SOAR** | Shuffle: deception hit → TheHive case → optional isolate / disable account / notify |
| **Hunting UI** | Admin “deception events” + timeline; Customer: rare, highly summarized “tamper attempt” notices only |
| **Entitlement** | `deception_enabled` / hunt hours SKU |
| **Safety** | Strict allowlists so deception never false-triggers production isolate without policy |

#### Market implication

Deception is a **net-new** product line. You have the **response hooks** (isolate, cases) but not the **bait + ingest** layer.

---

### Cross-cutting gaps (affect all four dimensions)

From this audit + `STACK_AUDIT_MARKET_READINESS_REPORT.md` (still largely applicable):

- Redis not yet a durable job queue for async connectors.  
- MFA/SSO absent (email/password JWT).  
- HA/cloud multi-AZ not productized.  
- Per-execution EDR callback tokens still Wave-2 (shared key model).  
- Zeek / MISP / Velociraptor remain roadmap despite entitlement fields.

---

## 4. Architectural Effort Matrix

Effort = build + wire + tenant-safe UI + validation (not just install a tool).

| Gap / initiative | Effort | Why |
|------------------|--------|-----|
| **D1 — M365 / Entra audit ingest → alerts** | **High** | New connectors, secrets, Graph/API quotas, identity schemas, detection content, customer-safe copy |
| **D1 — CloudTrail / GCP audit (multi-cloud ITDR)** | **High** | Per-cloud auth models + normalization; multiplies ops |
| **D1 — Identity response (revoke session / disable user)** | **Medium–High** | Graph actions + strong approval/audit; dangerous if wrong tenant |
| **D2 — Nuclei-only external URL scanning (approved domains)** | **Low–Medium** | Extends existing VM 109 + vuln sync; scope/legal gates mandatory |
| **D2 — Full EASM (Amass/httpx + inventory UI)** | **High** | New asset universe, discovery noise, ownership UX, continuous scheduling |
| **D3 — Wazuh SCA ingest → findings table** | **Medium** | Wazuh already can produce SCA; need adapter + schema + Admin list |
| **D3 — Customer compliance scorecard (CIS/ISO/PCI mapping)** | **High** | Control library, scoring, waivers, executive UX, evidence exports |
| **D4 — Canarytokens webhook → alert/incident** | **Medium** | Thin ingest + taxonomy + promote; reuse SOC sync patterns |
| **D4 — Auto-isolate / account lock on deception** | **Medium–High** | Policy engine + false-positive risk; reuse EDR/Shuffle |
| **Enable Zeek live (entitlement already exists)** | **Medium** | Sensor deploy + ingest (KB roadmap); not ITDR/EASM by itself |
| **Enable MISP enrichment** | **Medium** | KB-050/051 planned; helps hunting, not deception |
| **Velociraptor DFIR** | **High** | New VM + evidence safety (KB-054/055) |

**Legend:** Low ≈ days–1 sprint with existing patterns · Medium ≈ 1–3 sprints · High ≈ multi-sprint / dedicated KB sequence.

---

## 5. Recommended Execution Roadmap for Next Steps

Do **not** start coding until you pick a dimension and approve a named KB. Suggested order balances **market pull** vs **reuse of existing adapters**.

### Phase A — Decide the commercial wedge (this week)

1. Pick **one** primary sell-through for the next quarter:  
   - **A1 ITDR/M365**, or  
   - **A2 External exposure (pragmatic)**, or  
   - **A3 Compliance scorecard**, or  
   - **A4 Deception MVP**.  
2. Keep Level-3 MDR/EDR/vuln as the **cashflow baseline**; do not pause Windows EDR honesty / ops hardening entirely.

### Phase B — Fastest credible increments (recommended sequence)

| Order | Initiative | Rationale |
|------:|------------|-----------|
| **1** | **Pragmatic external exposure (approved domains → Nuclei on VM 109 + Admin/Customer surface)** | Lowest effort toward “EASM-lite”; reuses vuln pipeline; clear legal scope |
| **2** | **Deception webhook MVP → high-severity alert + TheHive case** (isolate optional, policy-gated) | Differentiator; reuses SOC sync + Shuffle + isolate |
| **3** | **Wazuh SCA → compliance findings + Admin view** | Foundation for CaaS before full ISO scorecard |
| **4** | **M365 / Entra audit connector (ITDR Phase 1)** | Highest market demand; highest complexity — start after connector patterns proven on (1)–(2) |
| **5** | **Customer Compliance Scorecard v1** | Depends on (3) + control mapping content pack |
| **6** | Full EASM discovery suite + Zeek/MISP/Velociraptor as capacity allows | Scale/depth after wedge proven |

### Phase C — Guardrails for every new dimension

- New customer fields must go through `customer_safe_labels` / capability language.  
- Fail-closed tenant mapping on every new ingest key.  
- Named KB + validation script before commit/tag.  
- No scanner or Graph secrets on VM 100 beyond adapter config.  
- Update Ops Bible + entitlements catalog when a SKU becomes sellable.

### Phase D — What not to do next

- Do not claim Level 4/5 in sales decks until at least one of D1–D4 is **live and validated**.  
- Do not bolt Amass/Graph onto the control plane without a tenant-scoped data model.  
- Do not auto-isolate on every deception/ITDR hit without SOC policy + audit (false positives destroy trust).

---

## Appendix A — Evidence index (audit anchors)

| Area | Paths / artifacts |
|------|-------------------|
| Routes | `backend-api/app/main.py`, `api/routes/*.py` (edr, soc_sync, vuln_*, entitlements, customer, admin_*) |
| Labels | `backend-api/app/services/customer_safe_labels.py` |
| Schemas | `postgres/init/001_*.sql`, `004_kb069_vulnerabilities.sql`, `005_kb071_tenant_entitlements.sql`, `014`/`015` EDR |
| Vuln targets | `config/vuln_scan_targets.yml`, `docs/KB078_*.md`, `docs/KB079_*.md` |
| EDR / containment | `deploy/wazuh-active-response/windows/`, `docs/KB083_*.md`, `docs/KB091_*.md` |
| Frontends | `frontend-admin/src/pages/*`, `frontend-customer/src/pages/*` |
| Context | `CONTEXT.md`, `docs/MSSP_PLATFORM_MASTER_BLUEPRINT.md`, `docs/KB036_*.md` |
| Prior readiness | `docs/STACK_AUDIT_MARKET_READINESS_REPORT.md` |

## Appendix B — Maturity scorecard snapshot

| Dimension | Maturity today | Target for Level 4 |
|-----------|----------------|--------------------|
| Endpoint / NIDS MDR | **Strong (L3)** | Maintain |
| Co-managed EDR response | **Strong (L3)** | Per-exec tokens, Linux+Windows parity ops |
| Vuln management | **Moderate–Strong** | Broader asset coverage + Enterprise option |
| ITDR / M365 | **Absent** | Entra/M365 ingest + identity IR |
| EASM | **Absent** (known-target Nuclei only) | Discovery + continuous external inventory |
| Compliance CaaS | **Absent** (preferences only) | SCA + scorecard |
| Deception / hunt | **Absent** | Webhook + SOAR + optional auto-contain |
| Cloud IT (AWS/GCP logs) | **Absent** | After or with ITDR |

---

*End of report. Next step: choose Phase B initiative #1–4 and open a planning-only KB before implementation.*
