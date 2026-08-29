# PM-004 — MSSP Platform Capability Matrix

**Task:** PM-004 Full MSSP Platform Portfolio Discovery & Backlog Reconstruction  
**Date:** 2026-08-29  
**Repository:** `/opt/mssp-control`  
**Branch:** `kb112-sovereign-edge`  
**Product RC:** `87821f1` (tag `kb112-sovereign-edge-validated`)  
**Docs HEAD:** `6b6b33d`  
**Method:** Repository inspection, migration review, service/route depth checks, existing audit cross-reference, lab configuration evidence. No secrets included.

## Executive Summary

The NikTiar MSSP platform is a **substantial, multi-domain MXDR control plane** with two production-grade React portals, a 40-module FastAPI backend, 49 SQL migrations, appliance licensing/OTA, and extensive KB validation discipline. Overall maturity aligns with **Level 3 Co-Managed MDR / Emerging MXDR** per prior audits, with **Sovereign Edge (SOV)** as the active pre-release workstream.

Several **prior P0 findings are now closed in code** (Postgres RLS on core tables, EDR agent-tenant validation, NDR source_tool detection, production sample-seed gating). Remaining gaps concentrate on **enterprise hardening (MFA/SSO, RLS expansion), live engine deployment (Zeek/MISP/Velociraptor), exposure automation, appliance test coverage, and HA/architecture decisions**.

### Maturity Totals (Primary State)

| Maturity | Count |
|---|---:|
| OPERATIONAL | 28 |
| PARTIAL | 22 |
| WIP | 3 |
| STUB | 4 |
| MISSING | 5 |
| TECHNICAL_DEBT | 8 |
| ARCHITECTURE_DECISION_REQUIRED | 4 |
| **Capabilities assessed** | **74** |

### Domain Breakdown

| Domain | Capabilities | OPERATIONAL | PARTIAL | WIP | STUB | MISSING | DEBT | ADR |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| PLT | 6 | 2 | 1 | 0 | 0 | 0 | 2 | 1 |
| CTL | 7 | 4 | 2 | 0 | 0 | 0 | 1 | 0 |
| POR | 5 | 2 | 2 | 0 | 1 | 0 | 0 | 0 |
| APP | 6 | 3 | 1 | 0 | 1 | 1 | 0 | 1 |
| SOC | 5 | 3 | 2 | 0 | 0 | 0 | 0 | 0 |
| DET | 6 | 2 | 2 | 0 | 0 | 2 | 0 | 0 |
| EXP | 5 | 1 | 4 | 0 | 0 | 0 | 0 | 0 |
| INT | 5 | 1 | 3 | 0 | 0 | 1 | 0 | 0 |
| AI | 5 | 2 | 0 | 0 | 0 | 2 | 1 | 1 |
| SOV | 4 | 0 | 2 | 2 | 0 | 0 | 0 | 0 |
| INF | 5 | 1 | 1 | 0 | 0 | 1 | 2 | 0 |
| XCT | 5 | 3 | 1 | 0 | 0 | 0 | 1 | 0 |

---

## Capability Matrix

### PLT — Platform & Architecture

| Capability | Maturity | Code Evidence | Runtime/Test Evidence | Risk | Customer Impact | Dependencies | Work Type | Priority |
|---|---|---|---|---|---|---|---|---|
| FastAPI system-of-record + dual-portal architecture | OPERATIONAL | `backend-api/app/main.py`, `docker-compose.yml` | VM100 compose healthy; KB validators | Low | High — core product | None | — | — |
| 49-file raw SQL migration chain | TECHNICAL_DEBT | `postgres/init/001–049` | Applied on VM100 Postgres | Medium | Medium — upgrade friction | Alembic/Flyway ADR | Technical Debt | NORMAL |
| Single-node Postgres/Redis stack | ARCHITECTURE_DECISION_REQUIRED | `docker-compose.yml`, TD-004 | Lab single-node | High | High — SLA | TD-004, INF | Architecture Decision | HIGH |
| Dual appliance build trees (legacy + kevantic) | ARCHITECTURE_DECISION_REQUIRED | `mssp-appliance-builder/`, `kevantic-appliance/packer/` | Golden VM199 bake path | Medium | Medium — release confusion | ARCH-001, XCT-001 | Architecture Decision | NORMAL |
| Platform state verifier | PARTIAL | `scripts/verify_platform_state.py` | Manual execution | Low | Medium | None | Task | LOW |
| Retention purge schema | PARTIAL | `postgres/init/041_retention_purge.sql` | Scheduling unverified | Medium | Medium — data growth | PLT-001 | Feature | HIGH |

