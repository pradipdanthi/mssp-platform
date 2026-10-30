#!/usr/bin/env bash
# Disposable end-to-end rig for browser-level checks of TIA's dashboard actions.
#
#   ./scripts/tia_e2e_rig.sh up      start backend (test image) + SOC frontend (vite dev) + seed data
#   ./scripts/tia_e2e_rig.sh down    remove the rig (containers only; the throwaway DB is left to tia_local_test.sh)
#
# LOCAL evidence only: a throwaway Postgres/Redis (tia-test-pg / tia-test-redis, created by
# tia_local_test.sh with KEEP=1), synthetic tenants and alerts, a synthetic operator whose
# password is generated here and written to /tmp/tia-e2e-credentials (mode 600, never printed).
# The SOC agent is NOT started (SOC_AGENT_URL points at a closed port), so model answers are reported
# unavailable by design while tool answers keep working.
# Ports are bound to 127.0.0.1 only. Production containers are never touched.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
NET=tia-test-net
CRED=/tmp/tia-e2e-credentials

case "${1:-}" in
up)
  docker inspect tia-test-pg >/dev/null 2>&1 || { echo "start the throwaway database first: KEEP=1 ./scripts/tia_local_test.sh" >&2; exit 1; }
  docker rm -f tia-e2e-backend tia-e2e-frontend >/dev/null 2>&1 || true
  PW="E2e-$(head -c 18 /dev/urandom | base64 | tr -dc 'A-Za-z0-9' | head -c 20)"
  (umask 077; printf 'email=operator.e2e@example.test\npassword=%s\n' "$PW" > "$CRED")
  # migrations 119-122 are idempotent; apply them in case the DB predates them
  for m in 119_tia_conversation 120_tia_jobs 121_tia_playbooks 122_tia_evidence_effects 123_tia_authorized_scope 124_alert_occurrences; do
    docker exec -i tia-test-pg psql -q -U mssp_admin -d mssp_control < "$ROOT/postgres/init/$m.sql" >/dev/null
  done
  docker run -d --name tia-e2e-backend --network "$NET" --network-alias backend-api -p 127.0.0.1:18000:8000 \
    -e POSTGRES_HOST=tia-test-pg -e POSTGRES_PASSWORD=testpw -e DB_POOL_MIN_SIZE=1 -e DB_POOL_MAX_SIZE=6 \
    -e REDIS_HOST=tia-test-redis -e REDIS_PASSWORD=testpw -e SOC_AGENT_ENABLED=true -e SOC_AGENT_TOKEN=rig-agent-token-unused -e SOC_AGENT_URL=http://127.0.0.1:9 -e SOC_AGENT_ALLOW_INSECURE_HTTP=true -e JWT_SECRET=e2e-only-secret-not-used-elsewhere -e APP_ENV=development \
    -v "$ROOT/backend-api/app:/app/app:ro" -v "$ROOT/kevantic-appliance:/kevantic-appliance:ro" --tmpfs /backend-api:exec,mode=1777 \
    mssp-backend-test uvicorn app.main:app --host 0.0.0.0 --port 8000 >/dev/null
  for i in $(seq 1 40); do curl -fsS http://127.0.0.1:18000/health >/dev/null 2>&1 && break; sleep 1; done
  docker run --rm --network "$NET" -e POSTGRES_HOST=tia-test-pg -e POSTGRES_PASSWORD=testpw -e DB_POOL_MIN_SIZE=1 -e DB_POOL_MAX_SIZE=2 \
    -e E2E_CREDENTIALS_FILE=/cred -v "$CRED:/cred:ro" -v "$ROOT/backend-api/app:/app/app:ro" -v "$ROOT/scripts/tia_e2e_seed.py:/seed.py:ro" \
    mssp-backend-test python /seed.py
  docker run -d --name tia-e2e-frontend --network "$NET" -p 127.0.0.1:15174:5174 -v "$ROOT/frontend-soc:/w:ro" -w /tmp/app node:22-alpine \
    sh -c "cp -r /w/. /tmp/app/ && rm -rf node_modules && npm install --no-audit --no-fund --silent >/dev/null 2>&1 && exec npx vite --host 0.0.0.0 --port 5174" >/dev/null
  for i in $(seq 1 90); do curl -fsS http://127.0.0.1:15174/ >/dev/null 2>&1 && break; sleep 1; done
  curl -fsS http://127.0.0.1:15174/api/health | head -c 200; echo
  echo "rig is up: SOC UI http://127.0.0.1:15174  API http://127.0.0.1:18000  (credentials in $CRED)"
  ;;
