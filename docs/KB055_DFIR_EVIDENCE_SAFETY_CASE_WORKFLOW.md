# KB-055 — DFIR Evidence Safety and Case Workflow

Status: Implemented (pending validation/commit).  
Module type: **Planning / documentation only** — no runtime code, schema, compose, or `.env` changes.

Builds on: `docs/KB054_VELOCIRAPTOR_DFIR_DEPLOYMENT_PLAN.md` and `docs/KB036_MSSP_PLATFORM_ARCHITECTURE_ROADMAP.md` (TheHive VM 102 — KB-047 planned).  
Related: KB-025 (customer incident detail), KB-057 (live integration).

---

## 1. Purpose

Define **evidence safety rules** and the **DFIR case workflow** linking **Velociraptor (VM 110)** collections to **TheHive cases** and **MSSP incidents** — preserving chain-of-custody for SOC while ensuring **tenant isolation**, **no secrets**, and **zero raw evidence exposure** to customers.

This KB documents:

- Evidence classification and storage boundaries
- Case workflow steps (trigger → collect → review → close)
- Metadata allowed in MSSP Control Plane vs evidence that stays in DFIR store
- Customer-visible incident updates (status/summary only)
- Retention, access control, and audit requirements

**No runtime implementation** in KB-055.

---

## 2. Current baseline

| Area | Status |
|---|---|
| Velociraptor (VM 110) | Planned KB-054 — not deployed |
| TheHive (VM 102) | Planned KB-047 — not deployed |
| Customer incidents | KB-025 detail — safe fields only |
| DFIR evidence store | Not implemented |
| Chain-of-custody audit | General `audit_logs` exist — DFIR extensions planned |

---

## 3. Workflow overview

```
SOC opens / links TheHive case to MSSP incident (tenant-scoped)
  → DFIR analyst authorizes Velociraptor collection (VM 110)
  → Raw evidence stored in DFIR vault (encrypted, tenant-labeled)
  → TheHive task updated with evidence reference (hash, analyst, timestamp — not file download for customer)
  → MSSP adapter syncs safe incident status + case reference to PostgreSQL
  → Admin/SOC: full case + Velociraptor + TheHive context
  → Customer portal: incident status / plain-English update — **never evidence files or VQL output**
```

Architecture reference: `docs/KB036_MSSP_PLATFORM_ARCHITECTURE_ROADMAP.md` §5 (`incident` / `case`) and §9 customer portal safety.

---

## 4. Evidence classification

| Class | Examples | Customer visibility |
|---|---|---|
| **E0 — Metadata** | "Investigation opened", status timestamps | Safe summary allowed |
| **E1 — Derived facts** | "Suspicious scheduled task found" (analyst-written) | Plain-English in incident update if approved |
| **E2 — Technical artifacts** | VQL output, file hashes, registry paths | **SOC only** |
| **E3 — Raw collections** | Memory dumps, disk images, PCAP extracts | **SOC only** — encrypted store |
| **E4 — Credentials/tokens** | Recovered passwords, keys | **SOC only** — never customer, never Git |

Rule: **Default deny** — only E0/E1 approved text may appear in customer APIs.

---

## 5. Chain of custody (planned)

| Event | Audit field |
|---|---|
| Collection started | `actor_user_id`, `tenant_id`, `incident_id`, `client_id`, timestamp |
| Collection completed | Artifact hash (SHA-256), storage path (admin-only), size |
| Evidence accessed | Analyst ID, purpose, timestamp |
| Evidence exported | Approval ticket ID, destination (admin-only) |
| Evidence destroyed | Retention policy trigger, approver |

Audit logs: server-side detail OK; **never** expose custody log raw entries to customer API.

---

## 6. TheHive case linkage

| Field | Admin/SOC | Customer API |
|---|---|---|
| TheHive case ID | Yes | **Never** (or opaque "Case ref" if policy allows — prefer hidden) |
| Case title (internal) | Yes | **Never** verbatim if sensitive |
| Task status | Yes | Mapped to incident status label |
| Observable list (raw) | Yes | **Never** |
| Analyst assignment | Yes | **Never** |
| Safe incident narrative | Yes (editable) | Plain-English `customer_summary` only |