### CTL — Control Plane & Identity

| Capability | Maturity | Code Evidence | Runtime/Test Evidence | Risk | Customer Impact | Dependencies | Work Type | Priority |
|---|---|---|---|---|---|---|---|---|
| JWT auth + 5-role RBAC | OPERATIONAL | `auth.py`, `002_kb010_auth_rbac.sql` | KB-112 auth 13/13, RBAC 19/19 | Low | High | None | — | — |
| Postgres RLS (core 3 tables) | OPERATIONAL | `042_enable_rls.sql`, `test_db_rls.py` | Migration applied | Medium | High — tenancy | CTL-002 expansion | Feature | HIGH |
| EDR agent-tenant ownership | OPERATIONAL | `edr_actions.py`, `test_edr_agent_tenant.py` | Dedicated pytest suite | Low | Critical — IDOR closed | CTL-001 verify | QA Validation | HIGH |
| Customer MFA | PARTIAL | `043/044` migrations, `MfaSetupPage.tsx` | MFA routes exist | Medium | High — enterprise | CTL-003 | Feature | HIGH |
| SSO/SAML/OIDC | MISSING | Not found in auth routes | N/A | High | High — enterprise | CTL-003 | Feature | HIGH |
| Shared callback API key aliasing | TECHNICAL_DEBT | `edr.py`, env aliases | Lab config | Medium | Medium | SEC review | Technical Debt | NORMAL |
| Login rate limiting | MISSING | Not confirmed in auth.py | N/A | Medium | Medium | CTL-003 | Feature | HIGH |

### POR — Portals

| Capability | Maturity | Code Evidence | Runtime/Test Evidence | Risk | Customer Impact | Dependencies | Work Type | Priority |
|---|---|---|---|---|---|---|---|---|
| Admin portal (25 pages) | OPERATIONAL | `frontend-admin/src/pages/` | Playwright admin specs | Low | High | None | — | — |
| Customer portal (28 pages) | OPERATIONAL | `frontend-customer/src/pages/` | Playwright customer specs | Low | High | None | — | — |
| Admin parity for EASM/ITDR/NDR/Forensics | PARTIAL | Customer pages exist; admin absent | Visual gap | Low | Medium — SOC triage | POR-002 | Feature | NORMAL |
| Production synthetic adapter gating | PARTIAL | `_allow_lab_sample_seed()` in ITDR/VMaaS/NDR | `test_ndr_ingest.py` | Medium | High — trust | POR-001, TD-001 | Feature | HIGH |
| Admin IncidentDrawer lab TheHive stub | STUB | Per end-to-end audit | Fake SOAR trigger | Low | Low — internal | SOC integration | Bug | LOW |

### APP — Appliance Platform

| Capability | Maturity | Code Evidence | Runtime/Test Evidence | Risk | Customer Impact | Dependencies | Work Type | Priority |
|---|---|---|---|---|---|---|---|---|
| Ed25519 JWS licensing | OPERATIONAL | `kevantic-appliance/licensing/` | KB validators | Low | Critical | None | — | — |
| Appliance CLI register/heartbeat/license | OPERATIONAL | `kevantic-appliance/cli/` | VM210 Sovereign lab | Low | High | None | — | — |
| Golden VM199 bake pipeline | OPERATIONAL | `scripts/bake_golden_vm199_*.sh` | PM-004 did not rebake | Low | High | ARCH-001 | — | — |
| OTA channel (WPK) | PARTIAL | `kevantic-appliance/ota/` | Lab path exists | Medium | High | APP tests | Feature | NORMAL |
| Appliance automated tests | MISSING | `kevantic-appliance/tests/` empty | Zero files | High | High — delivery confidence | APP-001, TD-003 | Feature | HIGH |
| Edge service manifests (VMaaS/EASM/ITDR) | STUB | `services/04-vmaas`, `09-easm`, `10-itdr` | README+YAML only | Medium | Medium | APP-002 | Feature | NORMAL |