agent)
  # Attach a throwaway ingest adapter that talks to production /api/v1/chat only (no production callback).
  # Recreates tia-e2e-backend in place. Does not reseed and does not recreate production containers.
  docker inspect tia-e2e-backend >/dev/null 2>&1 || { echo "start the rig first: $0 up" >&2; exit 1; }
  docker inspect mssp-backend-api >/dev/null 2>&1 || { echo "production backend is not running; cannot reach the live model" >&2; exit 1; }
  UPSTREAM_ENV=/tmp/tia-e2e-upstream.env
  umask 077
  {
    echo "SOC_AGENT_TOKEN=rig-e2e-agent-token-not-production"
    printf 'UPSTREAM_CHAT_URL=%s\n' "$(docker exec mssp-backend-api printenv SOC_AGENT_URL)"
    printf 'UPSTREAM_TOKEN=%s\n' "$(docker exec mssp-backend-api printenv SOC_AGENT_TOKEN)"
  } > "$UPSTREAM_ENV"
  docker rm -f tia-e2e-agent >/dev/null 2>&1 || true
  docker run -d --name tia-e2e-agent --network "$NET" --network-alias tia-e2e-agent \
    --env-file "$UPSTREAM_ENV" -v "$ROOT/scripts/tia_e2e_agent.py:/agent.py:ro" \
    python:3.12-alpine python /agent.py >/dev/null
  for i in $(seq 1 20); do docker exec tia-e2e-agent wget -q -O- http://127.0.0.1:8080/health >/dev/null 2>&1 && break; sleep 1; done
  docker rm -f tia-e2e-backend >/dev/null 2>&1 || true
  docker run -d --name tia-e2e-backend --network "$NET" --network-alias backend-api -p 127.0.0.1:18000:8000 \
    -e POSTGRES_HOST=tia-test-pg -e POSTGRES_PASSWORD=testpw -e DB_POOL_MIN_SIZE=1 -e DB_POOL_MAX_SIZE=6 \
    -e REDIS_HOST=tia-test-redis -e REDIS_PASSWORD=testpw -e SOC_AGENT_ENABLED=true \
    -e SOC_AGENT_TOKEN=rig-e2e-agent-token-not-production -e SOC_AGENT_URL=http://tia-e2e-agent:8080 \
    -e SOC_AGENT_ALLOW_INSECURE_HTTP=true -e SOC_AGENT_TIMEOUT_SECONDS=120 \
    -e JWT_SECRET=e2e-only-secret-not-used-elsewhere -e APP_ENV=development \
    -v "$ROOT/backend-api/app:/app/app:ro" -v "$ROOT/kevantic-appliance:/kevantic-appliance:ro" --tmpfs /backend-api:exec,mode=1777 \
    mssp-backend-test uvicorn app.main:app --host 0.0.0.0 --port 8000 >/dev/null
  for i in $(seq 1 40); do curl -fsS http://127.0.0.1:18000/health >/dev/null 2>&1 && break; sleep 1; done
  echo "throwaway agent attached: e2e backend -> tia-e2e-agent:8080 -> production chat (no production callback)"
  ;;
down)
  docker rm -f tia-e2e-backend tia-e2e-frontend tia-e2e-agent >/dev/null 2>&1 || true
  rm -f "$CRED" /tmp/tia-e2e-upstream.env
  echo "rig removed"
  ;;
*) echo "usage: $0 up|down|agent" >&2; exit 2;;
esac
