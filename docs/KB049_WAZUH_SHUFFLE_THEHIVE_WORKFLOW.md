# KB-049 — Wazuh to Shuffle to TheHive Workflow

Status: **Live lab wiring validated** (2026-07-25).  
Branch: `kb039-kb060-platform-roadmap-execution`  
Module type: Planning doc + lab live wiring helpers (Wazuh shuffle integration script). No control-plane schema/compose/customer UI changes.

Builds on: `docs/KB036_MSSP_PLATFORM_ARCHITECTURE_ROADMAP.md`, **KB-040/041** (Wazuh stack), `docs/KB047_THEHIVE_DEPLOYMENT_PLAN.md` / co-located deploy, `docs/KB048_SHUFFLE_SOAR_DEPLOYMENT_PLAN.md`, and network detection KBs **KB-044** (Zeek deferred).

**Lab note:** Shuffle and TheHive run **co-located on VM 102** (`thehive_shuffle` / `192.168.0.212`), not separate VM 103.

---

## 1. Purpose

Define and wire the **SOC workflow** that routes **Wazuh alerts** (and Suricata-derived Wazuh alerts) through **Shuffle playbooks** on VM 102 to create or update **TheHive** alerts/cases — with tenant scoping, deduplication rules, and customer-safe projections back to MSSP Control Plane (KB-057 later).

---

## 2. Current baseline (live lab, 2026-07-25)

| Area | Status |
|---|---|
| VM 102 containers | TheHive + Shuffle stack **Up** (`:9000` / `:3001`) |
| TheHive `/api/status` | **OK** (HTTP 200) |
| Shuffle `/api/v1/health` | **OK** (admin user configured in browser) |
| TheHive org for tickets | Lab org **`MSSP-Lab`** (not the built-in `admin` org) |
| Wazuh → Shuffle trigger | **Configured** — Manager `ossec.conf` shuffle integration, level ≥ **10**, `wazuh-integratord` running |
| Shuffle → TheHive | **Configured** — workflow Webhook → TheHive `POST Create alert`; unique `sourceRef` required |
| End-to-end proof | **Passed** — temporary rule **100049** (level 12) → Shuffle webhook → new alert visible in TheHive **MSSP-Lab** |
| TheHive → Control Plane sync | **Not implemented** — KB-057 / future case sync |
| Tenant tagging on cases | Design only |
| Customer portal | Incident summaries (KB-025) — no workflow internals |

### 2.1 Lab URLs (SOC only — no secrets)

| Tool | URL |
|---|---|
| TheHive | `http://192.168.0.212:9000` |
| Shuffle | `http://192.168.0.212:3001` |
| Wazuh Dashboard | `https://192.168.0.211` |

Webhook URL and TheHive API keys stay **runtime-only** — never commit them.

### 2.2 Operator re-wire checklist (if rebuilding)

1. Open **Shuffle**: `http://192.168.0.212:3001` — admin already created in lab.
2. Open **TheHive**: `http://192.168.0.212:9000` — use org **MSSP-Lab** for alerts.
3. Shuffle workflow: **Webhook** (started) → TheHive create alert; auth URL `http://192.168.0.212:9000` + API key + org `MSSP-Lab`.
4. Alert JSON must include required TheHive fields (`type`, `source`, `sourceRef`, `title`, `description`, `date`, …) and a **unique** `sourceRef` per event.
5. On VM 100 (do not commit the URL):
   ```bash
   export SHUFFLE_WEBHOOK_URL='http://192.168.0.212:3001/api/v1/hooks/webhook_<ID>'
   export WAZUH_LEVEL_MIN=10
   ./scripts/kb049_configure_wazuh_shuffle_integration.sh
   ```
6. Helper inserts the shuffle `<integration>` **once** (first `</ossec_config>` only).

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
│ Shuffle SOAR (VM 102 co-located; VM 103 deferred) — KB-048      │
│   1. Receive alert payload                                      │
│   2. Resolve tenant_id (agent group / lookup)                   │
│   3. Deduplicate (open case? same rule+agent?)                │
│   4. Enrich (optional — MISP later KB-051)                      │
│   5. Create or update TheHive alert/case                        │
└────────────────────────────┬────────────────────────────────────┘
                             │ TheHive API
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│ TheHive (VM 102) — KB-047                                       │
│   Alert/case with tenant tag, title, severity, observables (SOC)│
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

**Lab v1 (done):** Wazuh shuffle integration webhook → Shuffle webhook URL (internal network only), level ≥ 10.

### 3.3 Playbook stages (reference design)

| Stage | Action |
|---|---|
| **Ingress** | Validate payload schema; reject malformed alerts safely (log server-side) |
| **Tenant resolve** | Map agent/group to `tenant_id` — fail closed if unknown |
| **Severity filter** | e.g. only level ≥ 10 opens new case; lower levels → notification only |
| **Dedup** | Search TheHive for open case with same tenant + rule + agent within window |
| **Case create** | POST TheHive alert/case with tenant custom field, title template, tags |
| **Observables** | Add IOCs for SOC — **not** synced raw to customer API |
| **Control plane hook** | Future: notify MSSP adapter to upsert `incidents` row (KB-057) |

### 3.4 Suricata / Zeek alerts in same workflow

Alerts that reached Wazuh via KB-044/046 use the **same Shuffle ingress** — playbook branches on `rule.groups` or `data.source` to set case category (network vs endpoint).

---

## 4. VM references

| VM | Name | Role in workflow |
|---|---|---|
| **VM 101** | `wazuh-stack` | Alert origin |
| **VM 102** | `thehive_shuffle` | TheHive + Shuffle (co-located lab) |
| **VM 103** | `shuffle` (deferred) | Separate Shuffle VM — not used in this lab |
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
| Rich Wazuh field mapping into TheHive title/description | Future playbook hardening |
| Shuffle playbook import/versioning | Future ops |
| TheHive case templates / auto-promote alert→case | Future |
| Bidirectional case status sync | KB-057 |
| MISP enrichment in playbook | KB-051 |
| Customer WhatsApp/email from workflow | Future notification KB |
| On-prem appliance alert path | KB-058 |
| Separate Shuffle VM 103 | Deferred (co-located on 102) |

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
- `scripts/kb049_configure_wazuh_shuffle_integration.sh` (runtime helper; webhook URL via env only)

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
