# KB-047 — TheHive Deployment Plan (VM 102)

Status: Implemented (pending validation/commit).  
Branch: `kb039-kb060-platform-roadmap-execution`  
Module type: **Planning / documentation only** — no runtime code, schema, compose, or `.env` changes.

Builds on: `docs/KB036_MSSP_PLATFORM_ARCHITECTURE_ROADMAP.md`, `docs/KB037_CLUSTER_APPLIANCE_REGISTRY_PLANNING.md`, `docs/KB038_TENANT_DEPLOYMENT_MODE_PLANNING.md`.

---

## 1. Purpose

Define the **lab deployment plan** for **TheHive** case and incident workflow platform on **VM 102** (`thehive`) — including optional Cortex, database dependencies, admin access model, and tenant/case scoping rules — before SOAR integration (KB-048/049) and control-plane case sync (KB-057).

This KB is **planning only**. No VM creation, TheHive install, or API wiring in this module.

---

## 2. Current baseline

| Area | Status |
|---|---|
| VM 102 `thehive` | **Not created** — roadmap placeholder (KB-036) |
| TheHive / Cortex | **Not deployed** |
| Case management in control plane | `incidents` table exists — no live TheHive sync |
| Customer portal | Incident summaries (KB-025) — no raw TheHive case JSON |
| Shuffle SOAR | **Not deployed** — VM 103 (KB-048) |

---

## 3. Architecture

### 3.1 TheHive role in MSSP stack

TheHive is the **SOC case workflow system** — analysts create and manage cases, tasks, observables, and timelines. It is **not** customer-facing UI. MSSP Control Plane holds **normalized incident records**; TheHive holds operational case detail.

```
Wazuh / Suricata / Zeek alerts (via KB-049 workflow)
  → Shuffle playbooks (VM 103)
  → TheHive cases (VM 102)
  → Future MSSP adapter (KB-057) → incidents table (tenant-scoped summaries)
  → Admin/SOC dashboard → customer-safe incident portal (KB-025)
```

### 3.2 Planned VM specification (lab)

| Item | Planned value |
|---|---|
| VM ID | **102** |
| Hostname | `thehive` |
| OS | Ubuntu LTS (KB-039 Ansible baseline) |
| vCPU / RAM | 4 vCPU, 8–16 GB RAM (TheHive + Cortex if co-located) |
| Disk | 60+ GB |
| Dependencies | Cassandra and/or Elasticsearch (per TheHive version — pin at implementation); optional Cortex on same VM or separate |

### 3.3 Deployment components (implementation checklist — not executed in KB-047)

1. Create VM 102 in Proxmox.
2. Deploy TheHive via Docker Compose or KB-039 playbook (version pinned at implementation).
3. Configure admin org, service accounts, API keys — **secrets in env only**.
4. Define **case naming / tagging** convention for `tenant_id` or tenant short code.
5. Optional: Cortex analyzers for enrichment (defer heavy analyzer set to KB-051+).
6. Health check: TheHive API `/api/status`, case create smoke test.

---

## 4. VM references

| VM | Name | Role |
|---|---|---|
| **VM 102** | `thehive` | TheHive (+ optional Cortex) — **this KB's focus** |
| **VM 103** | `shuffle` | SOAR — creates/updates cases via API (KB-048/049) |
| **VM 101** | `wazuh-stack` | Alert source for workflows |
| **VM 100** | `mssp-control` | System of record for customer-visible incidents |

---

## 5. Tenant isolation

- TheHive cases must be **tagged or organized** so SOC analysts cannot accidentally mix tenant data in customer-facing sync.
- Planning conventions (future implementation):
  - Case custom field: `tenant_id` or `tenant_short_code` (required on case create from Shuffle)
  - Separate TheHive organizations per tenant for high-isolation customers (production option)
  - MSSP adapter (KB-057) maps TheHive case → `incidents` row with strict `tenant_id` filter
- Customer APIs: only normalized incident summaries — wrong tenant → **404**.
- TheHive API keys and case observables with PII — **admin/SOC only**, never customer portal.

---

## 6. Customer portal safety

Customer portal must **never** expose:

- Raw TheHive case JSON, observables, or task details
- Cortex analyzer raw output
- Internal case IDs unless projected as customer-safe incident numbers (existing KB-025 pattern)
- TheHive URLs, API keys, or analyst notes marked internal

Customers see: incident title/status, plain-English summary, business impact, recommended actions — per existing customer incident design.

**No secrets** in Git, docs, or customer API responses.

---

## 7. Relationship to prior KBs

| KB | Relationship |
|---|---|
| **KB-036** | TheHive in case + SOAR phase; VM 102 placement |
| **KB-037/038** | Tenant/cluster context for case tagging |
| **KB-039** | Deployment automation for VM 102 |
| **KB-048** | Shuffle on VM 103 integrates with TheHive API |
| **KB-049** | Wazuh→Shuffle→TheHive end-to-end workflow |
| **KB-025** | Customer incident detail UI — receives safe projections only |
| **KB-057** | Live case/incident sync adapter |

---

## 8. Explicit deferrals

| Item | Deferred to |
|---|---|
| VM 102 provisioning | KB-047 implementation KB |
| TheHive + DB install | KB-047 implementation KB |
| Cortex analyzer catalog | KB-051 / enrichment KBs |
| Shuffle webhook configuration | KB-048/049 |
| MSSP `incidents` ↔ TheHive bidirectional sync | KB-057 |
| Customer case export | Out of scope |

---

## 9. Decision summary (approved defaults)

| # | Decision | Choice |
|---|---|---|
| D1 | Case platform VM | VM 102 `thehive` |
| D2 | Cortex | Optional on VM 102 for lab — not required for KB-047 plan approval |
| D3 | Tenant scoping | Mandatory tenant tag/field on automated case creation |
| D4 | Customer visibility | Normalized incident summaries only — **no raw TheHive data** |
| D5 | Secrets | API keys in env/secret store — **no secrets** in Git or docs |

---

## 10. What KB-047 changes (and must not)

### Changes

- `docs/KB047_THEHIVE_DEPLOYMENT_PLAN.md` (this file)
- `scripts/kb047_validate_thehive_deployment_plan.sh`

### Must not change

- `backend-api/`, `frontend-customer/`, `frontend-admin/`
- `postgres/init/`, `docker-compose.yml`, `.env`

---

## 11. Validation

```bash
cd /opt/mssp-control
chmod +x scripts/kb047_validate_thehive_deployment_plan.sh
./scripts/kb047_validate_thehive_deployment_plan.sh
```

Expected final line:

```text
KB-047 THEHIVE DEPLOYMENT PLAN VALIDATION PASSED
```