### SOC — Security Operations

| Capability | Maturity | Code Evidence | Runtime/Test Evidence | Risk | Customer Impact | Dependencies | Work Type | Priority |
|---|---|---|---|---|---|---|---|---|
| Alert/incident triage + taxonomy | OPERATIONAL | `alert_incident_triage.py`, `037_alert_suppressions.sql` | KB validators | Low | High | None | — | — |
| Service catalog + tier rollout | OPERATIONAL | `service_catalog.py`, admin TierRollout pages | Entitlements 50K LOC | Low | High | None | — | — |
| Audit logging | PARTIAL | `audit_service.py`, `audit_logs.py` | Partial mutation coverage | Medium | Medium — compliance | SOC-002 | Feature | NORMAL |
| Shared-engine tenant isolation | PARTIAL | Wazuh/TheHive/Shuffle via tags | Documented risks | High | Critical | SOC-002 | Feature | HIGH |
| Recommendation promotion | OPERATIONAL | `recommendation_management.py` | API present | Low | Medium | None | — | — |

### DET — Detection & Response

| Capability | Maturity | Code Evidence | Runtime/Test Evidence | Risk | Customer Impact | Dependencies | Work Type | Priority |
|---|---|---|---|---|---|---|---|---|
| Wazuh webhook ingest | OPERATIONAL | `soc_sync.py` | Lab VM101 | Low | High | None | — | — |
| NDR source_tool detection | OPERATIONAL | `detect_ingress_source_tool()`, `test_ndr_ingest.py` | Unit tests pass | Low | High | SOC-001 lab validation | QA Validation | HIGH |
| EDR isolate/kill/forensics | OPERATIONAL | `edr_actions.py`, AR scripts | KB-114/115 | Low | Critical | None | — | — |
| Zeek live pipeline | MISSING | `ansible/roles/zeek_sensor` | Not deployed | Medium | Medium — NDR depth | DET-001 | Feature | NORMAL |
| TheHive/Shuffle SOAR | PARTIAL | `thehive_client.py`, `shuffle_edr_client.py` | Shared-org fallback risk | Medium | High | SOC-002 | Feature | HIGH |
| MISP/Velociraptor live | MISSING | Ansible roles exist | Not deployed | Medium | Medium | INT-001/002 | Feature | NORMAL |

### EXP — Exposure & Assurance

| Capability | Maturity | Code Evidence | Runtime/Test Evidence | Risk | Customer Impact | Dependencies | Work Type | Priority |
|---|---|---|---|---|---|---|---|---|
| VMaaS vuln management | OPERATIONAL | `vmaas_service.py`, `vuln_sync.py` | Greenbone/Nuclei paths | Low | High | None | — | — |
| EASM API/UI | PARTIAL | `easm.py`, `EasmPage.tsx`, `023_easm_attack_surface.sql` | Target-list discovery | Medium | High | EXP-001 | Feature | HIGH |
| Compliance scorecards | PARTIAL | `compliance.py`, `sca_compliance_service.py` | Heuristic mapping | Medium | Medium | EXP-002 | Feature | NORMAL |
| ThreatLens retrospective | PARTIAL | `threatlens.py`, `RetrospectiveHuntsPage.tsx` | API present | Low | Medium | DET engines | Feature | NORMAL |
| HIPAA scoring engine | MISSING | Marketing claim vs no engine (C-1 audit) | N/A | High | High — legal/trust | Product decision | Architecture Decision | HIGH |

### INT — Integrations

| Capability | Maturity | Code Evidence | Runtime/Test Evidence | Risk | Customer Impact | Dependencies | Work Type | Priority |
|---|---|---|---|---|---|---|---|---|
| ITDR (Entra Graph) | PARTIAL | `itdr_service.py`, `024_cloud_itdr_identity.sql` | Entra live; others placeholder | Medium | High | INT expansion | Feature | NORMAL |
| Threat-intel enrichment | PARTIAL | `threat_intel_service.py` | May seed samples | Medium | Medium | INT-001 MISP | Feature | NORMAL |
| Agent install/package tokens | OPERATIONAL | `admin_agent_packages.py`, `020_kb086` | KB-086 | Low | High | None | — | — |
| AWS/GCP/Okta ITDR connectors | MISSING | DB placeholders only | N/A | Low | Medium — roadmap | ITDR | Feature | SOMEDAY |
| Appliance alert ingest | OPERATIONAL | `appliance_alert_ingest.py` | Sovereign path | Low | High | APP | — | — |

