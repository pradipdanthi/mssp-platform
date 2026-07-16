# KB-050 — MISP Threat Intelligence Deployment Plan (VM 108)

Status: Implemented (pending validation/commit).  
Module type: **Planning / documentation only** — no runtime code, schema, compose, or `.env` changes.

Builds on: `docs/KB036_MSSP_PLATFORM_ARCHITECTURE_ROADMAP.md` (Phase 8 — threat intel).  
Related: KB-049 (Wazuh → Shuffle → TheHive workflow), KB-051 (Threat Intel Enrichment Workflow — next).

---

## 1. Purpose

Define the **lab deployment plan** for **MISP** (Malware Information Sharing Platform) on **VM 108** (`misp`) as the MSSP platform's **threat intelligence engine**.

This KB covers:

- VM sizing, network placement, and service layout (planning only — **no install in KB-050**)
- How MISP fits the KB-036 adapter pattern (engine → normalize → PostgreSQL)
- **Tenant isolation** rules for intel feeds, events, and sharing groups
- **Admin vs customer** visibility boundaries
- Credential and **no secrets** handling
- Deferrals to KB-051 (enrichment workflow) and KB-057 (live integration)

MISP is a **backend SOC tool**. Customers never receive direct MISP logins or raw feed exports.

---

## 2. Current baseline

| Area | Status |
|---|---|
| VM 108 `misp` | **Roadmap placeholder** — not created |
| MISP service | **Not deployed** |
| Threat intel tables/adapters | **Not implemented** — future schema KB |
| KB-049 SOAR/case path | Planned — TheHive/Shuffle not deployed yet |
| Customer portal | No threat-intel UI — summaries via alert/incident enrichment only (KB-051) |

---

## 3. Target VM — VM 108 (`misp`)

| Item | Planned value |
|---|---|
| Proxmox VM | **VM 108** |
| Hostname | `misp` |
| Role | Central MISP threat intelligence platform for MSSP lab |
| Network | Internal lab VLAN; reachable from VM 100 (control plane), VM 103 (Shuffle), VM 102 (TheHive) — **not** customer-facing |
| Deployment method | Ansible + Docker Compose (KB-039 foundation) when implementation KB runs |

### 3.1 Planned service components (reference layout)

| Component | Purpose |
|---|---|
| MISP web UI | Analyst feed/event management — **SOC/admin only** |
| MISP API | Automation: Shuffle, adapters, enrichment workers |
| MariaDB/MySQL | MISP database — **admin-only** access |
| Redis | MISP queue/cache |
| Optional sync | Future trusted feed connectors (document only — no live keys in Git) |

### 3.2 Capacity notes (lab)

- Single VM sufficient for lab/demo multi-tenant enrichment
- Production scaling (feed volume, event rate) deferred to KB-059 / ops runbooks (KB-060)

---

## 4. Architecture placement (KB-036)

```
External / trusted threat feeds (future)
  → VM 108 MISP (normalize IOCs, attributes, tags)
  → Shuffle playbooks / enrichment worker (KB-051)
  → MSSP adapters → tenant-scoped intel references in PostgreSQL
  → Admin/SOC dashboard (full context)
  → Customer portal (plain-English enrichment only — never raw MISP JSON)
```

**Architecture invariant:** Control plane consumes **normalized, tenant-scoped records** with `source_platform = misp` (or adapter label). See `docs/KB036_MSSP_PLATFORM_ARCHITECTURE_ROADMAP.md` §5.

---

## 5. Tenant isolation

Every MISP-related record stored in MSSP Control Plane must include **`tenant_id`** and be queryable only within that tenant.

| Rule | Requirement |
|---|---|
| Feed scope | Shared MSSP feeds may exist at platform level; **tenant attribution** happens at enrichment/adapter layer — never mix tenant A IOC context into tenant B alerts |
| MISP sharing groups | Lab: single org or org-per-tenant model documented before install KB; production must map sharing groups to `tenant_id` policy |
| Adapter writes | All inserts/updates filtered by `tenant_id` from authenticated admin context or trusted pipeline identity |
| Customer API | **Never** accept client-supplied `tenant_id` without cross-check against session tenant |
| Wrong tenant lookup | Customer APIs return **404** (not 403) on cross-tenant ID guesses |

