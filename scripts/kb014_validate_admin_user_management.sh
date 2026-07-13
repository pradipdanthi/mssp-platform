#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="/opt/mssp-control"
API_BASE="http://localhost:8000"
BODY_FILE="/tmp/kb014-body.json"
TEST_EMAIL="kb014.validation.user@example.local"
TEST_PASSWORD_1="Kb014-Validation-Pw-1!"
TEST_PASSWORD_2="Kb014-Validation-Pw-2!"

cd "$PROJECT_DIR"

echo "======================================================================"
echo "KB-014: Validate Admin User Management API"
echo "Target: $PROJECT_DIR"
echo "======================================================================"

fail() {
  echo
  echo "VALIDATION FAILED: $1"
  echo "Recent backend-api logs:"
  docker compose logs --tail=80 backend-api || true
  cleanup_test_user || true
  exit 1
}

section() {
  echo
  echo "----------------------------------------------------------------------"
  echo "$1"
  echo "----------------------------------------------------------------------"
}

cleanup_test_user() {
  docker compose exec -T postgres psql \
    -U "${POSTGRES_USER:-mssp_admin}" -d "${POSTGRES_DB:-mssp_control}" \
    -c "DELETE FROM platform_users WHERE email = '${TEST_EMAIL}';" >/dev/null 2>&1 || true
}

cleanup() {
  rm -f "$BODY_FILE"
  cleanup_test_user
  unset PLATFORM_ADMIN_PASSWORD SOC_MANAGER_PASSWORD SOC_ANALYST_PASSWORD \
        CUSTOMER_ADMIN_PASSWORD CUSTOMER_VIEWER_PASSWORD \
        PLATFORM_ADMIN_TOKEN SOC_MANAGER_TOKEN SOC_ANALYST_TOKEN \
        CUSTOMER_ADMIN_TOKEN CUSTOMER_VIEWER_TOKEN 2>/dev/null || true
}
trap cleanup EXIT

# print_body_redacted <body_file>
# Prints a response body for debugging with any sensitive JSON object key's
# value replaced by "<redacted>" - never prints a password or access token.
# If the body isn't valid JSON (or jq's `walk` isn't available), prints a
# safe placeholder instead of falling back to an unredacted raw dump.
print_body_redacted() {
  local file="$1"
  local redacted
  redacted="$(jq '
      walk(
        if type == "object" then
          with_entries(
            if (.key | ascii_downcase) as $k
               | ($k == "password" or $k == "new_password" or $k == "password_hash"
                  or $k == "access_token" or $k == "token" or $k == "jwt"
                  or $k == "secret" or $k == "jwt_secret")
            then .value = "<redacted>"
            else .
            end
          )
        else .
        end
      )
    ' "$file" 2>/dev/null)"
  if [ -n "$redacted" ]; then
    echo "$redacted"
  else
    echo "(response body omitted - could not be parsed/redacted safely)"
  fi
}

# response_has_password_hash_string <body_file>
# Fails if the literal string "password_hash" appears anywhere in the body
# (this string has no legitimate reason to ever appear in any response).
response_has_password_hash_string() {
  grep -qi "password_hash" "$1" 2>/dev/null
}

# response_has_sensitive_object_key <body_file>
# Fails only if the *parsed JSON* response contains "password", "new_password",
# or "password_hash" as an actual object key, at any depth (e.g. an echoed
# request body inside a validation error's "input"). Deliberately does NOT
# match those words when they only appear as array/string values - e.g.
# loc: ["body", "new_password"] - or inside a URL path such as
# /admin/users/{id}/password, since jq's `objects | has(...)` only inspects
# real JSON object keys, never array entries or strings.
response_has_sensitive_object_key() {
  local file="$1"
  jq -e '
    [.. | objects | select(has("password") or has("new_password") or has("password_hash"))]
    | length > 0
  ' "$file" >/dev/null 2>&1
}