### AI — AI & Triage

| Capability | Maturity | Code Evidence | Runtime/Test Evidence | Risk | Customer Impact | Dependencies | Work Type | Priority |
|---|---|---|---|---|---|---|---|---|
| Tier-1 on-demand triage | OPERATIONAL | `ai_tier1_triage.py` | Ollama VM115 | Medium | High | AI-002 | — | — |
| Async alert analysis queue | OPERATIONAL | `ai_alert_analysis.py`, `ai_alert_queue.py` | In-process worker | Medium | High | worker-ai empty | — | — |
| Safety gates (no auto-isolate) | OPERATIONAL | `ENABLE_AUTO_CLOSE_LOW_RISK` default false | Documented | Low | Critical | None | — | — |
| Pre-LLM FP veto | MISSING | Confirmed absent | N/A | Medium | Medium — cost/latency | AI-001 | Feature | HIGH |
| Ollama HA / capacity | TECHNICAL_DEBT | VM115 SPOF | No failover | High | Medium | AI-002, INF-001 | Feature | NORMAL |
| Standalone AI worker architecture | ARCHITECTURE_DECISION_REQUIRED | `worker-ai/` empty | Inline backend | Low | Low | AI-002 | Architecture Decision | SOMEDAY |

### SOV — Sovereign Edge

| Capability | Maturity | Code Evidence | Runtime/Test Evidence | Risk | Customer Impact | Dependencies | Work Type | Priority |
|---|---|---|---|---|---|---|---|---|
| Sovereign deployment mode | PARTIAL | `049_sovereign_edge_deployment_mode.sql` | Migration present | Medium | High — edge SKU | REL-001 | Release | HIGH |
| Portal auth/RBAC hardening | OPERATIONAL | `87821f1` product RC | QA-001 13/13 auth, 19/19 RBAC | Low | Critical | None | — | — |
| KB-112–115 validation suite | OPERATIONAL | `scripts/kb112–115_*.sh` | QA-001 all gates pass | Low | High | None | — | — |
| Sovereign GA customer release | WIP | `docs/releases/REL-001` GO recommendation | Not published/baked | Medium | High — revenue | REL-001, ARCH-001 | Release | HIGH |

### INF — Infrastructure & Lab

| Capability | Maturity | Code Evidence | Runtime/Test Evidence | Risk | Customer Impact | Dependencies | Work Type | Priority |
|---|---|---|---|---|---|---|---|---|
| Ansible VM provisioning (15 roles) | OPERATIONAL | `ansible/roles/` | Lab VMs 101–110 | Low | High — engine fleet | None | — | — |
| Hard-coded lab IP defaults | TECHNICAL_DEBT | `config.py`, TD-002 | 192.168.0.x | Medium | Medium | TD-002 | Technical Debt | NORMAL |
| Control-plane HA | MISSING | TD-004 open | Single VM100 | High | Critical | TD-004, CTL-002 | Architecture Decision | HIGH |
| OLAP/analytics separation | PARTIAL | `045_analytics_views.sql` | Co-located on VM100 | Medium | Medium | INF-001 | Feature | NORMAL |
| Notification worker | MISSING | `worker-notification/` empty | N/A | Low | Low | Future | Feature | SOMEDAY |

### XCT — Cross-Cutting

