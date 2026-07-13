#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="/opt/mssp-control"
API_BASE="http://localhost:8000"
BODY_FILE="/tmp/kb013-body.json"
TEST_SHORT_CODE="KBTEST13"

cd "$PROJECT_DIR"

echo "======================================================================"
echo "KB-013: Validate Admin Tenant Management API"
echo "Target: $PROJECT_DIR"
echo "======================================================================"

fail() {
  echo
  echo "VALIDATION FAILED: $1"
  echo "Recent backend-api logs:"
  docker compose logs --tail=80 backend-api || true
  cleanup_test_tenant || true
  exit 1
}

section() {
  echo
  echo "----------------------------------------------------------------------"
  echo "$1"
  echo "----------------------------------------------------------------------"
}

cleanup_test_tenant() {
  docker compose exec -T postgres psql \
    -U "${POSTGRES_USER:-mssp_admin}" -d "${POSTGRES_DB:-mssp_control}" \
    -c "DELETE FROM tenants WHERE short_code = '${TEST_SHORT_CODE}';" >/dev/null 2>&1 || true
}

cleanup() {
  rm -f "$BODY_FILE"
  cleanup_test_tenant
  unset PLATFORM_ADMIN_PASSWORD SOC_MANAGER_PASSWORD SOC_ANALYST_PASSWORD \
        CUSTOMER_ADMIN_PASSWORD CUSTOMER_VIEWER_PASSWORD \
        PLATFORM_ADMIN_TOKEN SOC_MANAGER_TOKEN SOC_ANALYST_TOKEN \
        CUSTOMER_ADMIN_TOKEN CUSTOMER_VIEWER_TOKEN 2>/dev/null || true
}
trap cleanup EXIT

# check_status <description> <expected_http_code> <method> <url> [token] [json_body]
check_status() {
  local description="$1"
  local expected="$2"
  local method="$3"
  local url="$4"
  local token="${5:-}"
  local body="${6:-}"
  local actual
  local args=(-s -o "$BODY_FILE" -w '%{http_code}' -X "$method")

  if [ -n "$token" ]; then
    args+=(-H "Authorization: Bearer $token")
  fi
  if [ -n "$body" ]; then
    args+=(-H "Content-Type: application/json" -d "$body")
  fi

  actual="$(curl "${args[@]}" "$url")"

  if [ "$actual" = "$expected" ]; then
    echo "OK   [$actual] $description"
  else
    echo "FAIL [$actual, expected $expected] $description"
    echo "Response body:"
    cat "$BODY_FILE" 2>/dev/null || true
    echo
    fail "$description expected HTTP $expected but got $actual"
  fi

  if grep -qi "password_hash" "$BODY_FILE" 2>/dev/null; then
    fail "$description leaked a password_hash field in the response body"
  fi
}

section "1. File checks"

for f in \
  backend-api/app/schemas/tenants.py \
  backend-api/app/api/routes/tenant_management.py \
  backend-api/app/api/routes/admin.py
do
  [ -f "$f" ] || fail "$f is missing"
  echo "found: $f"
done

grep -q '@router.get("/tenants")' backend-api/app/api/routes/admin.py \
  || fail "admin.py no longer defines GET /tenants - existing endpoint may have been modified"
echo "OK: admin.py still defines the original GET /tenants handler"

grep -q "tenant_management_router" backend-api/app/main.py \
  || fail "main.py does not include tenant_management_router"
echo "OK: main.py includes tenant_management_router"

section "2. Docker Compose and service health"

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

section "3. Public endpoints must remain public (no token)"

check_status "GET /health (public)" 200 GET "$API_BASE/health"
check_status "GET /auth/roles (public)" 200 GET "$API_BASE/auth/roles"
check_status "GET /docs (public, dev docs)" 200 GET "$API_BASE/docs"

section "4. Enter demo passwords (input hidden, never logged)"

read -rs -p "Enter the password for platform.admin@example.local: " PLATFORM_ADMIN_PASSWORD
echo
read -rs -p "Enter the password for soc.manager@example.local: " SOC_MANAGER_PASSWORD
echo
read -rs -p "Enter the password for soc.analyst@example.local: " SOC_ANALYST_PASSWORD
echo
read -rs -p "Enter the password for customer.admin@demo2.local: " CUSTOMER_ADMIN_PASSWORD
echo
read -rs -p "Enter the password for customer.viewer@demo.local: " CUSTOMER_VIEWER_PASSWORD
echo

