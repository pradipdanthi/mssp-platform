# Disaster Recovery Playbook — MSSP Control Plane (VM 100)

Status: Operational blueprint for full control-plane rebuild.  
Created: 2026-07-31 · Synced with Phase 6 (Threat Intelligence) commit baseline.  
Audience: Platform operators restoring `/opt/mssp-control` after host loss, volume corruption, or greenfield rebuild.

**Source of truth:** Git commits/tags and live validation beat stale prose. Never commit `.env` or `.secrets/`.

---

## 0. Git sync audit (2026-07-31)

### Working tree

| Check | Result |
|---|---|
| Branch | `main` |
| Working tree | **Clean** (nothing uncommitted at audit time) |
| HEAD (Phase 6) | `73a3f42` — Threat Intelligence & Enrichment |
| Remote | `git@github.com:pradipdanthi/mssp-platform.git` (local may be ahead of `origin/main`) |

### Schema migrations `021`–`027` (tracked in Git)

| File | Feature |
|---|---|
| `postgres/init/021_service_consultation_requests.sql` | Service consultation requests |
| `postgres/init/022_continuous_compliance_sca.sql` | Continuous Compliance (CaaS / SCA) |
| `postgres/init/023_easm_attack_surface.sql` | External Attack Surface (EASM) |
| `postgres/init/024_cloud_itdr_identity.sql` | Cloud & Identity (ITDR) |
| `postgres/init/025_vulnerability_management_vmaas.sql` | Vulnerability Management (VMaaS) |
| `postgres/init/026_network_detection_response_ndr.sql` | Network Detection & Response (NDR) |
| `postgres/init/027_threat_intelligence_enrichment.sql` | Threat Intelligence & Enrichment |

### Service workers (tracked)

- `backend-api/app/services/compliance_service.py` (Phase 1)
- `backend-api/app/services/easm_service.py` (Phase 2)
- `backend-api/app/services/itdr_service.py` (Phase 3)
- `backend-api/app/services/vmaas_service.py` (Phase 4)
- `backend-api/app/services/ndr_service.py` (Phase 5)
- `backend-api/app/services/threat_intel_service.py` (Phase 6)

### Customer portal routes (tracked)

| Path | Page |
|---|---|
| `/compliance` | Continuous Compliance |
| `/easm` | Attack Surface |
| `/itdr` | Cloud & Identity |
| `/vulnerabilities` | Vulnerability Management |
| `/ndr`, `/network` | Network Detection & Response |
| `/threat-intel` | Threat Intelligence |

**Not in Git (must restore from secure backup separately):** `.env`, `.secrets/*`, Docker named volumes (`postgres_data`, `redis_data`), optional `runtime/vuln-free/`.

---

## 1. Required host dependencies

### Control plane host (VM 100)

| Dependency | Notes |
|---|---|
| Linux (Ubuntu 22.04/24.04 or equivalent) | Production path historically `192.168.0.201` |
| Docker Engine | Validated on Docker 29.x |
| Docker Compose plugin | `docker compose` v2+ (validated v5.x) |
| Git | Clone / pull |
| curl, jq, openssl | Health checks and secret generation |
| bash | Validation scripts under `scripts/` |

Optional on host (only if developing outside containers):

| Dependency | Notes |
|---|---|
| Python 3.12 | Matches `backend-api/Dockerfile` (`python:3.12-slim`) |
| Node.js 20 + npm | Matches frontend Dockerfiles (`node:20-alpine`) |

### Compose images (pulled/built automatically)

| Service | Image / build |
|---|---|
| `postgres` | `postgres:16-alpine` |
| `redis` | `redis:7-alpine` |
| `backend-api` | Build `./backend-api` (Python 3.12 + `requirements.txt`) |
| `frontend-admin` | Build `./frontend-admin` (Node 20 → nginx 1.27) |
| `frontend-customer` | Build `./frontend-customer` (Node 20 → nginx 1.27) |

### Python packages (backend image)

Pinned in `backend-api/requirements.txt`:

- `fastapi==0.115.6`
- `uvicorn[standard]==0.34.0`
- `psycopg[binary]==3.2.3`
- `psycopg_pool==3.2.4`
- `redis==5.2.1`
- `pydantic==2.10.4`
- `bcrypt==4.2.1`
- `PyJWT==2.10.1`
- `reportlab==4.2.5`
- `openpyxl==3.1.5`
- `boto3==1.35.0`

### Published ports

| Port | Service |
|---|---|
| `${API_PORT}` → 8000 | FastAPI (`mssp-backend-api`) |
| `3000` | Admin / SOC portal |
| `3001` | Customer portal |

### Related engine VMs (adapters — not this compose file)

Restore or reconnect separately (Ansible under `ansible/` when a named KB applies):

| Role | Typical host |
|---|---|
| Wazuh | VM 101 |
| TheHive / Shuffle | VM 102 |
| Suricata | VM 106 |
| Nuclei / Vuls / Greenbone CE | VM 109 |

---

## 2. Git clone and environment setup

### 2.1 Clone