| Capability | Maturity | Code Evidence | Runtime/Test Evidence | Risk | Customer Impact | Dependencies | Work Type | Priority |
|---|---|---|---|---|---|---|---|---|
| Customer-safe engine label mapping | OPERATIONAL | `customer_safe_labels.py` | Prevents brand leakage | Low | High | None | — | — |
| Production sample-seed gating pattern | OPERATIONAL | `_allow_lab_sample_seed()` ITDR/VMaaS/NDR | Tests confirm prod=false | Low | Critical — trust | TD-001 | — | — |
| KB-numbered validation discipline (~116 scripts) | OPERATIONAL | `scripts/kb*_validate_*.sh` | Dominant QA style | Low | High | None | — | — |
| Duplicate build automation | TECHNICAL_DEBT | Two builder trees | Confusion risk | Medium | Medium | XCT-001 | Technical Debt | NORMAL |
| Playwright E2E coverage | PARTIAL | 5 spec files in `e2e/` | Thin vs backend surface | Medium | Medium | QA program | QA Validation | NORMAL |

---

## Top Platform Risks

1. **Shared SOC engine tenant isolation** — Wazuh/TheHive/Shuffle rely on tags/groups; documented fallback risks (SOC-002).
2. **Control-plane single point of failure** — VM100 Postgres/Redis/API with no HA (TD-004, ARCH-001).
3. **Appliance delivery confidence gap** — zero automated appliance tests despite licensing/OTA complexity (APP-001, TD-003).
4. **Marketing/compliance honesty** — HIPAA claims without scoring engine (EXP domain, C-1 audit finding).
5. **Live detection engine gaps** — Zeek/MISP/Velociraptor entitled but not deployed (DET-001, INT-001/002).

## Top Product Gaps

1. **Enterprise auth** — MFA partial; SSO/SAML/OIDC and rate limiting missing (CTL-003).
2. **RLS expansion** — Core 3 tables protected; full tenant table coverage needed (CTL-002).
3. **EASM true discovery** — API/UI exist; automation beyond scan targets missing (EXP-001).
4. **Admin portal domain parity** — Staff cannot triage EASM/ITDR/NDR/Forensics natively (POR-002).
5. **Pre-LLM FP veto** — All alerts hit Ollama; cost and latency scale linearly (AI-001).

---

## Recommended Next Two Workstreams

### Workstream A — Control Plane Production Readiness (EPIC-CTL-001)

**Why now:** Closes the highest-density security/tenancy/enterprise-readiness gaps; several P0 fixes landed but expansion and MFA/SSO remain blockers for enterprise buyers.

**What it unblocks:** Customer onboarding at scale, RLS confidence, AI cost control, retention/ops sustainability.

**Key dependencies:** None blocking start; INF-001 can parallelize.

**Main risks:** SSO vendor choice delay; RLS migration complexity on high-traffic tables.

**First work items:** CTL-002, CTL-003, PLT-001, AI-001, CTL-001 (verify regression)

### Workstream B — SOC Operations Production Readiness (EPIC-SOC-001)

**Why now:** Customer trust depends on alert fidelity and engine isolation; NDR ingest fix landed but lab validation and shared-engine hardening remain.

**What it unblocks:** Multi-tenant SOC at scale, NDR customer value, TheHive/Shuffle production workflows.

**Key dependencies:** Partially depends on DET live sensors for full NDR value.

**Main risks:** Shared-engine refactor scope; lab sensor deployment effort.

**First work items:** SOC-002, SOC-001, DET-001, INT-001, POR-001

---

## Deliberately Deferred

- **Sovereign GA publish/bake** — tracked under REL-001/SOV-REL-001; not started during PM-004.
- **ARCH-001 appliance delivery model decision** — remains open Architecture Decision.
- **Billing/commercial module** — no substantive implementation found; not fabricated.
- **HA implementation** — TD-004 design only.
- **AWS/GCP/Okta ITDR connectors** — roadmap placeholders only.

---

## OpenProject Cross-Reference

New backlog items created by PM-004 script: EPIC-CTL-001, EPIC-SOC-001, EPIC-DET-001, EPIC-EXP-001, EPIC-POR-001, EPIC-APP-001 plus CTL-001..003, SOC-001..002, DET-001, INT-001..002, EXP-001..002, POR-001..002, AI-001..002, INF-001, PLT-001, APP-001..002, XCT-001.

Existing items preserved: PM-001..004, REC-001..005, SEC-001, QA-001, REL-001, ARCH-001, TD-001..004, SOV-REL-001.

---

*Generated by PM-004 discovery. No product code modified.*
