# REL-001 Sovereign Edge Release Readiness

| Field | Value |
|-------|-------|
| **Work ID** | REL-001 |
| **Release identifier** | `sovereign-beta` (OpenProject Version) |
| **Product RC branch** | `kb112-sovereign-edge` |
| **Product RC commit** | `87821f1201a8571bdf1696ffe1f6e98d09e8108c` (`87821f1`) |
| **RC subject** | `fix(sovereign): harden portal authentication and RBAC` |
| **RC author** | Pradip Danthi |
| **RC date** | 2026-08-29 14:34:59 +0530 |
| **Gate date** | 2026-08-29 |
| **Disposition** | **GO — RELEASE CANDIDATE READY** |

## Release Candidate

The certified product release candidate is commit **`87821f1`** on branch **`kb112-sovereign-edge`**. Any subsequent docs-only commit(s) for release metadata do **not** change product code under test.

Sovereign Edge delta from platform baseline (`9bbad4f` / `kb111-appliance-entitlement-niktiar-validated`):

| Commit | Summary |
|--------|---------|
| `03133b2` | KB-112 foundation and deployment mode |
| `72caa9b` | Integrate deployment mode with control plane |
| `babf115` | Sovereign edge runtime and offline operation |
| `13b025f` | KB-112–115 validation and deployment tooling |
| `46ff0f7` | Stabilize KB-113 logical HA validation |
| `87821f1` | Harden portal authentication and RBAC (SEC-001) |

## QA Evidence

| Item | Value |
|------|-------|
| **Work package** | QA-001 — Closed, QA Status = Regression Pass |
| **Evidence file** | `docs/qa/QA-001-SOVEREIGN-REGRESSION.md` |
| **KB-112** | 14/14 PASS |
| **SEC-001 auth** | 13/13 PASS |
| **Sovereign RBAC** | 19/19 PASS |
| **KB-113** | 10/10 PASS (×2 consecutive + contamination final) |
| **KB-114** | 19/19 PASS |
| **KB-115** | 12/12 PASS (alias mode) |
| **Control-plane regression** | 136 unit tests PASS; authenticated API PASS |
| **VM210 runtime** | PASS |

No product code changes were required during QA-001. Live Git HEAD at REL-001 gate matches QA evidence exactly.

## Security Gate

| Check | Status |
|-------|--------|
| SEC-001 work package | Closed |
| Signed JWT (HMAC-SHA256) | Present in `portal_auth.py` |
| PBKDF2 user credentials | Present |
| `X-Sovereign-Role` auth bypass | **Not present** in source |
| Bearer-only portal auth | `unified_portal.py` uses `Authorization` Bearer |
| Lab bootstrap gating | `SOVEREIGN_PORTAL_LAB_BOOTSTRAP` env-gated |
| Secrets in tracked files | None identified in RC scope |

## Release Scope

This release candidate includes:

- **Sovereign Edge foundation (KB-112):** `sovereign_edge` deployment mode, control-plane integration, admin UI, offline license delivery helpers
- **Logical HA (KB-113):** single-host logical cluster, failover, split-brain guard, state replication
- **Full stack / air-gap (KB-114):** unified portal, TheHive/Shuffle integration paths, offline operation, renewal reminders
- **Multihost HA (KB-115):** multihost cluster topology, cross-node replication, alias-mode lab validation path
- **Authentication / RBAC (SEC-001):** local JWT auth, role enforcement, header-spoof rejection

Out of scope for this gate: customer shipment, external publish, VM199 golden bake.

## Known Limitations (Non-blocking)

- KB-115 validated via **alias mode** on Beta (231/232 NIC aliases) when ephemeral Proxmox clones were unreachable — supported by repo provisioning script fallback
- Legacy validators `kb008` / `kb010` expect pre-SEC-001 unauthenticated admin APIs; superseded by sovereign RBAC + authenticated regression
- OpenProject uses **Closed** status where governance spec references **DONE**

