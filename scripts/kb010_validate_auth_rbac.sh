#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="/opt/mssp-control"
API_BASE="http://localhost:8000"

cd "$PROJECT_DIR"

echo "======================================================================"
echo "KB-010: Validate Auth/RBAC Foundation"
echo "Mode: Phase 1 only (existing /admin and /customer endpoints unchanged)"
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
  rm -f /tmp/kb010-wrong-login.json
  unset SOC_PASSWORD CUST_PASSWORD SOC_TOKEN CUST_TOKEN 2>/dev/null || true
}
trap cleanup EXIT

section "1. File and folder checks"

for f in \
  backend-api/app/core/config.py \
  backend-api/app/core/security.py \
  backend-api/app/db/session.py \
  backend-api/app/api/dependencies.py \
  backend-api/app/api/routes/auth.py \
  backend-api/app/schemas/auth.py \
  backend-api/app/services/auth_service.py \
  postgres/init/002_kb010_auth_rbac.sql \
  scripts/kb010_create_auth_rbac.sh
do
  [ -f "$f" ] || fail "$f is missing"
  echo "found: $f"
done

grep -q "bcrypt" backend-api/requirements.txt || fail "bcrypt missing from backend-api/requirements.txt"
grep -q "PyJWT" backend-api/requirements.txt || fail "PyJWT missing from backend-api/requirements.txt"
echo "requirements.txt has bcrypt and PyJWT"

section "2. Docker Compose and service health"

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

section "3. Public /health endpoint (must work WITHOUT a token)"

health_json="$(curl -fsS "$API_BASE/health")"
echo "$health_json" | jq .
echo "$health_json" | jq -e '.api == "ok"' >/dev/null || fail "/health did not report ok"

section "4. Enter demo passwords to test login (input hidden, never logged)"

read -rs -p "Enter the password you set for soc.manager@example.local: " SOC_PASSWORD
echo
read -rs -p "Enter the password you set for customer.viewer@demo.local: " CUST_PASSWORD
echo

[ -n "$SOC_PASSWORD" ] || fail "SOC password cannot be empty."
[ -n "$CUST_PASSWORD" ] || fail "Customer password cannot be empty."

section "5. POST /auth/login - demo SOC user"

soc_login_body="$(jq -n --arg email "soc.manager@example.local" --arg password "$SOC_PASSWORD" '{email:$email,password:$password}')"
soc_login_response="$(curl -fsS -X POST "$API_BASE/auth/login" \
  -H "Content-Type: application/json" \
  -d "$soc_login_body")"

echo "$soc_login_response" | jq 'del(.access_token)'

echo "$soc_login_response" | jq -e '.user.role == "soc_manager"' >/dev/null || fail "SOC login did not return expected role"
echo "$soc_login_response" | jq -e '.access_token | length > 10' >/dev/null || fail "SOC login did not return an access token"
echo "$soc_login_response" | grep -qi "password_hash" && fail "SOC login response leaked password_hash field name"
echo "SOC login response does not contain password_hash"

SOC_TOKEN="$(echo "$soc_login_response" | jq -r '.access_token')"

section "6. GET /auth/me - demo SOC user"

soc_me_response="$(curl -fsS "$API_BASE/auth/me" -H "Authorization: Bearer $SOC_TOKEN")"
echo "$soc_me_response" | jq .
echo "$soc_me_response" | jq -e '.role == "soc_manager"' >/dev/null || fail "/auth/me role mismatch for SOC user"
echo "$soc_me_response" | grep -qi "password" && fail "/auth/me leaked a password-related field"
echo "/auth/me for SOC user looks correct and has no password fields"

section "7. POST /auth/login - demo customer user"

cust_login_body="$(jq -n --arg email "customer.viewer@demo.local" --arg password "$CUST_PASSWORD" '{email:$email,password:$password}')"
cust_login_response="$(curl -fsS -X POST "$API_BASE/auth/login" \
  -H "Content-Type: application/json" \
  -d "$cust_login_body")"

echo "$cust_login_response" | jq 'del(.access_token)'

echo "$cust_login_response" | jq -e '.user.role == "customer_viewer"' >/dev/null || fail "Customer login did not return expected role"
echo "$cust_login_response" | jq -e '.user.tenant_id != null' >/dev/null || fail "Customer login did not return a tenant_id"

CUST_TOKEN="$(echo "$cust_login_response" | jq -r '.access_token')"
CUST_TENANT_ID="$(echo "$cust_login_response" | jq -r '.user.tenant_id')"

section "8. GET /auth/me - demo customer user"

cust_me_response="$(curl -fsS "$API_BASE/auth/me" -H "Authorization: Bearer $CUST_TOKEN")"
echo "$cust_me_response" | jq .
echo "$cust_me_response" | jq -e --arg tid "$CUST_TENANT_ID" '.tenant_id == $tid' >/dev/null || fail "/auth/me tenant_id mismatch for customer user"
echo "/auth/me for customer user looks correct and tenant_id matches login response"

section "9. Failure cases"

echo "9a. Wrong password must return 401"
wrong_login_body="$(jq -n --arg email "soc.manager@example.local" --arg password "deliberately-wrong-password" '{email:$email,password:$password}')"
wrong_status="$(curl -s -o /tmp/kb010-wrong-login.json -w '%{http_code}' -X POST "$API_BASE/auth/login" \
  -H "Content-Type: application/json" \
  -d "$wrong_login_body")"
[ "$wrong_status" = "401" ] || fail "Wrong password did not return 401 (got $wrong_status)"
jq . /tmp/kb010-wrong-login.json
echo "Wrong password correctly rejected with 401"

echo
echo "9b. /auth/me with no Authorization header must return 401"
no_token_status="$(curl -s -o /dev/null -w '%{http_code}' "$API_BASE/auth/me")"
[ "$no_token_status" = "401" ] || fail "/auth/me without a token did not return 401 (got $no_token_status)"
echo "/auth/me without a token correctly returns 401"

echo
echo "9c. /auth/me with a garbage token must return 401"
bad_token_status="$(curl -s -o /dev/null -w '%{http_code}' "$API_BASE/auth/me" -H "Authorization: Bearer not-a-real-token")"
[ "$bad_token_status" = "401" ] || fail "/auth/me with a garbage token did not return 401 (got $bad_token_status)"
echo "/auth/me with a garbage token correctly returns 401"

unset SOC_PASSWORD CUST_PASSWORD SOC_TOKEN CUST_TOKEN

section "10. GET /auth/roles"

roles_response="$(curl -fsS "$API_BASE/auth/roles")"
echo "$roles_response" | jq .
for r in platform_admin soc_manager soc_analyst customer_admin customer_viewer; do
  echo "$roles_response" | jq -e --arg r "$r" 'any(.roles[]; .role == $r)' >/dev/null \
    || fail "/auth/roles is missing role: $r"
done
echo "/auth/roles contains all 5 expected roles"

section "11. Regression check - KB-008 endpoints must still work unauthenticated"

./scripts/kb008_validate_backend_api_foundation.sh

section "12. Final validation verdict"

echo "KB-010 AUTH/RBAC FOUNDATION VALIDATION PASSED (Phase 1)"
echo
echo "Notes:"
echo "  - /admin/* and /customer/* preview endpoints are intentionally still"
echo "    unauthenticated in this phase (Phase 2 would add protection)."
echo "  - Demo credentials used above are for internal testing only."
echo
echo "======================================================================"
echo "KB-010 validation completed successfully."
echo "======================================================================"