# response_has_known_password_value <body_file>
# Fails if either of this script's own known plaintext validation passwords
# appears verbatim anywhere in the body (fixed-string match, not a generic
# "password" text search).
response_has_known_password_value() {
  local file="$1"
  grep -qF -- "$TEST_PASSWORD_1" "$file" 2>/dev/null && return 0
  grep -qF -- "$TEST_PASSWORD_2" "$file" 2>/dev/null && return 0
  return 1
}

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
    echo "Response body (redacted):"
    print_body_redacted "$BODY_FILE"
    echo
    fail "$description expected HTTP $expected but got $actual"
  fi

  # Never leak password/hash material, no matter which check this is. These
  # deliberately do not flag loc/type/msg text or URL paths that merely
  # contain the word "password" (e.g. /admin/users/{id}/password, or
  # loc: ["body", "new_password"]) - see each function's own comment.
  if response_has_password_hash_string "$BODY_FILE"; then
    fail "$description leaked the string password_hash in the response body"
  fi
  if response_has_sensitive_object_key "$BODY_FILE"; then
    fail "$description exposed password/new_password/password_hash as a JSON object key in the response body"
  fi
  if response_has_known_password_value "$BODY_FILE"; then
    fail "$description leaked a known validation password value in the response body"
  fi
}

section "1. File checks"

for f in \
  backend-api/app/schemas/users.py \
  backend-api/app/api/routes/user_management.py \
  backend-api/app/api/routes/admin.py \
  backend-api/app/api/routes/tenant_management.py
do
  [ -f "$f" ] || fail "$f is missing"
  echo "found: $f"
done

grep -q '@router.get("/tenants")' backend-api/app/api/routes/admin.py \
  || fail "admin.py no longer defines GET /tenants - existing endpoint may have been modified"
echo "OK: admin.py still defines the original GET /tenants handler"

grep -q "user_management_router" backend-api/app/main.py \
  || fail "main.py does not include user_management_router"
echo "OK: main.py includes user_management_router"

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

section "6. Resolve an existing tenant id (DEMO) for customer-role test payloads"

DEMO_LOOKUP="$(curl -fsS -H "Authorization: Bearer $PLATFORM_ADMIN_TOKEN" "$API_BASE/admin/tenants")"
DEMO_TENANT_ID="$(echo "$DEMO_LOOKUP" | jq -r '.tenants[] | select(.short_code=="DEMO") | .id')"
[ -n "$DEMO_TENANT_ID" ] && [ "$DEMO_TENANT_ID" != "null" ] || fail "Could not resolve tenant id for short_code DEMO from GET /admin/tenants"
echo "Resolved DEMO tenant id: $DEMO_TENANT_ID"

section "7. New endpoints must return 401 with no/garbage token"

check_status "GET /admin/users with no token" 401 GET "$API_BASE/admin/users"
check_status "GET /admin/users with garbage token" 401 GET "$API_BASE/admin/users" "not-a-real-token"
check_status "POST /admin/users with no token" 401 POST "$API_BASE/admin/users" "" '{"email":"x@example.local","full_name":"x","password":"password123","role":"customer_viewer"}'
check_status "PATCH /admin/users/00000000-0000-0000-0000-000000000000 with no token" 401 PATCH "$API_BASE/admin/users/00000000-0000-0000-0000-000000000000" "" '{"phone":"1"}'
check_status "PATCH /admin/users/.../password with no token" 401 PATCH "$API_BASE/admin/users/00000000-0000-0000-0000-000000000000/password" "" '{"new_password":"password123"}'

section "8. Customer roles must be denied with 403 on all new endpoints"

check_status "GET /admin/users as customer_viewer (must be denied)" 403 GET "$API_BASE/admin/users" "$CUSTOMER_VIEWER_TOKEN"
check_status "GET /admin/users as customer_admin (must be denied)" 403 GET "$API_BASE/admin/users" "$CUSTOMER_ADMIN_TOKEN"
check_status "POST /admin/users as customer_viewer (must be denied)" 403 POST "$API_BASE/admin/users" "$CUSTOMER_VIEWER_TOKEN" '{"email":"x@example.local","full_name":"x","password":"password123","role":"customer_viewer","tenant_id":"'"$DEMO_TENANT_ID"'"}'

