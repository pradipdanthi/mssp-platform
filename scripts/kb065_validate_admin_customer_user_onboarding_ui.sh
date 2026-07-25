#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="/opt/mssp-control"
API_BASE="http://localhost:8000"
FRONTEND_BASE="http://localhost:3000"
BODY_FILE="/tmp/kb065-body.json"
ADMIN_EMAIL="${KB065_ADMIN_EMAIL:-${PLATFORM_ADMIN_EMAIL:-platform.admin@example.local}}"
ADMIN_PASSWORD="${KB065_ADMIN_PASSWORD:-${PLATFORM_ADMIN_PASSWORD:-}}"
SKIP_LIVE="${SKIP_LIVE:-0}"

cd "$PROJECT_DIR"

echo "======================================================================"
echo "KB-065: Validate Admin Customer/User Onboarding UI"
echo "Target: $PROJECT_DIR"
echo "======================================================================"

fail() {
  echo
  echo "VALIDATION FAILED: $1"
  echo "Recent frontend-admin logs:"
  docker compose logs --tail=60 frontend-admin 2>/dev/null || true
  rm -f "$BODY_FILE"
  exit 1
}

section() {
  echo
  echo "----------------------------------------------------------------------"
  echo "$1"
  echo "----------------------------------------------------------------------"
}

cleanup_api_fixtures() {
  # Soft-cleanup: mark validation tenant inactive if it exists; remove validation user if present.
  if [[ -n "${TOKEN:-}" && -n "${CREATED_TENANT_ID:-}" ]]; then
    curl -sS -o /dev/null -w "" -X PATCH \
      -H "Authorization: Bearer $TOKEN" \
      -H "Content-Type: application/json" \
      -d '{"status":"inactive","notes":"kb065 validation cleanup"}' \
      "$API_BASE/admin/tenants/$CREATED_TENANT_ID" || true
  fi
  if [[ -n "${TOKEN:-}" && -n "${CREATED_USER_ID:-}" ]]; then
    curl -sS -o /dev/null -w "" -X PATCH \
      -H "Authorization: Bearer $TOKEN" \
      -H "Content-Type: application/json" \
      -d '{"status":"inactive"}' \
      "$API_BASE/admin/users/$CREATED_USER_ID" || true
  fi
  rm -f "$BODY_FILE"
}
trap cleanup_api_fixtures EXIT

section "1. Expected frontend files exist"

REQUIRED_FILES=(
  "frontend-admin/src/api/admin.ts"
  "frontend-admin/src/pages/TenantsPage.tsx"
  "frontend-admin/src/pages/UsersPage.tsx"
  "frontend-admin/src/components/Layout.tsx"
  "frontend-admin/src/styles.css"
  "docs/KB065_ADMIN_CUSTOMER_UI_FEATURE_GAPS.md"
  "scripts/kb065_validate_admin_customer_user_onboarding_ui.sh"
)

for f in "${REQUIRED_FILES[@]}"; do
  [ -f "$f" ] || fail "$f is missing"
  echo "found: $f"
done

section "2. Source contains onboarding UI markers"

grep -q "Add Customer" frontend-admin/src/pages/TenantsPage.tsx || fail "TenantsPage missing Add Customer"
grep -q "createTenant" frontend-admin/src/pages/TenantsPage.tsx || fail "TenantsPage missing createTenant"
grep -q "updateTenant" frontend-admin/src/pages/TenantsPage.tsx || fail "TenantsPage missing updateTenant"
grep -q "Add User" frontend-admin/src/pages/UsersPage.tsx || fail "UsersPage missing Add User"
grep -q "createUser" frontend-admin/src/pages/UsersPage.tsx || fail "UsersPage missing createUser"
grep -q "updateUserPassword" frontend-admin/src/pages/UsersPage.tsx || fail "UsersPage missing updateUserPassword"
grep -q 'label: "Customers"' frontend-admin/src/components/Layout.tsx || fail "Layout nav missing Customers label"
grep -q "export function createTenant" frontend-admin/src/api/admin.ts || fail "admin.ts missing createTenant"
grep -q "export function createUser" frontend-admin/src/api/admin.ts || fail "admin.ts missing createUser"
echo "OK: onboarding UI source markers present"

section "3. No secrets in frontend source"

# Comments that say we deliberately omit password_hash are allowed.
if grep -RInE 'JWT_SECRET|ChangeMe123!|appliance_api_key\s*=' frontend-admin/src --include='*.ts' --include='*.tsx' | grep -q .; then
  fail "Suspicious secret-like content found in frontend-admin/src"
fi
# Fail only if a response type declares password_hash (request password for create is allowed).
if grep -RInE 'password_hash' frontend-admin/src --include='*.ts' --include='*.tsx' | grep -v 'Intentionally no password' | grep -v 'password/password_hash' | grep -v 'no password' | grep -q .; then
  fail "Frontend must not use password_hash except in intentional omit-comments"
fi
echo "OK: no obvious secret literals in frontend source"

section "4. Containers healthy"

docker compose ps --status running | grep -q "mssp-frontend-admin" || fail "frontend-admin not running"
docker compose ps --status running | grep -q "mssp-backend-api" || fail "backend-api not running"
curl -fsS "$API_BASE/health" | grep -q '"api":"ok"' || fail "/health not ok"
curl -fsS -o /dev/null -w "%{http_code}" "$FRONTEND_BASE/" | grep -Eq '200|304' || fail "frontend-admin not serving"
echo "OK: frontend-admin and backend-api are up"

