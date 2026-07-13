#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="/opt/mssp-control"

cd "$PROJECT_DIR"

echo "======================================================================"
echo "KB-008: Validate Backend API Foundation"
echo "Mode: READ-ONLY validation"
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

section "1. File and folder checks"

[ -d backend-api ] || fail "backend-api directory missing"
[ -f backend-api/Dockerfile ] || fail "backend-api/Dockerfile missing"
[ -f backend-api/requirements.txt ] || fail "backend-api/requirements.txt missing"
[ -f backend-api/app/main.py ] || fail "backend-api/app/main.py missing"
[ -f docker-compose.yml ] || fail "docker-compose.yml missing"

echo "backend-api directory exists"
echo "Dockerfile exists"
echo "requirements.txt exists"
echo "app/main.py exists"
echo "docker-compose.yml exists"

section "2. Docker Compose and service health"

docker compose config >/tmp/kb008-validation-compose.txt
echo "Docker Compose syntax: OK"

docker compose ps

backend_state="$(docker inspect -f '{{.State.Status}}' mssp-backend-api 2>/dev/null || echo 'missing')"
postgres_health="$(docker inspect -f '{{.State.Health.Status}}' mssp-postgres 2>/dev/null || echo 'missing')"
redis_health="$(docker inspect -f '{{.State.Health.Status}}' mssp-redis 2>/dev/null || echo 'missing')"

echo
echo "mssp-backend-api state: $backend_state"
echo "mssp-postgres health:   $postgres_health"
echo "mssp-redis health:      $redis_health"

[ "$backend_state" = "running" ] || fail "backend-api container is not running"
[ "$postgres_health" = "healthy" ] || fail "postgres is not healthy"
[ "$redis_health" = "healthy" ] || fail "redis is not healthy"

section "3. API health endpoint"

health_json="$(curl -fsS http://localhost:8000/health)"
echo "$health_json" | jq .

echo "$health_json" | jq -e '.api == "ok"' >/dev/null || fail "API health is not ok"
echo "$health_json" | jq -e '.database == "ok"' >/dev/null || fail "Database health is not ok"
echo "$health_json" | jq -e '.redis == "ok"' >/dev/null || fail "Redis health is not ok"

section "4. Admin API endpoint checks"

echo "GET /admin/dashboard"
curl -fsS http://localhost:8000/admin/dashboard | jq .
curl -fsS http://localhost:8000/admin/dashboard | jq -e '.overview.total_tenants >= 1' >/dev/null || fail "Admin dashboard tenant count invalid"
curl -fsS http://localhost:8000/admin/dashboard | jq -e '.overview.total_incidents >= 1' >/dev/null || fail "Admin dashboard incident count invalid"

echo
echo "GET /admin/tenants"
curl -fsS http://localhost:8000/admin/tenants | jq .
curl -fsS http://localhost:8000/admin/tenants | jq -e '.tenants | length >= 1' >/dev/null || fail "Admin tenants endpoint returned no tenants"

echo
echo "GET /admin/appliances"
curl -fsS http://localhost:8000/admin/appliances | jq .
curl -fsS http://localhost:8000/admin/appliances | jq -e '.appliances | length >= 1' >/dev/null || fail "Admin appliances endpoint returned no appliances"

echo
echo "GET /admin/alerts"
curl -fsS http://localhost:8000/admin/alerts | jq .
curl -fsS http://localhost:8000/admin/alerts | jq -e '.alerts | length >= 1' >/dev/null || fail "Admin alerts endpoint returned no alerts"

echo
echo "GET /admin/incidents"
curl -fsS http://localhost:8000/admin/incidents | jq .
curl -fsS http://localhost:8000/admin/incidents | jq -e '.incidents | length >= 1' >/dev/null || fail "Admin incidents endpoint returned no incidents"

section "5. Customer API endpoint checks"

echo "GET /customer/dashboard/DEMO"
curl -fsS http://localhost:8000/customer/dashboard/DEMO | jq .
curl -fsS http://localhost:8000/customer/dashboard/DEMO | jq -e '.tenant.short_code == "DEMO"' >/dev/null || fail "Customer dashboard tenant mismatch"
curl -fsS http://localhost:8000/customer/dashboard/DEMO | jq -e '.open_incidents | length >= 1' >/dev/null || fail "Customer dashboard returned no open incidents"

echo
echo "GET /customer/incidents/DEMO"
curl -fsS http://localhost:8000/customer/incidents/DEMO | jq .
curl -fsS http://localhost:8000/customer/incidents/DEMO | jq -e '.incidents | length >= 1' >/dev/null || fail "Customer incidents endpoint returned no incidents"

section "6. API documentation endpoint"

curl -fsS http://localhost:8000/docs >/tmp/kb008-docs.html
test -s /tmp/kb008-docs.html || fail "FastAPI docs page is empty"
echo "FastAPI docs endpoint is reachable: http://localhost:8000/docs"

section "7. Final validation verdict"

echo "KB-008 BACKEND API FOUNDATION VALIDATION PASSED"
echo
echo "LAN URLs:"
echo "  http://192.168.0.201:8000/health"
echo "  http://192.168.0.201:8000/docs"
echo "  http://192.168.0.201:8000/admin/dashboard"
echo "  http://192.168.0.201:8000/customer/dashboard/DEMO"
echo
echo "======================================================================"
echo "KB-008 validation completed successfully."
echo "======================================================================"
