#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="/opt/mssp-control"
API_BASE="http://localhost:8000"
BODY_FILE="/tmp/kb011-body.json"

cd "$PROJECT_DIR"

# shellcheck disable=SC1091
source "$(dirname "$0")/load_validation_credentials.sh"

echo "======================================================================"
echo "KB-011: Validate Protected /admin/* and /customer/* APIs"
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
  unset PLATFORM_ADMIN_PASSWORD SOC_MANAGER_PASSWORD SOC_ANALYST_PASSWORD \
        CUSTOMER_ADMIN_PASSWORD CUSTOMER_VIEWER_PASSWORD \
        PLATFORM_ADMIN_TOKEN SOC_MANAGER_TOKEN SOC_ANALYST_TOKEN \
        CUSTOMER_ADMIN_TOKEN CUSTOMER_VIEWER_TOKEN 2>/dev/null || true
}
trap cleanup EXIT

# check_status <description> <expected_http_code> <url> [bearer_token]
check_status() {
  local description="$1"
  local expected="$2"
  local url="$3"
  local token="${4:-}"
  local actual

  if [ -n "$token" ]; then
    actual="$(curl -s -o "$BODY_FILE" -w '%{http_code}' -H "Authorization: Bearer $token" "$url")"
  else
    actual="$(curl -s -o "$BODY_FILE" -w '%{http_code}' "$url")"
  fi

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

section "1. File and dependency checks"

for f in \
  backend-api/app/main.py \
  backend-api/app/api/dependencies.py \
  scripts/kb011_seed_rbac_fixtures.sh
do
  [ -f "$f" ] || fail "$f is missing"
  echo "found: $f"
done

grep -q "require_roles" backend-api/app/main.py || fail "main.py does not reference require_roles - KB-011 protection may not be applied"
grep -q "require_tenant_match" backend-api/app/main.py || fail "main.py does not reference require_tenant_match - KB-011 tenant isolation may not be applied"
grep -q "get_current_user" backend-api/app/main.py || fail "main.py does not reference get_current_user - KB-011 protection may not be applied"
echo "main.py references the expected KB-011 dependencies"

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

section "3. Public endpoints must remain public (no token)"

check_status "GET /health (public)" 200 "$API_BASE/health"
check_status "GET /auth/roles (public)" 200 "$API_BASE/auth/roles"
check_status "GET /docs (public, dev docs)" 200 "$API_BASE/docs"

section "4. Lab login passwords (from .secrets/validation.env or prompt)"

if validation_creds_complete; then
  echo "Using credentials from .secrets/validation.env (values not printed)."
else
  echo "Tip: copy deploy/environments/validation.lab.example.env to .secrets/validation.env"
  echo "     so validators run without prompts (chmod 600)."
  echo
  [[ -n "${PLATFORM_ADMIN_PASSWORD:-}" ]] || read -rs -p "Enter the password for platform.admin@example.local: " PLATFORM_ADMIN_PASSWORD
  echo
  [[ -n "${SOC_MANAGER_PASSWORD:-}" ]] || read -rs -p "Enter the password for soc.manager@example.local: " SOC_MANAGER_PASSWORD
  echo
  [[ -n "${SOC_ANALYST_PASSWORD:-}" ]] || read -rs -p "Enter the password for soc.analyst@example.local: " SOC_ANALYST_PASSWORD
  echo
  [[ -n "${CUSTOMER_ADMIN_PASSWORD:-}" ]] || read -rs -p "Enter the password for customer.admin@demo2.local: " CUSTOMER_ADMIN_PASSWORD
  echo
  [[ -n "${CUSTOMER_VIEWER_PASSWORD:-}" ]] || read -rs -p "Enter the password for customer.viewer@demo.local: " CUSTOMER_VIEWER_PASSWORD
  echo
fi

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

PLATFORM_ADMIN_EMAIL="${PLATFORM_ADMIN_EMAIL:-platform.admin@example.local}"
SOC_MANAGER_EMAIL="${SOC_MANAGER_EMAIL:-soc.manager@example.local}"
SOC_ANALYST_EMAIL="${SOC_ANALYST_EMAIL:-soc.analyst@example.local}"
CUSTOMER_ADMIN_EMAIL="${CUSTOMER_ADMIN_EMAIL:-customer.admin@demo2.local}"
CUSTOMER_VIEWER_EMAIL="${CUSTOMER_VIEWER_EMAIL:-customer.viewer@demo.local}"

echo "Logging in as platform_admin ($PLATFORM_ADMIN_EMAIL)..."
PLATFORM_ADMIN_TOKEN="$(login "$PLATFORM_ADMIN_EMAIL" "$PLATFORM_ADMIN_PASSWORD" "platform_admin")"

echo "Logging in as soc_manager ($SOC_MANAGER_EMAIL)..."
SOC_MANAGER_TOKEN="$(login "$SOC_MANAGER_EMAIL" "$SOC_MANAGER_PASSWORD" "soc_manager")"

echo "Logging in as soc_analyst ($SOC_ANALYST_EMAIL)..."
SOC_ANALYST_TOKEN="$(login "$SOC_ANALYST_EMAIL" "$SOC_ANALYST_PASSWORD" "soc_analyst")"

echo "Logging in as customer_admin ($CUSTOMER_ADMIN_EMAIL)..."
CUSTOMER_ADMIN_TOKEN="$(login "$CUSTOMER_ADMIN_EMAIL" "$CUSTOMER_ADMIN_PASSWORD" "customer_admin")"

echo "Logging in as customer_viewer ($CUSTOMER_VIEWER_EMAIL)..."
CUSTOMER_VIEWER_TOKEN="$(login "$CUSTOMER_VIEWER_EMAIL" "$CUSTOMER_VIEWER_PASSWORD" "customer_viewer")"

unset PLATFORM_ADMIN_PASSWORD SOC_MANAGER_PASSWORD SOC_ANALYST_PASSWORD CUSTOMER_ADMIN_PASSWORD CUSTOMER_VIEWER_PASSWORD

for tok_name in PLATFORM_ADMIN_TOKEN SOC_MANAGER_TOKEN SOC_ANALYST_TOKEN CUSTOMER_ADMIN_TOKEN CUSTOMER_VIEWER_TOKEN; do
  [ -n "${!tok_name}" ] || fail "$tok_name was not obtained - login must have failed."
done

echo "All 5 logins succeeded and returned tokens (not displayed)."

section "6. Regression: GET /auth/me still works (KB-010)"

check_status "GET /auth/me as soc_manager" 200 "$API_BASE/auth/me" "$SOC_MANAGER_TOKEN"
check_status "GET /auth/me with no token" 401 "$API_BASE/auth/me"

section "7. /admin/* endpoints - 401 for no/garbage token"

ADMIN_ENDPOINTS=(
  "/admin/dashboard"
  "/admin/tenants"
  "/admin/appliances"
  "/admin/alerts"
  "/admin/incidents"
)

for ep in "${ADMIN_ENDPOINTS[@]}"; do
  check_status "GET $ep with no token" 401 "$API_BASE$ep"
  check_status "GET $ep with garbage token" 401 "$API_BASE$ep" "not-a-real-token"
done

section "8. /admin/* endpoints - platform_admin, soc_manager, soc_analyst must all be allowed"

for ep in "${ADMIN_ENDPOINTS[@]}"; do
  check_status "GET $ep as platform_admin" 200 "$API_BASE$ep" "$PLATFORM_ADMIN_TOKEN"
  check_status "GET $ep as soc_manager" 200 "$API_BASE$ep" "$SOC_MANAGER_TOKEN"
  check_status "GET $ep as soc_analyst" 200 "$API_BASE$ep" "$SOC_ANALYST_TOKEN"
done

section "9. /admin/* endpoints - customer roles must be denied with 403"

for ep in "${ADMIN_ENDPOINTS[@]}"; do
  check_status "GET $ep as customer_viewer (must be denied)" 403 "$API_BASE$ep" "$CUSTOMER_VIEWER_TOKEN"
  check_status "GET $ep as customer_admin (must be denied)" 403 "$API_BASE$ep" "$CUSTOMER_ADMIN_TOKEN"
done

section "10. /customer/* endpoints - 401 for no/garbage token"

CUSTOMER_ENDPOINTS=(
  "/customer/dashboard"
  "/customer/incidents"
)

CUSTOMER_VIEWER_TENANT="${CUSTOMER_VIEWER_TENANT:-DEMO}"
CUSTOMER_ADMIN_TENANT="${CUSTOMER_ADMIN_TENANT:-DEMO2}"

for ep in "${CUSTOMER_ENDPOINTS[@]}"; do
  check_status "GET $ep/$CUSTOMER_VIEWER_TENANT with no token" 401 "$API_BASE$ep/$CUSTOMER_VIEWER_TENANT"
  check_status "GET $ep/$CUSTOMER_VIEWER_TENANT with garbage token" 401 "$API_BASE$ep/$CUSTOMER_VIEWER_TENANT" "not-a-real-token"
done

section "11. /customer/* endpoints - admin/SOC roles get cross-tenant read access"

for ep in "${CUSTOMER_ENDPOINTS[@]}"; do
  check_status "GET $ep/$CUSTOMER_VIEWER_TENANT as platform_admin (cross-tenant support access)" 200 "$API_BASE$ep/$CUSTOMER_VIEWER_TENANT" "$PLATFORM_ADMIN_TOKEN"
  check_status "GET $ep/$CUSTOMER_VIEWER_TENANT as soc_manager (cross-tenant support access)" 200 "$API_BASE$ep/$CUSTOMER_VIEWER_TENANT" "$SOC_MANAGER_TOKEN"
  check_status "GET $ep/$CUSTOMER_VIEWER_TENANT as soc_analyst (cross-tenant support access)" 200 "$API_BASE$ep/$CUSTOMER_VIEWER_TENANT" "$SOC_ANALYST_TOKEN"
  check_status "GET $ep/$CUSTOMER_ADMIN_TENANT as platform_admin (cross-tenant support access)" 200 "$API_BASE$ep/$CUSTOMER_ADMIN_TENANT" "$PLATFORM_ADMIN_TOKEN"
  check_status "GET $ep/$CUSTOMER_ADMIN_TENANT as soc_manager (cross-tenant support access)" 200 "$API_BASE$ep/$CUSTOMER_ADMIN_TENANT" "$SOC_MANAGER_TOKEN"
  check_status "GET $ep/$CUSTOMER_ADMIN_TENANT as soc_analyst (cross-tenant support access)" 200 "$API_BASE$ep/$CUSTOMER_ADMIN_TENANT" "$SOC_ANALYST_TOKEN"
done

section "12. /customer/* endpoints - customer roles may only see their own tenant"

for ep in "${CUSTOMER_ENDPOINTS[@]}"; do
  echo "12a. customer_viewer on own tenant -> 200"
  check_status "GET $ep/$CUSTOMER_VIEWER_TENANT as customer_viewer (own tenant)" 200 "$API_BASE$ep/$CUSTOMER_VIEWER_TENANT" "$CUSTOMER_VIEWER_TOKEN"

  echo "12b. customer_viewer on other tenant -> 404, never 403 (anti-enumeration)"
  check_status "GET $ep/$CUSTOMER_ADMIN_TENANT as customer_viewer (wrong tenant, must be 404)" 404 "$API_BASE$ep/$CUSTOMER_ADMIN_TENANT" "$CUSTOMER_VIEWER_TOKEN"

  echo "12c. customer_admin on own tenant -> 200"
  check_status "GET $ep/$CUSTOMER_ADMIN_TENANT as customer_admin (own tenant)" 200 "$API_BASE$ep/$CUSTOMER_ADMIN_TENANT" "$CUSTOMER_ADMIN_TOKEN"

  echo "12d. customer_admin on other tenant -> 404, never 403 (anti-enumeration)"
  check_status "GET $ep/$CUSTOMER_VIEWER_TENANT as customer_admin (wrong tenant, must be 404)" 404 "$API_BASE$ep/$CUSTOMER_VIEWER_TENANT" "$CUSTOMER_ADMIN_TOKEN"
done

section "13. Anti-enumeration sanity check: nonexistent tenant looks identical to wrong tenant"

check_status "GET /customer/dashboard/NOSUCHTENANT as customer_viewer" 404 "$API_BASE/customer/dashboard/NOSUCHTENANT" "$CUSTOMER_VIEWER_TOKEN"
check_status "GET /customer/incidents/NOSUCHTENANT as customer_viewer" 404 "$API_BASE/customer/incidents/NOSUCHTENANT" "$CUSTOMER_VIEWER_TOKEN"

section "14. Final validation verdict"

echo "KB-011 PROTECTED APIS VALIDATION PASSED"
echo
echo "Summary:"
echo "  - /health, /auth/login, /auth/roles, /docs remain public."
echo "  - /auth/me remains protected (KB-010 regression check passed)."
echo "  - All 5 /admin/* endpoints require platform_admin, soc_manager, or soc_analyst (401/403 enforced)."
echo "  - Both /customer/* endpoints require a valid token (401 enforced)."
echo "  - platform_admin/soc_manager/soc_analyst have cross-tenant read access on /customer/*."
echo "  - customer_admin/customer_viewer can only reach their own tenant's /customer/* data (404 on mismatch, not 403)."
echo "  - No response leaked a password_hash field."
echo
echo "Note: scripts/kb008_validate_backend_api_foundation.sh and"
echo "scripts/kb010_validate_auth_rbac.sh are historical validators and are"
echo "expected to fail on their unauthenticated /admin and /customer checks"
echo "now that those endpoints are protected. This is intentional."
echo
echo "======================================================================"
echo "KB-011 validation completed successfully."
echo "======================================================================"