section "5. Live UI source served (Vite bind-mount)"

# Dev image bind-mounts host frontend-admin/src — confirm container can see Add Customer.
docker compose exec -T frontend-admin sh -c 'grep -q "Add Customer" /app/src/pages/TenantsPage.tsx' \
  || fail "Container TenantsPage.tsx missing Add Customer (bind mount / rebuild issue)"
docker compose exec -T frontend-admin sh -c 'grep -q "Add User" /app/src/pages/UsersPage.tsx' \
  || fail "Container UsersPage.tsx missing Add User"
echo "OK: container serves updated Tenants/Users pages"

section "6. Live API onboarding path (same APIs the UI calls)"

if [[ "$SKIP_LIVE" == "1" ]]; then
  echo "SKIP_LIVE=1 — skipping live API create/update proof"
elif [[ -z "$ADMIN_PASSWORD" ]]; then
  echo "PLATFORM_ADMIN_PASSWORD / KB065_ADMIN_PASSWORD not set — skipping live API proof"
  echo "(UI source checks already passed. Re-run with PLATFORM_ADMIN_PASSWORD set for full gate.)"
else
  LOGIN_CODE=$(curl -sS -o "$BODY_FILE" -w "%{http_code}" \
    -H "Content-Type: application/json" \
    -d "{\"email\":\"$ADMIN_EMAIL\",\"password\":\"$ADMIN_PASSWORD\"}" \
    "$API_BASE/auth/login")
  unset ADMIN_PASSWORD
  [[ "$LOGIN_CODE" == "200" ]] || fail "platform_admin login failed (HTTP $LOGIN_CODE)"
  TOKEN=$(python3 -c 'import json; print(json.load(open("'"$BODY_FILE"'"))["access_token"])')
  [[ -n "$TOKEN" ]] || fail "login response missing access_token"

  SHORT="KB065$(date +%s | tail -c 5)"
  CREATE_TENANT_CODE=$(curl -sS -o "$BODY_FILE" -w "%{http_code}" \
    -X POST \
    -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: application/json" \
    -d "{\"name\":\"KB065 Validation Customer\",\"short_code\":\"$SHORT\",\"status\":\"onboarding\",\"sla_level\":\"standard\",\"business_criticality\":\"medium\",\"timezone\":\"Asia/Kolkata\",\"notes\":\"kb065 ui validation\"}" \
    "$API_BASE/admin/tenants")
  [[ "$CREATE_TENANT_CODE" == "201" ]] || fail "POST /admin/tenants returned HTTP $CREATE_TENANT_CODE (body: $(head -c 300 "$BODY_FILE"))"
  CREATED_TENANT_ID=$(python3 -c 'import json; print(json.load(open("'"$BODY_FILE"'"))["id"])')
  echo "OK: created tenant $SHORT ($CREATED_TENANT_ID)"

  USER_EMAIL="kb065.ui.${SHORT}@example.local"
  CREATE_USER_CODE=$(curl -sS -o "$BODY_FILE" -w "%{http_code}" \
    -X POST \
    -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: application/json" \
    -d "{\"email\":\"$USER_EMAIL\",\"full_name\":\"KB065 UI User\",\"password\":\"TempPass123!\",\"role\":\"customer_admin\",\"tenant_id\":\"$CREATED_TENANT_ID\",\"status\":\"active\"}" \
    "$API_BASE/admin/users")
  [[ "$CREATE_USER_CODE" == "201" ]] || fail "POST /admin/users returned HTTP $CREATE_USER_CODE (body: $(head -c 300 "$BODY_FILE"))"
  CREATED_USER_ID=$(python3 -c 'import json; print(json.load(open("'"$BODY_FILE"'"))["id"])')
  python3 -c 'import json; d=json.load(open("'"$BODY_FILE"'")); assert "password" not in d and "password_hash" not in d' \
    || fail "user create response leaked password fields"
  echo "OK: created customer_admin $USER_EMAIL ($CREATED_USER_ID) without password leakage"

  PATCH_TENANT_CODE=$(curl -sS -o "$BODY_FILE" -w "%{http_code}" \
    -X PATCH \
    -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: application/json" \
    -d '{"status":"active","sla_level":"business"}' \
    "$API_BASE/admin/tenants/$CREATED_TENANT_ID")
  [[ "$PATCH_TENANT_CODE" == "200" ]] || fail "PATCH tenant failed HTTP $PATCH_TENANT_CODE"
  echo "OK: PATCH tenant works"

  PATCH_USER_CODE=$(curl -sS -o "$BODY_FILE" -w "%{http_code}" \
    -X PATCH \
    -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: application/json" \
    -d '{"status":"inactive"}' \
    "$API_BASE/admin/users/$CREATED_USER_ID")
  [[ "$PATCH_USER_CODE" == "200" ]] || fail "PATCH user failed HTTP $PATCH_USER_CODE"
  echo "OK: PATCH user works"
fi

echo
echo "======================================================================"
echo "KB-065 ADMIN CUSTOMER/USER ONBOARDING UI VALIDATION PASSED"
echo "======================================================================"