for pw_name in PLATFORM_ADMIN_PASSWORD SOC_MANAGER_PASSWORD SOC_ANALYST_PASSWORD CUSTOMER_ADMIN_PASSWORD CUSTOMER_VIEWER_PASSWORD; do
  [ -n "${!pw_name}" ] || fail "$pw_name cannot be empty."
done

section "5. Logging in as all 5 roles"

login() {
  local email="$1"
  local password="$2"
  local expected_role="$3"
  local body
  body="$(jq -n --arg email "$email" --arg password "$password" '{email:$email,password:$password}')"
  local response
  response="$(curl -fsS -X POST "$API_BASE/auth/login" \
    -H "Content-Type: application/json" \
    -d "$body")"
  echo "$response" | jq 'del(.access_token)' >&2
  echo "$response" | jq -e --arg role "$expected_role" '.user.role == $role' >/dev/null \
    || fail "Login for $email did not return expected role $expected_role"
  echo "$response" | grep -qi "password_hash" && fail "Login response for $email leaked password_hash"
  echo "$response" | jq -r '.access_token'
}

echo "Logging in as platform_admin..."
PLATFORM_ADMIN_TOKEN="$(login "platform.admin@example.local" "$PLATFORM_ADMIN_PASSWORD" "platform_admin")"

echo "Logging in as soc_manager..."
SOC_MANAGER_TOKEN="$(login "soc.manager@example.local" "$SOC_MANAGER_PASSWORD" "soc_manager")"

echo "Logging in as soc_analyst..."
SOC_ANALYST_TOKEN="$(login "soc.analyst@example.local" "$SOC_ANALYST_PASSWORD" "soc_analyst")"

echo "Logging in as customer_admin (tenant DEMO2)..."
CUSTOMER_ADMIN_TOKEN="$(login "customer.admin@demo2.local" "$CUSTOMER_ADMIN_PASSWORD" "customer_admin")"

echo "Logging in as customer_viewer (tenant DEMO)..."
CUSTOMER_VIEWER_TOKEN="$(login "customer.viewer@demo.local" "$CUSTOMER_VIEWER_PASSWORD" "customer_viewer")"

unset PLATFORM_ADMIN_PASSWORD SOC_MANAGER_PASSWORD SOC_ANALYST_PASSWORD CUSTOMER_ADMIN_PASSWORD CUSTOMER_VIEWER_PASSWORD

for tok_name in PLATFORM_ADMIN_TOKEN SOC_MANAGER_TOKEN SOC_ANALYST_TOKEN CUSTOMER_ADMIN_TOKEN CUSTOMER_VIEWER_TOKEN; do
  [ -n "${!tok_name}" ] || fail "$tok_name was not obtained - login must have failed."
done

echo "All 5 logins succeeded and returned tokens (not displayed)."

section "6. Resolve an existing tenant id (DEMO) to use for read checks"

DEMO_LOOKUP="$(curl -fsS -H "Authorization: Bearer $PLATFORM_ADMIN_TOKEN" "$API_BASE/admin/tenants")"
DEMO_TENANT_ID="$(echo "$DEMO_LOOKUP" | jq -r '.tenants[] | select(.short_code=="DEMO") | .id')"
[ -n "$DEMO_TENANT_ID" ] && [ "$DEMO_TENANT_ID" != "null" ] || fail "Could not resolve tenant id for short_code DEMO from GET /admin/tenants"
echo "Resolved DEMO tenant id: $DEMO_TENANT_ID"

section "7. New endpoints must return 401 with no/garbage token"

check_status "GET /admin/tenants/$DEMO_TENANT_ID with no token" 401 GET "$API_BASE/admin/tenants/$DEMO_TENANT_ID"
check_status "GET /admin/tenants/$DEMO_TENANT_ID with garbage token" 401 GET "$API_BASE/admin/tenants/$DEMO_TENANT_ID" "not-a-real-token"
check_status "POST /admin/tenants with no token" 401 POST "$API_BASE/admin/tenants" "" '{"name":"x","short_code":"XX"}'
check_status "PATCH /admin/tenants/$DEMO_TENANT_ID with no token" 401 PATCH "$API_BASE/admin/tenants/$DEMO_TENANT_ID" "" '{"notes":"x"}'

section "8. Customer roles must be denied with 403 on all 3 new endpoints"

