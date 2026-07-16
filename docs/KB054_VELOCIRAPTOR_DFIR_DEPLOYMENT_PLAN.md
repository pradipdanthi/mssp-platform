# KB-054 — Velociraptor DFIR Deployment Plan (VM 110)

Status: Implemented (pending validation/commit).  
Module type: **Planning / documentation only** — no runtime code, schema, compose, or `.env` changes.

Builds on: `docs/KB036_MSSP_PLATFORM_ARCHITECTURE_ROADMAP.md` (Phase 10 — DFIR).  
Related: KB-055 (DFIR Evidence Safety and Case Workflow — next), KB-047 (TheHive).

---

## 1. Purpose

Define the **lab deployment plan** for **Velociraptor** on **VM 110** (`velociraptor`) as the MSSP platform's **endpoint investigation and DFIR engine**.

This KB covers:

- VM 110 server layout, client enrollment, and lab scope (**planning only — no install in KB-054**)
- How Velociraptor fits the adapter pattern without exposing forensic artifacts to customers
- **Tenant isolation** for investigations and collected artifacts
- **Admin vs customer** visibility (case references only)
- **No secrets** and credential rules
- Deferrals to KB-055 (evidence safety and case workflow)

Velociraptor is **SOC/DFIR-only**. Customers never receive Velociraptor UI access, agent installers with embedded secrets, or raw collection results.

---

## 2. Current baseline

| Area | Status |
|---|---|
| VM 110 `velociraptor` | **Roadmap placeholder** — not created |
| Velociraptor server/clients | **Not deployed** |
| DFIR case linkage | TheHive planned KB-047 — not deployed |
| Customer incident detail | KB-025 — no DFIR artifact fields |
| osquery | KB-036 optional — not in KB-054 scope |

---

## 3. Target VM — VM 110 (`velociraptor`)

| Item | Planned value |
|---|---|
| Proxmox VM | **VM 110** |
| Hostname | `velociraptor` |
| Role | Central Velociraptor server for MSSP lab DFIR |
| Network | Internal lab VLAN; clients on VM 104/105; **not** customer-facing |
| Deployment | Ansible + Compose or official packages (KB-039) when implementation KB runs |

### 3.1 Planned components

| Component | Purpose |
|---|---|
| Velociraptor server | Orchestration, VQL queries, artifact collection |
| Velociraptor clients | Lab endpoints (Windows/Linux) — enrolled per tenant policy |
| Encrypted gRPC | Client-server communication — certs from vault |
| Artifact store | Server-side collection storage — **admin-only** |

### 3.2 Lab enrollment scope

| Client | Tenant mapping |
|---|---|
| VM 104 Windows lab | Mapped to DEMO tenant via `protected_assets` / appliance registry |
| VM 105 Linux lab | Same — explicit `tenant_id` on enrollment metadata |
| Production | Per-customer deployment mode (KB-038) — on-prem clients stay local where required |

---

## 4. Architecture placement (KB-036)

```
Incident / alert (tenant-scoped) triggers DFIR (SOC action)
  → Velociraptor collection on VM 110 (VQL artifacts)
  → Raw results stored server-side (encrypted, access-controlled)
  → Optional TheHive case attachment metadata (KB-055)
  → MSSP adapter writes case reference + safe status to PostgreSQL
  → Admin/SOC: full forensic context in Velociraptor UI
  → Customer portal: incident status / "investigation in progress" — **never raw evidence**
```

See `docs/KB036_MSSP_PLATFORM_ARCHITECTURE_ROADMAP.md` §Layer 8 (Velociraptor) and §7 VM 110.

---

## 5. Tenant isolation

| Rule | Requirement |
|---|---|
| Client labels | Every enrolled client tagged with **`tenant_id`** (Velociraptor labels + MSSP registry) |
| Collections | SOC initiates only on clients belonging to incident's tenant |
| Artifact storage | Namespace or label per tenant; admin cross-tenant requires elevated role + audit |
| Adapter writes | Case reference rows include `tenant_id NOT NULL` |
| Customer API | No collection IDs, VQL, or file paths; wrong incident → **404** |
| On-prem mode (KB-038) | Collections may run locally; only **safe case metadata** syncs to control plane |

---

## 6. Admin vs customer visibility

| Data | Admin/SOC | Customer portal |
|---|---|---|
| Velociraptor UI / VQL results | Yes | **Never** |
| Raw disk/memory artifacts | Yes (controlled store) | **Never** |
| File paths, registry hives | Yes | **Never** |
| Collection job ID | Yes | **Never** |
| Incident/case status update | Yes | Safe status label only |
| "Investigation underway" message | Yes | Optional plain-English notice |
| Client enrollment tokens | Yes (vault) | **Never** |

**Customer safety (KB-036 §9):** no packet captures, raw JSON, IP dumps, credentials, or internal notes.

---

## 7. Credentials and no secrets

| Rule | Requirement |
|---|---|
| Server/client certificates | PKI or vault-generated — **never Git** |
| Enrollment secrets / write-back keys | One-time issuance; stored hashed or in vault |
| Documentation | Placeholders only (`<REDACTED>`) |
| Customer API | Never return enrollment material or collection download URLs |

---

## 8. Integration touchpoints (planned)

| System | Role |
|---|---|
| TheHive (VM 102) | Case task + observable references (KB-055) |
| Shuffle (VM 103) | Optional auto-launch collection playbook |
| `incidents` table | Safe status sync after collection completes |
| Audit logs | Record who launched collection, tenant, incident ID |

---

## 9. Explicit deferrals

| Item | Deferred to |
|---|---|
| VM 110 provisioning / Velociraptor install | Future implementation KB |
| Client packages for lab endpoints | Post VM 104/105 readiness |
| KB-055 evidence safety workflow | Next Phase 10 module |
| Evidence download API | Admin-only future KB — never customer |
| osquery integration | Optional future KB |

---

## 10. Decision summary

| # | Decision | Choice |
|---|---|---|
| D1 | VM assignment | **VM 110** — hostname `velociraptor` |
| D2 | Customer Velociraptor access | **Never** |
| D3 | Raw evidence to customer | **Never** |
| D4 | Tenant isolation | Client labels + incident `tenant_id` enforcement |
| D5 | Parent roadmap | **KB-036** Phase 10 DFIR |
| D6 | Secrets in Git | **Forbidden** |

---

## 11. What KB-054 changes (and must not)

### Changes

- `docs/KB054_VELOCIRAPTOR_DFIR_DEPLOYMENT_PLAN.md` (this file)
- `scripts/kb054_validate_velociraptor_dfir_deployment_plan.sh`

### Must not change

- `backend-api/`, `frontend-customer/`, `frontend-admin/`
- `postgres/init/`, `docker-compose.yml`, `.env`

---

## 12. Validation

```bash
cd /opt/mssp-control
chmod +x scripts/kb054_validate_velociraptor_dfir_deployment_plan.sh
./scripts/kb054_validate_velociraptor_dfir_deployment_plan.sh
```

Expected final line:

```text
KB-054 VELOCIRAPTOR DFIR DEPLOYMENT PLAN VALIDATION PASSED
```