```bash
sudo mkdir -p /opt
sudo chown "$USER:$USER" /opt
cd /opt
git clone git@github.com:pradipdanthi/mssp-platform.git mssp-control
cd /opt/mssp-control
git checkout main
git pull --ff-only
git log -1 --oneline
```

HTTPS alternative (if SSH keys unavailable):

```bash
git clone https://github.com/pradipdanthi/mssp-platform.git mssp-control
```

### 2.2 Create `.env` (never commit)

Create `/opt/mssp-control/.env` with at least:

```bash
# Core
APP_ENV=production
TZ=Asia/Kolkata
API_PORT=8000

# PostgreSQL
POSTGRES_DB=mssp_control
POSTGRES_USER=mssp_admin
POSTGRES_PASSWORD=<STRONG_RANDOM_PASSWORD>

# Redis
REDIS_PASSWORD=<STRONG_RANDOM_PASSWORD>

# Auth
JWT_SECRET=<LONG_RANDOM_SECRET>
JWT_ALGORITHM=HS256

# Optional integrations (defaults exist in compose)
THEHIVE_URL=http://192.168.0.212:9000
THEHIVE_USER=admin@thehive.local
THEHIVE_DEFAULT_ORG=MSSP
WAZUH_API_URL=https://192.168.0.211:55000
WAZUH_API_VERIFY_TLS=false
# Leave empty for fail-closed tenant mapping:
WAZUH_DEFAULT_TENANT_SHORT_CODE=

ADMIN_PORTAL_BASE_URL=http://192.168.0.201:3000
RESEND_API_KEY=
RESEND_FROM_EMAIL=MSSP Control Plane <onboarding@resend.dev>
SALES_NOTIFY_EMAIL=sales@example.com
```

Generate secrets without printing them to chat logs:

```bash
openssl rand -base64 48   # JWT_SECRET / passwords
```

### 2.3 Create `.secrets/` files (never commit)

Compose mounts these as Docker secrets:

```bash
mkdir -p /opt/mssp-control/.secrets
chmod 700 /opt/mssp-control/.secrets

# One secret per file (no trailing newline preferred for tokens):
#   soc_sync_api_key
#   wazuh_ingress_token
#   shuffle_webhook_url
#   vuln_sync_api_key
#   thehive_password
#   wazuh_api_user
#   wazuh_api_password
#
# Optional (if used by other modules):
#   greenbone_hook_token
#   edr_callback_api_key

chmod 600 /opt/mssp-control/.secrets/*
```

Restore these from the offline secrets vault / previous host backup — **do not invent production tokens** unless rotating every integration endpoint.

### 2.4 Permissions

```bash
cd /opt/mssp-control
chmod 600 .env
chmod 700 .secrets
```

---

## 3. Database restore order

PostgreSQL mounts `./postgres/init` → `/docker-entrypoint-initdb.d` **only on first start of an empty `postgres_data` volume**. Scripts run in **lexical filename order**.

### 3.1 Fresh volume (automatic)

1. Ensure `postgres_data` volume does not exist (or is empty).
2. `docker compose up -d postgres` (or full stack).
3. Init scripts `001` … `027` apply automatically in this order:

```
001_mssp_core_schema.sql
002_kb010_auth_rbac.sql
003_kb016_appliance_registration_heartbeat.sql
004_kb069_vulnerabilities.sql
005_kb071_tenant_entitlements.sql
006_kb071b_entitlement_roadmap_modules.sql
007_kb072_tenant_engine_bindings.sql
008_kb073_tenant_deployment_mode.sql
009_kb073b_cloud_appliance_mode.sql
010_kb074_tenant_customer_profile.sql
011_kb075_contract_ready_onboarding.sql
012_kb076_service_upgrade_requests.sql
013_kb079_vuln_scan_scheduler.sql
014_kb083_edr_actions.sql
015_kb084_edr_lifecycle_forensics.sql
016_kb085_audit_enrichment.sql
017_kb086_asset_type_folders.sql
018_kb086_service_catalog_keys.sql
019_kb086_asset_service_coverage.sql
020_kb086_agent_install_tokens.sql
021_service_consultation_requests.sql
022_continuous_compliance_sca.sql
023_easm_attack_surface.sql
024_cloud_itdr_identity.sql
025_vulnerability_management_vmaas.sql
026_network_detection_response_ndr.sql
027_threat_intelligence_enrichment.sql
```

### 3.2 Existing volume missing later migrations

If the DB already has data but is missing newer DDL (common after code pull on a long-lived volume), apply **only the missing files** in order:

```bash
cd /opt/mssp-control
for f in postgres/init/02{1,2,3,4,5,6,7}_*.sql; do
  echo "Applying $f"
  docker compose exec -T postgres \
    psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1 -f - < "$f"
done
```

(Use the same user/db names as in `.env`. Scripts are written to be idempotent with `IF NOT EXISTS` where practical.)

### 3.3 Full logical backup restore (preferred for true DR)

From a prior host:

