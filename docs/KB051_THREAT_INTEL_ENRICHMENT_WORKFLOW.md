# KB-051 — Threat Intel Enrichment Workflow

Status: Implemented (pending validation/commit).  
Module type: **Planning / documentation only** — no runtime code, schema, compose, or `.env` changes.

Builds on: `docs/KB050_MISP_THREAT_INTEL_DEPLOYMENT_PLAN.md` and `docs/KB036_MSSP_PLATFORM_ARCHITECTURE_ROADMAP.md`.  
Related: KB-049 (alert → Shuffle → TheHive), KB-057 (customer-safe live SOC integration).

---

## 1. Purpose

Define the **end-to-end threat intelligence enrichment workflow**: how security alerts and incidents gain **context from MISP (VM 108)** while preserving **tenant isolation**, **no secrets**, and **customer-safe** projections.

This KB documents:

- Trigger points (new/updated alerts, case observables)
- Shuffle playbook and worker responsibilities
- Normalized fields written to MSSP Control Plane
- Plain-English customer summaries vs SOC-only technical detail
- Failure and timeout behavior

**No runtime implementation** in KB-051 — workflow design only.

---

## 2. Current baseline

| Area | Status |
|---|---|
| MISP (VM 108) | Planned in KB-050 — not deployed |
| Shuffle (VM 103) | Not deployed |
| Alert enrichment fields | Existing `security_alerts` — customer-safe AI/summary fields; no MISP linkage yet |
| Enrichment worker | Not implemented |
| Customer alert detail (KB-029) | Shows approved summary fields only |

---

## 3. Workflow overview

```
security_alerts (tenant-scoped) or TheHive observables
  → enrichment trigger (Shuffle playbook or background worker)
  → MISP API lookup on VM 108 (hashes, IPs, domains, URLs — SOC path)
  → normalize match result (tenant_id, source_platform=misp, visibility_status)
  → update alert/incident enrichment fields in PostgreSQL
  → Admin/SOC: full match metadata
  → Customer API: plain-English enrichment block only
```

Reference architecture: `docs/KB036_MSSP_PLATFORM_ARCHITECTURE_ROADMAP.md` §5 normalization rule and §9 customer portal safety.

---

## 4. Trigger points

| Trigger | Actor | Notes |
|---|---|---|
| New high/critical alert | Shuffle playbook (KB-049 path) | Primary lab path |
| Alert observable added | Enrichment worker | Idempotent re-enrichment |
| Case observable (TheHive) | Optional sync job | Links case + alert intel |
| Manual SOC re-run | Admin action (future API) | Audit logged |

All triggers must resolve **`tenant_id`** from the alert/incident record — never from unvalidated client input.

---

## 5. MISP lookup rules

| Rule | Requirement |
|---|---|
| Query types | Hashes, IP, domain, URL — allowlist per customer safety policy |
| Timeout | Bounded (e.g. 10–30s); fail safe — alert remains without enrichment |
| No match | Store `enrichment_status = no_match` — not an error |
| Multiple matches | Prefer highest confidence / most specific attribute; SOC sees full list |
| Shared feeds | Platform feeds OK; **results tagged with tenant context** at write time |
| Rate limits | Queue/worker backoff — never block alert ingestion |

MISP credentials: **environment only** — **no secrets** in Git or logs returned to customers.

---

## 6. Normalized output (planned fields)

Future adapter/worker writes (names illustrative — schema KB later):

| Field | Admin/SOC | Customer API |
|---|---|---|
| `enrichment_status` | Yes | Safe enum label |
| `threat_intel_summary` | Yes (technical + plain) | **Plain-English only** |
| `matched_ioc_type` | Yes | Generic label if approved |
| `matched_ioc_value` | Yes (full) | **Never** raw IOC unless explicitly approved safe design |
| `misp_event_uuid` | Yes | **Never** |
| `source_platform` | Yes (`misp`) | Hidden or generic "Threat intelligence" |
| `visibility_status` | Yes | Drives customer projection |

Align with KB-036 record concepts: `alert`, `tenant`, `source_platform`, `visibility_status`.

---

## 7. Tenant isolation

| Rule | Requirement |
|---|---|
| Alert lookup | Enrichment only for alerts where `alert.tenant_id = T` |
| MISP query context | Must not attach Tenant B intel narrative to Tenant A alert |
| Worker identity | Pipeline uses service credentials — tenant scope from record, not from MISP org alone |
| Customer API | Filter enrichment block by authenticated user's tenant; wrong ID → **404** |
| Cross-tenant feed hits | Log at platform level; **store per-tenant enrichment copy** if narrative differs |

---

## 8. Admin vs customer visibility

| Content | Admin/SOC | Customer portal |
|---|---|---|
| Full MISP attribute JSON | Yes | **Never** |
| Feed/source attribution (internal) | Yes | Safe generic wording |
| Confidence scores (raw) | Yes | Optional simplified label ("High confidence") |
| Recommended actions | Yes | Existing recommendation workflow |
| Internal analyst enrichment notes | Yes | **Never** (`internal_notes` forbidden) |

**Customer safety:** enrichment must not leak other tenants' context, raw STIX/MISP exports, or credential material.

---

## 9. Failure modes

| Condition | Behavior |
|---|---|
| MISP offline | `enrichment_status = unavailable`; alert unchanged; log for SOC |
| Timeout | Retry with backoff; cap attempts; no customer-facing error detail |
| Malformed MISP response | Discard; log server-side; never crash ingestion |
| Partial field mapping | Write safe subset only; flag degraded in admin view |

---

## 10. Explicit deferrals

| Item | Deferred to |
|---|---|
| Shuffle playbook JSON | Post KB-048/049 implementation |
| PostgreSQL columns / tables | Future schema KB |
| Enrichment worker code | KB-057 or dedicated implementation KB |
| Customer UI enrichment section | Future customer alert detail enhancement |
| MISP VM install | KB-050 follow-on implementation KB |

---

## 11. Decision summary

| # | Decision | Choice |
|---|---|---|
| D1 | Intel engine | MISP on **VM 108** (KB-050) |
| D2 | Primary orchestration | Shuffle + background worker |
| D3 | Customer sees | Plain-English enrichment summary only |
| D4 | Raw MISP to customer | **Never** |
| D5 | Tenant isolation | Record-scoped `tenant_id` on every write |
| D6 | Secrets | **No secrets** in Git/docs — MISP API via env |

---

## 12. What KB-051 changes (and must not)

### Changes

- `docs/KB051_THREAT_INTEL_ENRICHMENT_WORKFLOW.md` (this file)
- `scripts/kb051_validate_threat_intel_enrichment_workflow.sh`

### Must not change

- `backend-api/`, `frontend-customer/`, `frontend-admin/`
- `postgres/init/`, `docker-compose.yml`, `.env`

---

## 13. Validation

```bash
cd /opt/mssp-control
chmod +x scripts/kb051_validate_threat_intel_enrichment_workflow.sh
./scripts/kb051_validate_threat_intel_enrichment_workflow.sh
```

Expected final line:

```text
KB-051 THREAT INTEL ENRICHMENT WORKFLOW VALIDATION PASSED
```
