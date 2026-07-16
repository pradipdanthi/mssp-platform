# KB-049 — Wazuh to Shuffle to TheHive Workflow

Status: Implemented (pending validation/commit).  
Branch: `kb039-kb060-platform-roadmap-execution`  
Module type: **Planning / documentation only** — no runtime code, schema, compose, or `.env` changes.

Builds on: `docs/KB036_MSSP_PLATFORM_ARCHITECTURE_ROADMAP.md`, **KB-040/041** (Wazuh stack), `docs/KB047_THEHIVE_DEPLOYMENT_PLAN.md`, `docs/KB048_SHUFFLE_SOAR_DEPLOYMENT_PLAN.md`, and network detection KBs **KB-044/046**.

---

## 1. Purpose

Define the **reference SOC workflow** that routes **Wazuh alerts** (and optionally Suricata/Zeek-derived Wazuh alerts) through **Shuffle playbooks** on VM 103 to create or update **TheHive cases** on VM 102 — with tenant scoping, deduplication rules, and customer-safe projections back to MSSP Control Plane.

This KB is **planning only**. Webhooks, playbooks, and adapters are **future implementation KBs**.

---

## 2. Current baseline

| Area | Status |
|---|---|
| Wazuh → Shuffle trigger | **Not configured** |
| Shuffle → TheHive case API | **Not configured** |
| TheHive → Control Plane sync | **Not implemented** — KB-057 |
| Tenant tagging on cases | Design only |
| Customer portal | Incident summaries (KB-025) — no workflow internals |

---

## 3. Architecture

### 3.1 End-to-end reference flow

```
┌─────────────────────────────────────────────────────────────────┐
│ Detection layer (VM 101 + sensors 106/107 via KB-044/046)       │
│   Wazuh rules fire → alert with level, rule id, agent metadata  │
└────────────────────────────┬────────────────────────────────────┘
                             │ webhook / API / integration
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│ Shuffle SOAR (VM 103) — KB-048                                  │
│   1. Receive alert payload                                      │
│   2. Resolve tenant_id (agent group / lookup)                   │
│   3. Deduplicate (open case? same rule+agent?)                │
│   4. Enrich (optional — MISP later KB-051)                      │
│   5. Create or update TheHive case                              │
└────────────────────────────┬────────────────────────────────────┘
                             │ TheHive API
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│ TheHive (VM 102) — KB-047                                       │
│   Case with tenant tag, title, severity, observables (SOC)      │
└────────────────────────────┬────────────────────────────────────┘
                             │ future adapter
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│ MSSP Control Plane (VM 100) — KB-057                          │
│   incidents table: tenant-scoped customer-safe summary            │
└────────────────────────────┬────────────────────────────────────┘
                             ▼
                    Customer portal (KB-025) — no raw logs
```

### 3.2 Trigger options from Wazuh (planning)

| Method | Description |
|---|---|
| **Integration webhook** | Wazuh integration forwards alerts to Shuffle HTTP endpoint |
| **Shuffle polling** | Shuffle workflow polls Wazuh API on interval — higher latency |
| **Indexer-driven** | Defer — prefer manager-side integration for lab v1 |

**Recommended for lab v1:** Wazuh integration webhook → Shuffle public webhook URL (internal network only).

### 3.3 Playbook stages (reference design)

| Stage | Action |
|---|---|
| **Ingress** | Validate payload schema; reject malformed alerts safely (log server-side) |
| **Tenant resolve** | Map agent/group to `tenant_id` — fail closed if unknown |
| **Severity filter** | e.g. only level ≥ 10 opens new case; lower levels → notification only |
| **Dedup** | Search TheHive for open case with same tenant + rule + agent within window |
| **Case create** | POST TheHive case with tenant custom field, title template, tags |
| **Observables** | Add IOCs for SOC — **not** synced raw to customer API |
| **Control plane hook** | Future: notify MSSP adapter to upsert `incidents` row (KB-057) |