check_status "GET /admin/tenants/$DEMO_TENANT_ID as customer_viewer (must be denied)" 403 GET "$API_BASE/admin/tenants/$DEMO_TENANT_ID" "$CUSTOMER_VIEWER_TOKEN"
check_status "GET /admin/tenants/$DEMO_TENANT_ID as customer_admin (must be denied)" 403 GET "$API_BASE/admin/tenants/$DEMO_TENANT_ID" "$CUSTOMER_ADMIN_TOKEN"
check_status "POST /admin/tenants as customer_viewer (must be denied)" 403 POST "$API_BASE/admin/tenants" "$CUSTOMER_VIEWER_TOKEN" '{"name":"x","short_code":"XX"}'
check_status "PATCH /admin/tenants/$DEMO_TENANT_ID as customer_admin (must be denied)" 403 PATCH "$API_BASE/admin/tenants/$DEMO_TENANT_ID" "$CUSTOMER_ADMIN_TOKEN" '{"notes":"x"}'

section "9. soc_manager and soc_analyst can read tenant detail"

check_status "GET /admin/tenants/$DEMO_TENANT_ID as soc_manager" 200 GET "$API_BASE/admin/tenants/$DEMO_TENANT_ID" "$SOC_MANAGER_TOKEN"
check_status "GET /admin/tenants/$DEMO_TENANT_ID as soc_analyst" 200 GET "$API_BASE/admin/tenants/$DEMO_TENANT_ID" "$SOC_ANALYST_TOKEN"
check_status "GET /admin/tenants/$DEMO_TENANT_ID as platform_admin" 200 GET "$API_BASE/admin/tenants/$DEMO_TENANT_ID" "$PLATFORM_ADMIN_TOKEN"

section "10. soc_manager and soc_analyst cannot create/update tenants (403)"

check_status "POST /admin/tenants as soc_manager (must be denied)" 403 POST "$API_BASE/admin/tenants" "$SOC_MANAGER_TOKEN" '{"name":"x","short_code":"XX"}'
check_status "POST /admin/tenants as soc_analyst (must be denied)" 403 POST "$API_BASE/admin/tenants" "$SOC_ANALYST_TOKEN" '{"name":"x","short_code":"XX"}'
check_status "PATCH /admin/tenants/$DEMO_TENANT_ID as soc_manager (must be denied)" 403 PATCH "$API_BASE/admin/tenants/$DEMO_TENANT_ID" "$SOC_MANAGER_TOKEN" '{"notes":"x"}'
check_status "PATCH /admin/tenants/$DEMO_TENANT_ID as soc_analyst (must be denied)" 403 PATCH "$API_BASE/admin/tenants/$DEMO_TENANT_ID" "$SOC_ANALYST_TOKEN" '{"notes":"x"}'

section "11. Invalid tenant_id (not a UUID) must be a clean 422, never a raw DB error"

check_status "GET /admin/tenants/not-a-uuid as platform_admin" 422 GET "$API_BASE/admin/tenants/not-a-uuid" "$PLATFORM_ADMIN_TOKEN"

section "12. Invalid payloads must be rejected with 422"

check_status "POST /admin/tenants missing name" 422 POST "$API_BASE/admin/tenants" "$PLATFORM_ADMIN_TOKEN" '{"short_code":"'"$TEST_SHORT_CODE"'"}'
check_status "POST /admin/tenants bad short_code (contains space)" 422 POST "$API_BASE/admin/tenants" "$PLATFORM_ADMIN_TOKEN" '{"name":"KB013 Bad Tenant","short_code":"BAD CODE"}'
check_status "POST /admin/tenants invalid status enum" 422 POST "$API_BASE/admin/tenants" "$PLATFORM_ADMIN_TOKEN" '{"name":"KB013 Bad Tenant","short_code":"BADSTATUS","status":"not_a_real_status"}'
check_status "PATCH /admin/tenants/$DEMO_TENANT_ID empty body" 422 PATCH "$API_BASE/admin/tenants/$DEMO_TENANT_ID" "$PLATFORM_ADMIN_TOKEN" '{}'

section "13. platform_admin can create a clearly fake validation tenant"

cleanup_test_tenant

CREATE_BODY="$(jq -n --arg sc "$TEST_SHORT_CODE" '{
  name: "KB013 Validation Test Tenant (fake, safe to delete)",
  short_code: $sc,
  status: "active",
  sla_level: "standard",
  business_criticality: "low",
  timezone: "Asia/Kolkata",
  notes: "Created by scripts/kb013_validate_admin_tenant_management.sh - safe to delete."
}')"

check_status "POST /admin/tenants as platform_admin (create test tenant)" 201 POST "$API_BASE/admin/tenants" "$PLATFORM_ADMIN_TOKEN" "$CREATE_BODY"

