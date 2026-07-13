#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="/opt/mssp-control"
API_BASE="http://localhost:8000"
BODY_FILE="/tmp/kb012-body.json"

cd "$PROJECT_DIR"

echo "======================================================================"
echo "KB-012: Validate Backend API Route Modularization"
echo "Target: $PROJECT_DIR"
echo "======================================================================"

fail() {
  echo
  echo "VALIDATION FAILED: $1"
  echo "Recent backend-api logs:"
  docker compose logs --tail=80 backend-api || true
  exit 1
}

section() {
  echo
  echo "----------------------------------------------------------------------"
  echo "$1"
  echo "----------------------------------------------------------------------"
}

cleanup() {
  rm -f "$BODY_FILE"
}
trap cleanup EXIT

# check_status <description> <expected_http_code> <url>
check_status() {
  local description="$1"
  local expected="$2"
  local url="$3"
  local actual

  actual="$(curl -s -o "$BODY_FILE" -w '%{http_code}' "$url")"

  if [ "$actual" = "$expected" ]; then
    echo "OK   [$actual] $description"
  else
    echo "FAIL [$actual, expected $expected] $description"
    echo "Response body:"
    cat "$BODY_FILE" 2>/dev/null || true
    echo
    fail "$description expected HTTP $expected but got $actual"
  fi
}

section "1. New route files must exist"

for f in \
  backend-api/app/api/routes/health.py \
  backend-api/app/api/routes/admin.py \
  backend-api/app/api/routes/customer.py
do
  [ -f "$f" ] || fail "$f is missing - KB-012 modularization was not completed"
  echo "found: $f"
done

section "2. main.py must contain no route decorators"

if grep -qE '@app\.(get|post|put|patch|delete)\(' backend-api/app/main.py; then
  fail "backend-api/app/main.py still contains an @app.<method>(...) route decorator - route logic was not fully moved out"
fi
echo "OK: main.py has no @app.get / @app.post / etc. route decorators"

section "3. main.py must include all expected routers"

for router_name in auth_router health_router admin_router customer_router; do
  grep -q "app.include_router($router_name)" backend-api/app/main.py \
    || fail "backend-api/app/main.py does not call app.include_router($router_name)"
  echo "OK: main.py includes $router_name"
done

section "4. Docker Compose and service health"

docker compose ps

backend_state="$(docker inspect -f '{{.State.Status}}' mssp-backend-api 2>/dev/null || echo 'missing')"
postgres_health="$(docker inspect -f '{{.State.Health.Status}}' mssp-postgres 2>/dev/null || echo 'missing')"
redis_health="$(docker inspect -f '{{.State.Health.Status}}' mssp-redis 2>/dev/null || echo 'missing')"

echo
echo "mssp-backend-api state: $backend_state"
echo "mssp-postgres health:   $postgres_health"
echo "mssp-redis health:      $redis_health"

[ "$backend_state" = "running" ] || fail "backend-api container is not running (did you rebuild it after this change?)"
[ "$postgres_health" = "healthy" ] || fail "postgres is not healthy"
[ "$redis_health" = "healthy" ] || fail "redis is not healthy"

section "5. GET /health must still work and be public"

check_status "GET /health (public, no token)" 200 "$API_BASE/health"
db_status="$(jq -r '.database' "$BODY_FILE")"
redis_status="$(jq -r '.redis' "$BODY_FILE")"
echo "  database: $db_status"
echo "  redis:    $redis_status"
[ "$db_status" = "ok" ] || fail "GET /health reported database status '$db_status', expected 'ok'"
[ "$redis_status" = "ok" ] || fail "GET /health reported redis status '$redis_status', expected 'ok'"

section "6. GET /auth/roles must still work and be public"

check_status "GET /auth/roles (public, no token)" 200 "$API_BASE/auth/roles"
role_count="$(jq '.roles | length' "$BODY_FILE")"
echo "  roles returned: $role_count"
[ "$role_count" = "5" ] || fail "GET /auth/roles returned $role_count roles, expected 5"

section "7. GET /openapi.json must still list every expected path"

check_status "GET /openapi.json" 200 "$API_BASE/openapi.json"

EXPECTED_PATHS=(
  "/"
  "/health"
  "/auth/login"
  "/auth/me"
  "/auth/roles"
  "/admin/dashboard"
  "/admin/tenants"
  "/admin/appliances"
  "/admin/alerts"
  "/admin/incidents"
  "/customer/dashboard/{short_code}"
  "/customer/incidents/{short_code}"
)

for p in "${EXPECTED_PATHS[@]}"; do
  jq -e --arg p "$p" '.paths | has($p)' "$BODY_FILE" >/dev/null \
    || fail "GET /openapi.json is missing expected path: $p"
  echo "OK: openapi.json has path $p"
done

section "8. Behavior regression gate: scripts/kb011_validate_protected_apis.sh"

echo "Running the full, unmodified KB-011 validation script now."
echo "This re-checks every /admin/* and /customer/* endpoint across all 5"
echo "roles (401/403/404/200) plus the public endpoints and password_hash"
echo "leak checks. It will ask you for the 5 demo passwords again."
echo

if ! ./scripts/kb011_validate_protected_apis.sh; then
  fail "scripts/kb011_validate_protected_apis.sh did not pass after route modularization - behavior changed, this is a real regression"
fi

section "9. Final validation verdict"

echo "KB-012 ROUTE MODULARIZATION VALIDATION PASSED"
echo
echo "Summary:"
echo "  - backend-api/app/api/routes/health.py, admin.py, customer.py all exist."
echo "  - backend-api/app/main.py has no route decorators and includes all 4 routers."
echo "  - GET /health and GET /auth/roles remain public and working."
echo "  - /openapi.json still lists all 12 expected paths with unchanged URLs."
echo "  - scripts/kb011_validate_protected_apis.sh passed unmodified - no observable"
echo "    behavior change to auth, RBAC, or tenant isolation."
echo
echo "======================================================================"
echo "KB-012 validation completed successfully."
echo "======================================================================"