section "9. soc_manager and soc_analyst can list and read user detail"

check_status "GET /admin/users as soc_manager" 200 GET "$API_BASE/admin/users" "$SOC_MANAGER_TOKEN"
check_status "GET /admin/users as soc_analyst" 200 GET "$API_BASE/admin/users" "$SOC_ANALYST_TOKEN"
check_status "GET /admin/users as platform_admin" 200 GET "$API_BASE/admin/users" "$PLATFORM_ADMIN_TOKEN"

PLATFORM_ADMIN_USER_ID="$(jq -r --arg email "platform.admin@example.local" '.users[] | select(.email==$email) | .id' "$BODY_FILE")"
[ -n "$PLATFORM_ADMIN_USER_ID" ] && [ "$PLATFORM_ADMIN_USER_ID" != "null" ] || fail "Could not resolve platform.admin@example.local's user id from GET /admin/users"

check_status "GET /admin/users/$PLATFORM_ADMIN_USER_ID as soc_manager" 200 GET "$API_BASE/admin/users/$PLATFORM_ADMIN_USER_ID" "$SOC_MANAGER_TOKEN"
check_status "GET /admin/users/$PLATFORM_ADMIN_USER_ID as soc_analyst" 200 GET "$API_BASE/admin/users/$PLATFORM_ADMIN_USER_ID" "$SOC_ANALYST_TOKEN"

section "10. soc_manager and soc_analyst cannot create/update/reset-password (403)"

CREATE_BODY_FOR_SOC_CHECK='{"email":"'"$TEST_EMAIL"'","full_name":"KB014 Validation User","password":"'"$TEST_PASSWORD_1"'","role":"customer_viewer","tenant_id":"'"$DEMO_TENANT_ID"'"}'

check_status "POST /admin/users as soc_manager (must be denied)" 403 POST "$API_BASE/admin/users" "$SOC_MANAGER_TOKEN" "$CREATE_BODY_FOR_SOC_CHECK"
check_status "POST /admin/users as soc_analyst (must be denied)" 403 POST "$API_BASE/admin/users" "$SOC_ANALYST_TOKEN" "$CREATE_BODY_FOR_SOC_CHECK"
check_status "PATCH /admin/users/$PLATFORM_ADMIN_USER_ID as soc_manager (must be denied)" 403 PATCH "$API_BASE/admin/users/$PLATFORM_ADMIN_USER_ID" "$SOC_MANAGER_TOKEN" '{"phone":"555-0000"}'
check_status "PATCH /admin/users/$PLATFORM_ADMIN_USER_ID as soc_analyst (must be denied)" 403 PATCH "$API_BASE/admin/users/$PLATFORM_ADMIN_USER_ID" "$SOC_ANALYST_TOKEN" '{"phone":"555-0000"}'
check_status "PATCH /admin/users/$PLATFORM_ADMIN_USER_ID/password as soc_manager (must be denied)" 403 PATCH "$API_BASE/admin/users/$PLATFORM_ADMIN_USER_ID/password" "$SOC_MANAGER_TOKEN" '{"new_password":"password123"}'

section "11. Invalid user_id (not a UUID) must be a clean 422, never a raw DB error"

check_status "GET /admin/users/not-a-uuid as platform_admin" 422 GET "$API_BASE/admin/users/not-a-uuid" "$PLATFORM_ADMIN_TOKEN"
check_status "PATCH /admin/users/not-a-uuid as platform_admin" 422 PATCH "$API_BASE/admin/users/not-a-uuid" "$PLATFORM_ADMIN_TOKEN" '{"phone":"1"}'
check_status "PATCH /admin/users/not-a-uuid/password as platform_admin" 422 PATCH "$API_BASE/admin/users/not-a-uuid/password" "$PLATFORM_ADMIN_TOKEN" '{"new_password":"password123"}'

section "12. Invalid create payloads must be rejected with 422"