### 3.4 Suricata / Zeek alerts in same workflow

Alerts that reached Wazuh via KB-044/046 use the **same Shuffle ingress** — playbook branches on `rule.groups` or `data.source` to set case category (network vs endpoint).

---

## 4. VM references

| VM | Name | Role in workflow |
|---|---|---|
| **VM 101** | `wazuh-stack` | Alert origin |
| **VM 103** | `shuffle` | Orchestration |
| **VM 102** | `thehive` | Case system of record (SOC) |
| **VM 100** | `mssp-control` | Customer-visible incident summaries |
| **VM 106/107** | network sensors | Indirect — alerts via Wazuh integration |

---

## 5. Tenant isolation

- **Every automated case** must include tenant context before TheHive create.
- Unknown tenant mapping → playbook **does not** create a case; logs error for SOC review.
- MSSP adapter (KB-057) enforces `tenant_id` on all `incidents` rows synced from TheHive.
- Customer APIs: tenant filter on incident number/ID — cross-tenant → **404**.
- Playbook debug logs with full alert JSON: **SOC infrastructure only**.

---

## 6. Customer portal safety

Customer portal must **never** expose:

- Raw Wazuh alert JSON, Suricata `eve.json`, or Zeek logs from workflow
- Shuffle execution history, webhook secrets, or playbook source
- TheHive observables, task lists, or analyst-only fields
- Internal case UUIDs unless mapped to customer-safe `incident_number`

Customers see: status, plain-English summary, business impact, actions — per KB-025.

**No secrets** in Git, docs, or customer API responses.

---

## 7. Relationship to prior KBs

| KB | Relationship |
|---|---|
| **KB-036** | Cloud model data flow — Shuffle + TheHive in path |
| **KB-037/038** | Tenant and cluster context for alert→tenant mapping |
| **KB-040/041** | Wazuh stack prerequisite |
| **KB-044** | Suricata alerts ingested by Wazuh — same workflow |
| **KB-046** | Zeek notices ingested by Wazuh — same workflow |
| **KB-047** | TheHive deployment and case API |
| **KB-048** | Shuffle deployment and webhook surface |
| **KB-025** | Customer incident detail UI |
| **KB-057** | Normalize case → `incidents` for customer portal |

---

## 8. Explicit deferrals

| Item | Deferred to |
|---|---|
| Wazuh integration module config | KB-049 implementation KB |
| Shuffle playbook import/versioning | KB-049 implementation KB |
| TheHive case templates | KB-049 implementation KB |
| Bidirectional case status sync | KB-057 |
| MISP enrichment in playbook | KB-051 |
| Customer WhatsApp/email from workflow | Future notification KB |
| On-prem appliance alert path | KB-058 |

---

## 9. Decision summary (approved defaults)

| # | Decision | Choice |
|---|---|---|
| D1 | Alert path | Wazuh webhook → Shuffle → TheHive API |
| D2 | Tenant mapping | Required before case create — fail closed if missing |
| D3 | Dedup | Same tenant + rule + agent within time window |
| D4 | Customer data | Control plane normalized summaries only — **no raw logs** |
| D5 | Secrets | Webhook/API keys in env — **no secrets** in Git or docs |

---

## 10. What KB-049 changes (and must not)

### Changes

- `docs/KB049_WAZUH_SHUFFLE_THEHIVE_WORKFLOW.md` (this file)
- `scripts/kb049_validate_wazuh_shuffle_thehive_workflow.sh`

### Must not change

- `backend-api/`, `frontend-customer/`, `frontend-admin/`
- `postgres/init/`, `docker-compose.yml`, `.env`

---

## 11. Validation

```bash
cd /opt/mssp-control
chmod +x scripts/kb049_validate_wazuh_shuffle_thehive_workflow.sh
./scripts/kb049_validate_wazuh_shuffle_thehive_workflow.sh
```

Expected final line:

```text
KB-049 WAZUH SHUFFLE THEHIVE WORKFLOW VALIDATION PASSED
```
