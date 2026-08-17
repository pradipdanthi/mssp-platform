#!/usr/bin/env bash
# production_deploy_control_plane.sh — KB-094 control plane deploy + smoke (lab or production).
# Safe to re-run. Does not touch engine VMs or appliances.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

log() { printf '[production_deploy] %s\n' "$*"; }
die() { log "ERROR: $*"; exit 1; }

command -v docker >/dev/null 2>&1 || die "docker not installed"
docker compose version >/dev/null 2>&1 || die "docker compose plugin missing"
[[ -f .env ]] || die ".env missing — copy deploy/environments/control-plane.lab.example.env or control-plane.production.example.env"

if grep -q '^APP_ENV=production' .env 2>/dev/null; then
  log "APP_ENV=production — ensure demo seed was NOT applied (KB-020)"
fi

# Required keys (presence only — never print values)
for key in POSTGRES_PASSWORD REDIS_PASSWORD JWT_SECRET POSTGRES_DB POSTGRES_USER; do
  grep -q "^${key}=" .env || die ".env missing ${key}= (see deploy/environments/)"
  if grep -q "^${key}=<REQUIRED>" .env 2>/dev/null; then
    die ".env still has placeholder ${key}=<REQUIRED>"
  fi
done

SECRET_STUBS=(
  soc_sync_api_key
  wazuh_ingress_token
  wazuh_api_user
  wazuh_api_password
  thehive_password
)
mkdir -p .secrets
for f in "${SECRET_STUBS[@]}"; do
  if [[ ! -s ".secrets/${f}" ]]; then
    log "WARN: .secrets/${f} missing or empty — some adapters may fail until populated"
  fi
done

BUILD_OPTS=(--build)
if [[ "${MSSP_FORCE_REBUILD:-}" == "1" ]]; then
  log "MSSP_FORCE_REBUILD=1 — no-cache rebuild of backend + frontends"
  docker compose build --no-cache backend-api frontend-admin frontend-customer
fi

log "Starting postgres + redis (if needed)"
docker compose up -d postgres redis

log "Building and recreating backend-api + both frontends"
docker compose up -d "${BUILD_OPTS[@]}" --force-recreate backend-api frontend-admin frontend-customer

log "Waiting for API health"
ok=0
for _ in $(seq 1 45); do
  if curl -fsS -m 3 http://127.0.0.1:8000/health >/dev/null 2>&1; then
    ok=1
    break
  fi
  sleep 2
done
[[ "$ok" -eq 1 ]] || die "API /health did not become ready"

if command -v jq >/dev/null 2>&1; then
  curl -fsS http://127.0.0.1:8000/health | jq -c .
else
  curl -fsS http://127.0.0.1:8000/health
  echo
fi

admin_home="$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:3000/)"
customer_home="$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:3001/)"
admin_login="$(curl -s -o /dev/null -w '%{http_code}' -X POST http://127.0.0.1:3000/api/auth/login \
  -H 'Content-Type: application/json' -d '{"email":"bad@example.com","password":"wrong"}')"
customer_login="$(curl -s -o /dev/null -w '%{http_code}' -X POST http://127.0.0.1:3001/api/auth/login \
  -H 'Content-Type: application/json' -d '{"email":"bad@example.com","password":"wrong"}')"

log "Smoke: admin_home=${admin_home} customer_home=${customer_home} admin_login=${admin_login} customer_login=${customer_login}"

[[ "$admin_home" == "200" && "$customer_home" == "200" ]] || die "portal home page not 200"
[[ "$admin_login" == "401" && "$customer_login" == "401" ]] || die "login proxy expected 401 not 502/405"

log "OK — control plane deploy smoke passed"
log "Next: ./scripts/kb011_validate_protected_apis.sh (needs lab credentials) or production bootstrap (KB-020)"