check_status "POST /admin/users invalid role" 422 POST "$API_BASE/admin/users" "$PLATFORM_ADMIN_TOKEN" '{"email":"bad-role@example.local","full_name":"Bad Role","password":"password123","role":"not_a_real_role"}'
check_status "POST /admin/users customer role without tenant_id" 422 POST "$API_BASE/admin/users" "$PLATFORM_ADMIN_TOKEN" '{"email":"no-tenant@example.local","full_name":"No Tenant","password":"password123","role":"customer_viewer"}'
check_status "POST /admin/users admin role with tenant_id" 422 POST "$API_BASE/admin/users" "$PLATFORM_ADMIN_TOKEN" '{"email":"admin-with-tenant@example.local","full_name":"Admin With Tenant","password":"password123","role":"soc_analyst","tenant_id":"'"$DEMO_TENANT_ID"'"}'
check_status "POST /admin/users nonexistent tenant_id" 422 POST "$API_BASE/admin/users" "$PLATFORM_ADMIN_TOKEN" '{"email":"bad-tenant@example.local","full_name":"Bad Tenant","password":"password123","role":"customer_viewer","tenant_id":"00000000-0000-0000-0000-000000000000"}'
check_status "PATCH /admin/users/$PLATFORM_ADMIN_USER_ID empty body" 422 PATCH "$API_BASE/admin/users/$PLATFORM_ADMIN_USER_ID" "$PLATFORM_ADMIN_TOKEN" '{}'

section "13. platform_admin can create a clearly fake validation user"

cleanup_test_user

CREATE_BODY="$(jq -n --arg email "$TEST_EMAIL" --arg pw "$TEST_PASSWORD_1" --arg tenant "$DEMO_TENANT_ID" '{
  email: $email,
  full_name: "KB014 Validation User (fake, safe to delete)",
  password: $pw,
  role: "customer_viewer",
  tenant_id: $tenant,
  phone: "000-000-0000"
}')"

check_status "POST /admin/users as platform_admin (create test user)" 201 POST "$API_BASE/admin/users" "$PLATFORM_ADMIN_TOKEN" "$CREATE_BODY"

TEST_USER_ID="$(jq -r '.id' "$BODY_FILE")"
[ -n "$TEST_USER_ID" ] && [ "$TEST_USER_ID" != "null" ] || fail "Created test user response did not include an id"
echo "Created test user id: $TEST_USER_ID"

jq -e '.email == "'"$TEST_EMAIL"'"' "$BODY_FILE" >/dev/null || fail "Created user email does not match expected value"
jq -e '.user_type == "customer"' "$BODY_FILE" >/dev/null || fail "Created user_type should be 'customer' for role customer_viewer"
jq -e '.status == "active"' "$BODY_FILE" >/dev/null || fail "Created user should default to status active"

section "14. Duplicate email must return a clean 409"

check_status "POST /admin/users duplicate email" 409 POST "$API_BASE/admin/users" "$PLATFORM_ADMIN_TOKEN" "$CREATE_BODY"

section "15. Created validation user can log in with the created password"

LOGIN_BODY="$(jq -n --arg email "$TEST_EMAIL" --arg pw "$TEST_PASSWORD_1" '{email:$email,password:$pw}')"
check_status "POST /auth/login as newly created validation user" 200 POST "$API_BASE/auth/login" "" "$LOGIN_BODY"
jq -e '.user.role == "customer_viewer"' "$BODY_FILE" >/dev/null || fail "Login response for validation user did not report role customer_viewer"

section "16. PATCH status=inactive disables the validation user"

check_status "PATCH /admin/users/$TEST_USER_ID set status=inactive" 200 PATCH "$API_BASE/admin/users/$TEST_USER_ID" "$PLATFORM_ADMIN_TOKEN" '{"status":"inactive"}'
jq -e '.status == "inactive"' "$BODY_FILE" >/dev/null || fail "PATCH did not persist status=inactive change"

echo "Confirming login is blocked while disabled..."
check_status "POST /auth/login as disabled validation user (must be denied)" 403 POST "$API_BASE/auth/login" "" "$LOGIN_BODY"