## Technical Debt (Deferred)

| ID | Status | Release impact |
|----|--------|----------------|
| TD-001 | BACKLOG | NON_BLOCKING — synthetic data paths |
| TD-002 | BACKLOG | NON_BLOCKING — lab infrastructure defaults |
| TD-003 | BACKLOG | NON_BLOCKING — appliance automated test suite expansion |
| TD-004 | BACKLOG | NON_BLOCKING — control-plane HA design |

## Architecture Decision

**ARCH-001** (official customer appliance delivery model: VM199 clone vs mkosi vs other) remains **BACKLOG**. REL-001 completes the **technical release gate** without resolving ARCH-001. Customer delivery/publish may remain blocked on ARCH-001 until product owner decision.

## Packaging / Delivery State

**Audit classification:** `CONTROL_PLANE_CODE_ONLY` + `APPLIANCE_RUNTIME` (lab-provisioned)

| Asset class | Location | Notes |
|-------------|----------|-------|
| Control plane | `backend-api/`, `frontend-admin/`, `docker-compose.yml` | Docker Compose on VM100 |
| Sovereign service modules | `backend-api/app/services/sovereign_edge.py`, `sovereign_rbac.py` | Integrated with tenant management |
| Appliance runtime | `kevantic-appliance/appliance/sovereign/` | Portal auth, logical/multihost cluster, node agent |
| Provisioning scripts | `scripts/kb112_*`, `kb113_*`, `kb114_*`, `kb115_*` | Lab validation and Beta provisioning |
| Appliance enablement | `kevantic-appliance/scripts/enable_sovereign_*` | On-appliance installation |
| Packer/B2 pipeline | `kevantic-appliance/scripts/b2_*` | Exists; not executed in REL-001 |
| Golden VM199 bake | `kevantic-appliance/scripts/bake_golden_vm199_*` | **Not executed** — separate controlled work item |
| Appliance VERSION file | `kevantic-appliance/VERSION` = `0.1.0-dev` | Dev track; no sovereign-specific semver tag yet |

**Release artifact for this gate:** Git branch `kb112-sovereign-edge` at `87821f1`, validated on lab VM100 + VM210. No immutable customer image produced.

## Release Risks

| Risk | Severity | Mitigation |
|------|----------|------------|
| ARCH-001 undecided delivery model | Medium (publish) | Documented deferral; lab RC still valid |
| KB-115 alias-mode vs true 2-VM clones | Low | Script-designed fallback; multihost logic validated |
| Legacy validator drift | Low | Sovereign-specific suites authoritative |
| No VM199 golden refresh for sovereign stack | Medium (fleet) | Separate bake work item after release decision |

## Rollback / Recovery References

- **Product rollback:** checkout `87821f1` on `kb112-sovereign-edge`; platform baseline tag `kb111-appliance-entitlement-niktiar-validated` (`9bbad4f`)
- **QA evidence:** `docs/qa/QA-001-SOVEREIGN-REGRESSION.md`
- **Lab runtime:** VM100 control plane containers; VM210 logical HA restored post-QA
- **OpenProject:** QA-001 Closed; Version `sovereign-beta` open

## Git Tag

Annotated tag **`kb112-sovereign-edge-validated`** on product RC **`87821f1`**, following repository `kb###-*-validated` convention.

## VM199 Action

**NONE** — no boot, modify, rebake, snapshot, or template conversion during REL-001.

## Release Recommendation

**GO — RELEASE CANDIDATE READY**

All REL-001 gates satisfied:

- QA-001 Regression Pass accepted
- Product RC identified and matches live Git
- No source drift since QA
- SEC-001 satisfied
- No critical/high release blocker
- Runtime sanity pass (VM100 + VM210)
- Release documentation complete
- OpenProject tracking updated

Shipment, external publish, and VM199 golden bake are **separate authorized actions** not performed by REL-001.
