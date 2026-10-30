#!/usr/bin/env bash
# Reproducible LOCAL test run for TIA (throwaway containers, synthetic data).
# This is local evidence only. It is not staging verification and touches no VM.
#
#   ./scripts/tia_local_test.sh            # backend + agent + migrations (+ frontend build if node image available)
#   KEEP=1 ./scripts/tia_local_test.sh     # leave the throwaway containers for inspection
#
# Never run against production: every container is named tia-test*, there is no
# access to .env or .secrets, and the backend code is mounted read-only.
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
NET=tia-test-net
PG=tia-test-pg
RD=tia-test-redis
IMG=mssp-backend-test
FAILED=0

cleanup() { [[ "${KEEP:-0}" == 1 ]] || { docker rm -f "$PG" "$RD" >/dev/null 2>&1; docker network rm "$NET" >/dev/null 2>&1; }; }
trap cleanup EXIT

step() { echo; echo "=== $*"; }
note_fail() { FAILED=$((FAILED + 1)); echo "FAILED: $*"; }

step "build test image (production requirements + backend-api/requirements-test.txt)"
docker build -q -t "$IMG" -f "$ROOT/backend-api/Dockerfile.test" "$ROOT/backend-api" >/dev/null || { echo "image build failed"; exit 2; }

step "throwaway Postgres and Redis"
docker rm -f "$PG" "$RD" >/dev/null 2>&1
docker network inspect "$NET" >/dev/null 2>&1 || docker network create "$NET" >/dev/null
docker run -d --name "$PG" --network "$NET" -e POSTGRES_USER=mssp_admin -e POSTGRES_PASSWORD=testpw -e POSTGRES_DB=mssp_control postgres:16-alpine >/dev/null
docker run -d --name "$RD" --network "$NET" redis:7-alpine redis-server --appendonly yes --requirepass testpw >/dev/null
for _ in $(seq 1 30); do docker exec "$PG" pg_isready -U mssp_admin -d mssp_control >/dev/null 2>&1 && break; sleep 1; done
sleep 2
for f in $(ls "$ROOT"/postgres/init/*.sql | sort); do
  docker exec -i "$PG" psql -q -U mssp_admin -d mssp_control < "$f" >/dev/null 2>&1 || true
done
docker exec "$PG" psql -U mssp_admin -d mssp_control -Atc "select 'schema_version', version from tia_schema_version" || note_fail "TIA schema not initialised"

run_backend() { # run_backend <label> <extra docker args...>
  local label="$1"; shift
  step "backend tests: $label"
  docker run --rm --network "$NET" -e POSTGRES_HOST="$PG" -e POSTGRES_PASSWORD=testpw \
    -e DB_POOL_MIN_SIZE=1 -e DB_POOL_MAX_SIZE=4 -e REDIS_HOST="$RD" -e REDIS_PASSWORD=testpw -e JWT_SECRET=test \
    -v "$ROOT/backend-api/app:/app/app:ro" -v "$ROOT/backend-api/tests:/app/tests:ro" -v "$ROOT/scripts:/scripts:ro" "$@" \
    "$IMG" python -m unittest discover -s tests -p 'test_*.py' 2>&1 | tee "/tmp/tia_${label// /_}.log" | grep -E "^(Ran|OK|FAILED|ERROR:|FAIL:)"
  return "${PIPESTATUS[0]}"
}
run_backend "with appliance modules" -v "$ROOT/kevantic-appliance:/kevantic-appliance:ro" --tmpfs /backend-api:exec,mode=1777 || note_fail "backend suite (with appliance modules)"
run_backend "default setup" || echo "(default setup excludes the sovereign modules; see docs/TIA_INVESTIGATION_STATUS.md)"

step "agent tests"
docker run --rm -v "$ROOT/soc-agent:/a" -w /a python:3.12-slim sh -c "pip install -q -r requirements.txt >/dev/null 2>&1; python -m unittest discover -s tests 2>&1 | tail -4" || note_fail "agent tests"

step "migration validation"
"$ROOT/scripts/tia_migration_validate.sh" "$PG" 2>&1 | tail -3 || note_fail "migration validation"

echo
[[ $FAILED -eq 0 ]] && echo "TIA LOCAL RUN: no gate failed (local evidence only)" || { echo "TIA LOCAL RUN: $FAILED gate(s) failed"; exit 1; }