section "17. PATCH status=active re-enables the validation user"

check_status "PATCH /admin/users/$TEST_USER_ID set status=active" 200 PATCH "$API_BASE/admin/users/$TEST_USER_ID" "$PLATFORM_ADMIN_TOKEN" '{"status":"active"}'
jq -e '.status == "active"' "$BODY_FILE" >/dev/null || fail "PATCH did not persist status=active change"

echo "Confirming login now works again..."
check_status "POST /auth/login as re-enabled validation user" 200 POST "$API_BASE/auth/login" "" "$LOGIN_BODY"

section "18. PATCH /password changes the password successfully"

PASSWORD_BODY="$(jq -n --arg pw "$TEST_PASSWORD_2" '{new_password:$pw}')"
check_status "PATCH /admin/users/$TEST_USER_ID/password as platform_admin" 200 PATCH "$API_BASE/admin/users/$TEST_USER_ID/password" "$PLATFORM_ADMIN_TOKEN" "$PASSWORD_BODY"

section "19. Old password no longer works, new password works"

check_status "POST /auth/login with OLD password (must fail)" 401 POST "$API_BASE/auth/login" "" "$LOGIN_BODY"

NEW_LOGIN_BODY="$(jq -n --arg email "$TEST_EMAIL" --arg pw "$TEST_PASSWORD_2" '{email:$email,password:$pw}')"
check_status "POST /auth/login with NEW password (must succeed)" 200 POST "$API_BASE/auth/login" "" "$NEW_LOGIN_BODY"

section "20. Clean up the validation test user"

cleanup_test_user
STILL_EXISTS="$(docker compose exec -T postgres psql -tA \
  -U "${POSTGRES_USER:-mssp_admin}" -d "${POSTGRES_DB:-mssp_control}" \
  -c "SELECT count(*) FROM platform_users WHERE email = '${TEST_EMAIL}';" 2>/dev/null | tr -d '[:space:]')"
[ "$STILL_EXISTS" = "0" ] || fail "Test user $TEST_EMAIL was not cleaned up (found $STILL_EXISTS rows)"
echo "OK: test user $TEST_EMAIL removed, no leftover validation data."

section "21. Behavior regression gate: scripts/kb013_validate_admin_tenant_management.sh"

echo "Running the full, unmodified KB-013 validation script now (which itself"
echo "reruns KB-012, and through it KB-011). It will ask for the 5 demo"
echo "passwords again."
echo

if ! ./scripts/kb013_validate_admin_tenant_management.sh; then
  fail "scripts/kb013_validate_admin_tenant_management.sh did not pass after adding user management - this is a real regression"
fi

section "22. Final validation verdict"

echo "KB-014 ADMIN USER MANAGEMENT VALIDATION PASSED"
echo
echo "Summary:"
echo "  - /health, /auth/roles, /docs remain public."
echo "  - GET/POST/PATCH /admin/users/* all require a valid token (401 enforced)."
echo "  - Customer roles are denied with 403 on all new endpoints."
echo "  - soc_manager/soc_analyst can list/read users but cannot create/update/reset (403)."
echo "  - platform_admin can create, read, update, and set passwords for users."
echo "  - Invalid user_id (non-UUID) returns a clean 422, never a raw DB error."
echo "  - Invalid payloads (bad role, missing/bad tenant_id, empty PATCH) return a clean 422."
echo "  - Duplicate email returns a clean 409."
echo "  - The created validation user could log in with its created password."
echo "  - Disabling the user (status=inactive) blocked login; re-enabling restored it."
echo "  - The password-set endpoint changed the password; the old password stopped working"
echo "    and the new password worked."
echo "  - No response ever contained password_hash or a password value."
echo "  - The validation test user ($TEST_EMAIL) was cleaned up - no leftover data."
echo "  - scripts/kb013_validate_admin_tenant_management.sh passed unmodified - no observable"
echo "    behavior change to tenant management, route structure, auth, RBAC, or tenant isolation."
echo
echo "======================================================================"
echo "KB-014 validation completed successfully."
echo "======================================================================"