MISP itself is cross-tenant at the engine layer; **MSSP Control Plane enforces isolation** in PostgreSQL and API projections.

---

## 6. Admin vs customer visibility

| Data | Admin/SOC | Customer portal |
|---|---|---|
| MISP UI / raw events | Yes (SOC analysts — future) | **Never** |
| Raw MISP JSON, feed URLs, API keys | Yes (secured env) | **Never** |
| IOC attributes (hashes, IPs, domains) | Yes for investigation | **Only** via approved customer-safe alert/incident summary fields (KB-051) |
| Threat intel source feed names | Yes | Safe label only if needed (e.g. "Known malicious indicator") |
| Internal MISP tags, galaxy clusters | Yes | **Never** |
| Enrichment confidence / analyst notes | Yes | Plain-English summary only |

**Customer portal safety (KB-036 §9):** no raw logs, no raw JSON, no packet captures, no credentials, no internal notes.

---

## 7. Credentials and no secrets

| Rule | Requirement |
|---|---|
| MISP admin/API keys | Stored in **environment / secrets vault** — never in Git, docs, or customer API |
| Documentation | Use placeholders only (`<REDACTED>`, `MISP_API_KEY`) |
| Ansible inventory | Encrypted vault or runtime injection — not committed plaintext |
| Validation scripts | Scan docs for obvious secret patterns |
| Customer responses | Never return tokens, keys, or feed authentication material |

---

## 8. Integration touchpoints (planned — not KB-050 scope)

| Consumer | Use |
|---|---|
| Shuffle (VM 103) | Pull IOC context during alert playbooks (KB-048/049) |
| Enrichment worker | KB-051 — attach intel summary to `security_alerts` |
| TheHive (VM 102) | Optional observable linking on cases |
| MSSP adapter | Normalize to `source_platform`, optional future `threat_intel_references` table |

---

## 9. Explicit deferrals

| Item | Deferred to |
|---|---|
| Proxmox VM 108 creation | Future implementation KB after KB-050 validated |
| MISP Docker/Ansible install | Future KB (after KB-039 automation foundation) |
| PostgreSQL schema for intel references | Future schema KB |
| KB-051 enrichment workflow | Next module in Phase 8 |
| Live customer-facing enrichment | KB-057 |
| OpenCTI | KB-036 — future optional, not immediate |

---

## 10. Decision summary (approved defaults)

| # | Decision | Choice |
|---|---|---|
| D1 | VM assignment | **VM 108** — hostname `misp` |
| D2 | Customer MISP access | **Never** — adapter summaries only |
| D3 | Tenant isolation | Enforced at control plane PostgreSQL + API |
| D4 | Secrets in Git | **Forbidden** — env/vault only |
| D5 | Raw MISP to customer | **Never** |
| D6 | Parent roadmap | **KB-036** Phase 8 threat intel |

---

## 11. What KB-050 changes (and must not)

### Changes

- `docs/KB050_MISP_THREAT_INTEL_DEPLOYMENT_PLAN.md` (this file)
- `scripts/kb050_validate_misp_threat_intel_deployment_plan.sh`

### Must not change

- `backend-api/`, `frontend-customer/`, `frontend-admin/`
- `postgres/init/`, `docker-compose.yml`, `.env`
- No VM 108 provisioning in KB-050

---

## 12. Validation

```bash
cd /opt/mssp-control
chmod +x scripts/kb050_validate_misp_threat_intel_deployment_plan.sh
./scripts/kb050_validate_misp_threat_intel_deployment_plan.sh
```

Expected final line:

```text
KB-050 MISP THREAT INTEL DEPLOYMENT PLAN VALIDATION PASSED
```