TEST_TENANT_ID="$(jq -r '.id' "$BODY_FILE")"
[ -n "$TEST_TENANT_ID" ] && [ "$TEST_TENANT_ID" != "null" ] || fail "Created test tenant response did not include an id"
echo "Created test tenant id: $TEST_TENANT_ID"

jq -e '.short_code == "'"$TEST_SHORT_CODE"'"' "$BODY_FILE" >/dev/null || fail "Created tenant short_code does not match expected value"
jq -e '.appliances == 0 and .protected_assets == 0 and .incidents == 0' "$BODY_FILE" >/dev/null || fail "Newly created tenant should have zero appliances/protected_assets/incidents"

section "14. Duplicate short_code must return a clean 409"

check_status "POST /admin/tenants duplicate short_code" 409 POST "$API_BASE/admin/tenants" "$PLATFORM_ADMIN_TOKEN" "$CREATE_BODY"

section "15. PATCH update works for platform_admin"

PATCH_BODY='{"business_criticality":"high","notes":"Updated by KB-013 validation script."}'
check_status "PATCH /admin/tenants/$TEST_TENANT_ID as platform_admin" 200 PATCH "$API_BASE/admin/tenants/$TEST_TENANT_ID" "$PLATFORM_ADMIN_TOKEN" "$PATCH_BODY"
jq -e '.business_criticality == "high"' "$BODY_FILE" >/dev/null || fail "PATCH did not persist business_criticality change"

echo "Confirming soft-delete style deactivation via status update..."
check_status "PATCH /admin/tenants/$TEST_TENANT_ID set status=inactive" 200 PATCH "$API_BASE/admin/tenants/$TEST_TENANT_ID" "$PLATFORM_ADMIN_TOKEN" '{"status":"inactive"}'
jq -e '.status == "inactive"' "$BODY_FILE" >/dev/null || fail "PATCH did not persist status=inactive change"

section "16. PATCH on an unknown (but valid-format) tenant_id returns 404"

check_status "PATCH /admin/tenants/00000000-0000-0000-0000-000000000000 as platform_admin" 404 PATCH "$API_BASE/admin/tenants/00000000-0000-0000-0000-000000000000" "$PLATFORM_ADMIN_TOKEN" '{"notes":"x"}'

section "17. Clean up the validation test tenant"

cleanup_test_tenant
STILL_EXISTS="$(docker compose exec -T postgres psql -tA \
  -U "${POSTGRES_USER:-mssp_admin}" -d "${POSTGRES_DB:-mssp_control}" \
  -c "SELECT count(*) FROM tenants WHERE short_code = '${TEST_SHORT_CODE}';" 2>/dev/null | tr -d '[:space:]')"
[ "$STILL_EXISTS" = "0" ] || fail "Test tenant $TEST_SHORT_CODE was not cleaned up (found $STILL_EXISTS rows)"
echo "OK: test tenant $TEST_SHORT_CODE removed, no leftover validation data."

section "18. Behavior regression gate: scripts/kb012_validate_route_modularization.sh"

echo "Running the full, unmodified KB-012 validation script now (which itself"
echo "reruns the KB-011 validation script). It will ask for the 5 demo"
echo "passwords again."
echo

if ! ./scripts/kb012_validate_route_modularization.sh; then
  fail "scripts/kb012_validate_route_modularization.sh did not pass after adding tenant management - this is a real regression"
fi

section "19. Final validation verdict"

echo "KB-013 ADMIN TENANT MANAGEMENT VALIDATION PASSED"
echo
echo "Summary:"
echo "  - /health, /auth/roles, /docs remain public."
echo "  - GET/POST/PATCH /admin/tenants/* all require a valid token (401 enforced)."
echo "  - Customer roles are denied with 403 on all 3 new endpoints."
echo "  - soc_manager/soc_analyst can read tenant detail but cannot create/update (403)."
echo "  - platform_admin can create, read, and update tenants."
echo "  - Invalid tenant_id (non-UUID) returns a clean 422, never a raw DB error."
echo "  - Invalid payloads (missing/bad fields, bad enum values) return a clean 422."
echo "  - Duplicate short_code returns a clean 409."
echo "  - Soft-delete via status=inactive/suspended works through PATCH."
echo "  - The validation test tenant ($TEST_SHORT_CODE) was cleaned up - no leftover data."
echo "  - scripts/kb012_validate_route_modularization.sh passed unmodified - no observable"
echo "    behavior change to auth, RBAC, tenant isolation, or route structure."
echo
echo "======================================================================"
echo "KB-013 validation completed successfully."
echo "======================================================================"