If TheHive KB-047 doc is not yet present, treat TheHive as planned VM 102 case engine per KB-036.

---

## 7. Tenant isolation

| Rule | Requirement |
|---|---|
| Incident scope | DFIR actions only when `incidents.tenant_id = T` |
| Velociraptor client | Must belong to same tenant as incident |
| TheHive case | Tagged with tenant org / custom field — no cross-tenant case merge |
| Evidence store path | Include tenant namespace |
| Customer incident API | Filter by session tenant; wrong `incidentNumber` → **404** |
| Hybrid/on-prem (KB-038) | Local collection allowed; **only E0/E1 metadata** crosses sync boundary |

---

## 8. Admin vs customer visibility

| Content | Admin/SOC | Customer portal |
|---|---|---|
| Velociraptor collection packages | Yes | **Never** |
| Download links / signed URLs | Admin-only authenticated | **Never** |
| VQL queries | Yes | **Never** |
| Incident status (`investigating`, `contained`, `closed`) | Yes | Yes — safe enum |
| Business impact statement | Yes | Yes — plain English |
| Recommended customer actions | Yes | Yes — via recommendations |
| `internal_notes`, `admin_notes` | Yes | **Never** |
| IP addresses from forensics | Yes | Omit unless approved safe design |

---

## 9. Retention and safety controls

| Control | Requirement |
|---|---|
| Encryption at rest | Required for E2/E3 in lab and production |
| Access RBAC | DFIR role + tenant scope for analysts |
| Retention period | Document per tenant contract — default lab 90 days |
| Deletion | Secure wipe; audit entry |
| Malware samples | Isolated analysis zone — never customer portal |
| **No secrets** in evidence exports | Redact before any export outside DFIR vault |

---

## 10. Failure modes

| Condition | Behavior |
|---|---|
| Collection fails | Incident stays open; SOC-only error detail |
| TheHive unreachable | Store evidence reference locally; retry sync |
| Tenant mismatch detected | Abort collection; alert platform admin |
| Customer requests "evidence" | Policy: provide summary only — never E2/E3 |

---

## 11. Explicit deferrals

| Item | Deferred to |
|---|---|
| Velociraptor install | KB-054 implementation follow-on |
| TheHive install | KB-047 |
| Evidence vault implementation | Future infrastructure KB |
| Customer incident DFIR status UI | Optional enhancement to KB-025 |
| Legal hold / export packages | KB-060 ops runbook |

---

## 12. Decision summary

| # | Decision | Choice |
|---|---|---|
| D1 | DFIR engine | Velociraptor **VM 110** (KB-054) |
| D2 | Case system | TheHive **VM 102** (KB-047) |
| D3 | Customer evidence access | **Never** — status/summary only |
| D4 | Chain of custody | Required audit trail for E2/E3 |
| D5 | Tenant isolation | Enforced on incident, client, case, store |
| D6 | Secrets | **No secrets** in Git, docs, or customer API |

---

## 13. What KB-055 changes (and must not)

### Changes

- `docs/KB055_DFIR_EVIDENCE_SAFETY_CASE_WORKFLOW.md` (this file)
- `scripts/kb055_validate_dfir_evidence_safety_case_workflow.sh`

### Must not change

- `backend-api/`, `frontend-customer/`, `frontend-admin/`
- `postgres/init/`, `docker-compose.yml`, `.env`

---

## 14. Validation

```bash
cd /opt/mssp-control
chmod +x scripts/kb055_validate_dfir_evidence_safety_case_workflow.sh
./scripts/kb055_validate_dfir_evidence_safety_case_workflow.sh
```

Expected final line:

```text
KB-055 DFIR EVIDENCE SAFETY CASE WORKFLOW VALIDATION PASSED
```
