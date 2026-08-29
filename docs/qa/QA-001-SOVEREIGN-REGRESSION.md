# QA-001 — Sovereign Edge Release Regression Sign-off

| Field | Value |
|-------|-------|
| **Work ID** | QA-001 |
| **Branch** | `kb112-sovereign-edge` |
| **Git HEAD (start/final)** | `87821f1201a8571bdf1696ffe1f6e98d09e8108c` |
| **Date (UTC+5:30)** | 2026-08-29 |
| **Primary host** | VM100 `mssp-control` / 192.168.0.201 |
| **Appliance** | VM210 `junexis-appliance-lab-01` / 192.168.0.226 |
| **QA engineer** | Autonomous QA (Cursor agent) |
| **Disposition** | **REGRESSION PASS** |

## Objective

Formal release regression sign-off for Sovereign Edge on branch `kb112-sovereign-edge` prior to REL-001. Revalidate KB-112 through KB-115, SEC-001 authentication/RBAC, control-plane health, security regression, and VM210 runtime without golden-image bake.

## Environment Baseline

### Git (VM100 `/opt/mssp-control`)

- Branch: `kb112-sovereign-edge`
- HEAD: `87821f1` — `fix(sovereign): harden portal authentication and RBAC`
- Working tree: clean (tracked); untracked docs only (architecture/PM-002B markdown, not code)
- Prior commits under test: `46ff0f7` (KB-113 stabilize), `13b025f` (KB-112–115 tooling)

### Containers (VM100)

| Service | Status |
|---------|--------|
| mssp-backend-api | Up, healthy |
| mssp-postgres | Up, healthy |
| mssp-redis | Up (auth required) |
| mssp-frontend-admin | Up |
| mssp-frontend-customer | Up |

### Health endpoint

```json
{"api":"ok","service":"mssp-backend-api","environment":"development","database":"ok","redis":"ok"}
```

### Host inventory

| VM | IP | Role |
|----|-----|------|
| VM100 | 192.168.0.201 | Control plane |
| VM210 | 192.168.0.226 | Beta / Sovereign appliance |
| pm-server | 192.168.0.238 | OpenProject |

## Test Matrix and Results

| Domain | Script / Suite | Expected | Result |
|--------|----------------|----------|--------|
| Control plane health | `curl /health`, `docker compose ps` | PASS | **PASS** |
| KB-112 foundation | `scripts/kb112_validate_sovereign_edge_foundation.sh` | 14/14 | **14/14 PASS** |
| SEC-001 auth | `backend-api/tests/test_sovereign_portal_auth.py` (host) | 12+ | **13/13 PASS** |
| Sovereign RBAC | `scripts/kb112_validate_sovereign_rbac.sh` | 19/19 | **19/19 PASS** |
| KB-113 logical HA (run 1) | `scripts/kb113_validate_sovereign_ha_failover.sh` | 10/10 | **10/10 PASS** |
| KB-113 logical HA (run 2) | same | 10/10 | **10/10 PASS** |
| KB-114 full stack | `scripts/kb114_validate_sovereign_full_stack.sh` | 19/19 | **19/19 PASS** |
| KB-115 multihost HA | `SOVEREIGN_HA_MODE=alias scripts/kb115_provision_sovereign_ephemeral_ha.sh` | pass | **12/12 PASS** |
| Contamination gate | KB-115 teardown → KB-113 | final 10/10 | **10/10 PASS** |
| Backend unit tests | `docker compose exec backend-api python -m unittest discover -s tests` | pass | **136 passed, 2 skipped** |
| Control-plane API regression | Authenticated curl matrix (validation.env creds) | pass | **PASS** |
| Security regression | Auth tests + header spoof + source grep | pass | **PASS** |
| VM210 runtime | SSH health + portal `/health` | pass | **PASS** |

## Commands Executed

```bash
cd /opt/mssp-control
bash scripts/kb112_validate_sovereign_edge_foundation.sh
bash scripts/kb112_validate_sovereign_rbac.sh
cd backend-api && PYTHONPATH=.:../kevantic-appliance python3 -m unittest tests.test_sovereign_portal_auth -v
bash scripts/kb113_validate_sovereign_ha_failover.sh   # run 1
bash scripts/kb113_validate_sovereign_ha_failover.sh   # run 2
bash scripts/kb114_validate_sovereign_full_stack.sh
SOVEREIGN_HA_MODE=alias bash scripts/kb115_provision_sovereign_ephemeral_ha.sh
bash scripts/kb115_teardown_beta_ha_aliases.sh         # lab cleanup after KB-115
bash scripts/kb113_validate_sovereign_ha_failover.sh   # contamination final
docker compose exec -T backend-api python -m unittest discover -s tests -p 'test_*.py' -q
```

## Failures Encountered and Resolution

### 1. KB-113 post-KB-115 contamination (LAB_STATE)

**Symptom:** After KB-115 alias-mode multihost HA, KB-113 preflight failed — appliance topology remained `multihost`, logical node agents not on 8443/8444.

**Classification:** LAB_STATE (KB-115 alias contamination)

**Resolution:** Ran `scripts/kb115_teardown_beta_ha_aliases.sh`, stopped multihost agents, re-paired `sovereign-logical-cluster`, restarted logical node agents. KB-113 then passed 10/10.

**Product code change:** None.

### 2. KB-010 interactive script (TEST_DEFECT — non-blocking)

**Symptom:** `scripts/kb010_validate_auth_rbac.sh` prompts for passwords and uses stale email `customer.viewer@demo.local` (lab uses `viewer@betawin.com` per `.secrets/validation.env`).

**Classification:** TEST_DEFECT in legacy validator; not a product regression.

**Mitigation:** Control-plane auth validated via `kb112_validate_sovereign_rbac.sh` (19/19) and authenticated API matrix with `validation.env` credentials.

### 3. KB-008 unauthenticated admin endpoints (EXPECTED)

**Symptom:** `kb008_validate_backend_api_foundation.sh` expects unauthenticated `/admin/*` — now returns 401 after auth hardening.

**Classification:** EXPECTED_LIMITATION of legacy KB-008 script post-SEC-001.

**Mitigation:** Authenticated regression confirms SOC manager access 200, anonymous 401.

## Security Results

- Valid JWT accepted; invalid/expired/malformed/forged tokens rejected (13 unit tests)
- `X-Sovereign-Role` header spoof returns 401 (unit + KB-114 live)
- RBAC matrix: platform/soc/customer role boundaries enforced (19 checks)
- No new security findings; Security Status = Not Required
- No secrets committed; evidence excludes credentials

## Fixes and Commits

| Item | Value |
|------|-------|
| Code fixes | None |
| Commits created | None |
| Final HEAD | `87821f1201a8571bdf1696ffe1f6e98d09e8108c` |

## VM210 Runtime (final)

- Hostname: `junexis-appliance-lab-01`
- Unified portal `/health`: `{"ok":true,"service":"sovereign-unified-portal"}`
- Topology after cleanup: `logical_single_host`
- Reachable via appliance SSH key (junexis@192.168.0.226)

## Non-blocking Warnings

- Untracked documentation files in repo (not staged)
- `kb010` / `kb008` legacy validators not updated for post-auth-hardening API (superseded by sovereign + authenticated checks)
- KB-115 executed in alias mode (231/232 on Beta NIC) because ephemeral Proxmox clones 221/222 were unreachable — functionally equivalent per repo script design

## Release Recommendation

**APPROVE** Sovereign Edge branch `kb112-sovereign-edge` at `87821f1` for merge-readiness review. Proceed to REL-001 when release engineering is ready.

REL-001 was **not** executed as part of QA-001.