```bash
# On source (example)
docker compose exec -T postgres \
  pg_dump -U mssp_admin -d mssp_control -Fc > /secure/backup/mssp_control.dump

# On target after empty volume + containers healthy
docker compose exec -T postgres \
  pg_restore -U mssp_admin -d mssp_control --clean --if-exists < /secure/backup/mssp_control.dump
```

After restore, verify schema presence:

```bash
docker compose exec -T postgres \
  psql -U mssp_admin -d mssp_control -c "\dt tenant_*"
```

Expect tables including (non-exhaustive): `tenant_compliance_*`, `tenant_easm_*`, `tenant_cloud_identity_*`, `tenant_vulnerability_*`, `tenant_ndr_*`, `tenant_threat_intel_*`.

### 3.4 Seed data

`postgres/seed/dev/` is for non-production seeding only. Production tenants/users come from backup restore or Admin onboarding — do not assume seed scripts recreate live customers.

---

## 4. Docker container spin-up

### 4.1 Build and start entire control plane

```bash
cd /opt/mssp-control
docker compose pull postgres redis
docker compose up -d --build
docker compose ps
```

Expected containers:

- `mssp-postgres` (healthy)
- `mssp-redis` (healthy)
- `mssp-backend-api`
- `mssp-frontend-admin`
- `mssp-frontend-customer`

### 4.2 After API or frontend code changes

Always recreate **backend + both frontends** together (avoids stale nginx upstream IPs):

```bash
cd /opt/mssp-control
docker compose up -d --build --force-recreate backend-api frontend-admin frontend-customer
```

### 4.3 Smoke checks

```bash
curl -fsS http://localhost:8000/health | jq .
curl -sS -o /dev/null -w "%{http_code}\n" -X POST http://localhost:3000/api/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"x","password":"y"}'   # expect 401, not 502/405
curl -sS -o /dev/null -w "%{http_code}\n" -X POST http://localhost:3001/api/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"x","password":"y"}'   # expect 401, not 502/405
```

Regression scripts (examples):

```bash
cd /opt/mssp-control
./scripts/kb011_validate_protected_apis.sh
./scripts/kb036_validate_mssp_platform_architecture_roadmap.sh
```

### 4.4 Re-hydrate service-engine sample/live sync (optional)

After a schema-only restore, Admin can refresh Phase engines per tenant:

```text
POST /admin/compliance/{tenant_ref}/sync   # Phase 1 (if route present)
POST /admin/easm/{tenant_ref}/sync         # Phase 2
POST /admin/itdr/{tenant_ref}/sync         # Phase 3
POST /admin/vmaas/{tenant_ref}/sync        # Phase 4
POST /admin/ndr/{tenant_ref}/sync          # Phase 5
POST /admin/threat-intel/{tenant_ref}/sync # Phase 6
```

(Exact paths match deployed OpenAPI; use Admin JWT.)

---

## 5. What to back up regularly (DR checklist)

| Asset | Frequency | Location |
|---|---|---|
| Git remote (`main` + tags) | Continuous | GitHub |
| PostgreSQL dump (`pg_dump -Fc`) | Daily + pre-upgrade | Offline / encrypted store |
| Redis AOF/RDB (optional) | Daily | Usually rebuildable; queue state may be lost |
| `.env` | On change | Secrets vault only |
| `.secrets/*` | On change | Secrets vault only |
| Proxmox VM snapshot (VM 100) | Weekly / pre-major change | Hypervisor |
| Engine VM configs (101–109) | Per KB change | Ansible + snapshots |

---

## 6. Failure modes (quick triage)

| Symptom | Likely cause | Action |
|---|---|---|
| Customer login `502` | Stale frontend upstream after API recreate | Recreate both frontends |
| Empty schema / missing Phase tables | Volume reused without migrations | Apply `021`–`027` manually in order |
| Auth fails for everyone | Wrong `JWT_SECRET` vs prior tokens | Restore original secret or force re-login after rotate |
| Integrations 401 | Missing/rotated `.secrets` files | Restore secret files; restart `backend-api` |
| Init scripts did nothing | Volume already initialized | Manual `psql -f` path (section 3.2) |

---

## 7. Related docs

- `AGENTS.md` — security, tenant isolation, commit rules
- `CONTEXT.md` — current validated baseline
- `docs/SERVICE_ENGINE_DEVELOPMENT_ROADMAP.md` — catalog Phase 1–6 status
- `docs/KB036_MSSP_PLATFORM_ARCHITECTURE_ROADMAP.md` — enterprise architecture
- `README.md` — repository layout

---

## 8. Post-restore acceptance

Mark DR complete only when all are true:

1. `docker compose ps` shows five core containers healthy/up.
2. `GET /health` reports database + Redis OK.
3. Admin `:3000` and Customer `:3001` login paths return auth errors (not gateway errors) for bad credentials.
4. Schema includes tables through `027` (threat intel).
5. At least one known tenant can open prior Phase UIs (`/compliance` … `/threat-intel`) without 5xx.
6. `.env` / `.secrets` remain untracked (`git status` clean; secrets never staged).
