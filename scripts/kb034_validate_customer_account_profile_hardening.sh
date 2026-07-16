#!/usr/bin/env bash
# KB-034: Validate Customer Account / Profile Hardening.
# Interactive: prompts for customer.viewer@demo.local password (never hardcoded).
# Optional: CUSTOMER_VIEWER_PASSWORD env for non-interactive runs.
# Temporarily changes password during the test and restores it before exit.
set -euo pipefail

PROJECT_DIR="/opt/mssp-control"
API_BASE="http://localhost:8000"
FRONTEND_BASE="http://localhost:3001"
BODY_FILE="/tmp/kb034-body.txt"
LOGIN_FILE="/tmp/kb034-login.json"

ORIGINAL_PASSWORD=""
TEMP_PASSWORD="Kb034TempPass!9x"
ORIGINAL_FULL_NAME=""
ORIGINAL_PHONE=""
VIEWER_TOKEN=""
PASSWORD_CHANGED="0"

cd "$PROJECT_DIR"

echo "======================================================================"
echo "KB-034: Validate Customer Account / Profile Hardening"
echo "Target: $PROJECT_DIR"
echo "======================================================================"

fail() {
  echo
  echo "VALIDATION FAILED: $1" >&2
  restore_account_state || true
  rm -f "$BODY_FILE" "$LOGIN_FILE"
  unset ORIGINAL_PASSWORD TEMP_PASSWORD VIEWER_TOKEN 2>/dev/null || true
  exit 1
}

section() {
  echo
  echo "----------------------------------------------------------------------"
  echo "$1"
  echo "----------------------------------------------------------------------"
}

cleanup() {
  restore_account_state || true
  rm -f "$BODY_FILE" "$LOGIN_FILE"
  unset ORIGINAL_PASSWORD TEMP_PASSWORD VIEWER_TOKEN 2>/dev/null || true
}
trap cleanup EXIT

login() {
  local email="$1"
  local password="$2"
  local expected_role="$3"
  local body response token role

  body="$(jq -n --arg email "$email" --arg password "$password" '{email:$email,password:$password}')"
  response="$(curl -sS -X POST "$API_BASE/auth/login" \
    -H "Content-Type: application/json" \
    -d "$body" -o "$LOGIN_FILE" -w "%{http_code}" || true)"
  [ "$response" = "200" ] || return 1
  token="$(jq -r '.access_token // empty' "$LOGIN_FILE")"
  role="$(jq -r '.user.role // empty' "$LOGIN_FILE")"
  [ -n "$token" ] || return 1
  [ "$role" = "$expected_role" ] || return 1
  echo "$token"
}

restore_account_state() {
  # Best-effort: restore password then profile fields.
  local token=""
  if [ "$PASSWORD_CHANGED" = "1" ] && [ -n "${ORIGINAL_PASSWORD:-}" ]; then
    token="$(login "customer.viewer@demo.local" "$TEMP_PASSWORD" "customer_viewer" 2>/dev/null || true)"
    if [ -n "$token" ]; then
      curl -sS -o /dev/null -X POST "$API_BASE/auth/change-password" \
        -H "Authorization: Bearer $token" \
        -H "Content-Type: application/json" \
        -d "$(jq -n --arg c "$TEMP_PASSWORD" --arg n "$ORIGINAL_PASSWORD" \
          '{current_password:$c,new_password:$n}')" || true
      PASSWORD_CHANGED="0"
    fi
  fi

  token="$(login "customer.viewer@demo.local" "${ORIGINAL_PASSWORD:-}" "customer_viewer" 2>/dev/null || true)"
  if [ -n "$token" ] && [ -n "${ORIGINAL_FULL_NAME:-}" ]; then
    curl -sS -o /dev/null -X PATCH "$API_BASE/auth/me" \
      -H "Authorization: Bearer $token" \
      -H "Content-Type: application/json" \
      -d "$(jq -n --arg n "$ORIGINAL_FULL_NAME" --arg p "${ORIGINAL_PHONE:-}" \
        'if $p == "" then {full_name:$n, phone:null} else {full_name:$n, phone:$p} end')" || true
  fi
}

assert_no_password_material() {
  local label="$1"
  local file="$2"
  local hit
  hit="$(jq -r '
    def check:
      if type == "object" then
        (keys_unsorted[] as $k
          | ($k | ascii_downcase) as $kd
          | if ($kd == "password" or $kd == "password_hash"
                or $kd == "current_password" or $kd == "new_password"
                or $kd == "token_hash")
            then $k else empty end),
        (to_entries[] | .value | check)
      elif type == "array" then .[] | check
      else empty end;
    [check] | unique | .[]
  ' "$file" 2>/dev/null || true)"
  if [ -n "$hit" ]; then
    fail "$label response exposes forbidden key(s): $(echo "$hit" | tr '\n' ' ')"
  fi
}

section "1. Required files exist"

REQUIRED=(
  "backend-api/app/api/routes/auth.py"
  "backend-api/app/schemas/auth.py"
  "backend-api/app/services/auth_service.py"
  "frontend-customer/src/pages/AccountPage.tsx"
  "frontend-customer/src/api/auth.ts"
  "frontend-customer/src/auth/AuthContext.tsx"
  "scripts/kb034_validate_customer_account_profile_hardening.sh"
  "docs/KB034_CUSTOMER_ACCOUNT_PROFILE_HARDENING.md"
)

for f in "${REQUIRED[@]}"; do
  [ -f "$f" ] || fail "$f is missing"
  echo "found: $f"
done

section "2. Protected paths must remain unmodified"

for p in frontend-admin/ postgres/init/ docker-compose.yml; do
  git diff --quiet -- "$p" || fail "$p has working-tree changes but KB-034 must not modify it"
  git diff --cached --quiet -- "$p" || fail "$p has staged changes but KB-034 must not modify it"
  echo "OK: $p unmodified"
done

if git status --porcelain -- .env 2>/dev/null | grep -q .; then
  fail ".env shows as changed/untracked"
fi
echo "OK: .env not changed/untracked."

section "3. Backend source checks"

grep -q 'def update_me' backend-api/app/api/routes/auth.py \
  || fail "auth.py missing update_me (PATCH /me)"
grep -q 'def change_password' backend-api/app/api/routes/auth.py \
  || fail "auth.py missing change_password"
grep -q 'class ProfileUpdateRequest' backend-api/app/schemas/auth.py \
  || fail "schemas/auth.py missing ProfileUpdateRequest"
grep -q 'class ChangePasswordRequest' backend-api/app/schemas/auth.py \
  || fail "schemas/auth.py missing ChangePasswordRequest"
grep -q 'phone' backend-api/app/schemas/auth.py \
  || fail "UserPublic must include phone"
grep -q 'change_own_password' backend-api/app/services/auth_service.py \
  || fail "auth_service missing change_own_password"
grep -q 'current_password' backend-api/app/core/error_handlers.py \
  || fail "error_handlers must treat current_password as sensitive"
echo "OK: backend auth profile/password pieces present."

section "4. Frontend source checks"

grep -q 'changePassword' frontend-customer/src/api/auth.ts \
  || fail "auth.ts missing changePassword"
grep -q 'updateMyProfile' frontend-customer/src/api/auth.ts \
  || fail "auth.ts missing updateMyProfile"
grep -q 'Change password' frontend-customer/src/pages/AccountPage.tsx \
  || fail "AccountPage missing change password UI"
grep -q 'Save profile' frontend-customer/src/pages/AccountPage.tsx \
  || fail "AccountPage missing save profile UI"

if grep -REn '/admin' frontend-customer/src 2>/dev/null; then
  fail "frontend-customer/src must not contain /admin"
fi
echo "OK: frontend account hardening present, no /admin."

section "5. Rebuild backend-api"

docker compose build backend-api || fail "docker compose build backend-api failed"
docker compose up -d backend-api || fail "docker compose up -d backend-api failed"

echo "Waiting for backend /health..."
UP=0
for _ in $(seq 1 40); do
  if curl -fsS "$API_BASE/health" -o "$BODY_FILE" 2>/dev/null; then
    if jq -e '.api == "ok" and .database == "ok" and .redis == "ok"' "$BODY_FILE" >/dev/null 2>&1; then
      UP=1
      break
    fi
  fi
  sleep 1
done
[ "$UP" = "1" ] || fail "backend /health not OK within 40s"
echo "OK: backend health healthy."

section "6. OpenAPI lists new auth routes"

OPENAPI="$(curl -fsS "$API_BASE/openapi.json" || fail "Could not fetch OpenAPI")"
echo "$OPENAPI" | jq -e '.paths["/auth/me"].patch' >/dev/null \
  || fail "OpenAPI missing PATCH /auth/me"
echo "$OPENAPI" | jq -e '.paths | has("/auth/change-password")' >/dev/null \
  || fail "OpenAPI missing /auth/change-password"
echo "OK: OpenAPI registers PATCH /auth/me and POST /auth/change-password."

section "7. Login as customer.viewer@demo.local"

if [ -z "${CUSTOMER_VIEWER_PASSWORD:-}" ]; then
  echo
  read -rs -p "Enter the password for customer.viewer@demo.local: " CUSTOMER_VIEWER_PASSWORD
  echo
fi
[ -n "${CUSTOMER_VIEWER_PASSWORD:-}" ] || fail "Password was empty"
ORIGINAL_PASSWORD="$CUSTOMER_VIEWER_PASSWORD"
unset CUSTOMER_VIEWER_PASSWORD

VIEWER_TOKEN="$(login "customer.viewer@demo.local" "$ORIGINAL_PASSWORD" "customer_viewer")" \
  || fail "Login failed for customer.viewer@demo.local"
echo "OK: logged in as customer_viewer."

section "8. GET /auth/me includes phone and no password material"

HTTP_CODE="$(curl -sS -o "$BODY_FILE" -w "%{http_code}" \
  -H "Authorization: Bearer $VIEWER_TOKEN" \
  "$API_BASE/auth/me" || true)"
[ "$HTTP_CODE" = "200" ] || fail "GET /auth/me expected 200, got $HTTP_CODE"
jq -e 'has("phone") and has("full_name") and has("email")' "$BODY_FILE" >/dev/null \
  || fail "GET /auth/me missing expected profile fields"
assert_no_password_material "GET /auth/me" "$BODY_FILE"
ORIGINAL_FULL_NAME="$(jq -r '.full_name' "$BODY_FILE")"
ORIGINAL_PHONE="$(jq -r '.phone // empty' "$BODY_FILE")"
echo "OK: /auth/me returns phone-capable public profile."

section "9. PATCH /auth/me updates name/phone only"

HTTP_CODE="$(curl -sS -o "$BODY_FILE" -w "%{http_code}" \
  -X PATCH \
  -H "Authorization: Bearer $VIEWER_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"full_name":"KB034 Demo Viewer","phone":"+1000340340"}' \
  "$API_BASE/auth/me" || true)"
[ "$HTTP_CODE" = "200" ] || fail "PATCH /auth/me expected 200, got $HTTP_CODE ($(cat "$BODY_FILE"))"
jq -e '.full_name == "KB034 Demo Viewer" and .phone == "+1000340340"' "$BODY_FILE" >/dev/null \
  || fail "PATCH /auth/me did not apply name/phone"
assert_no_password_material "PATCH /auth/me" "$BODY_FILE"

HTTP_CODE="$(curl -sS -o "$BODY_FILE" -w "%{http_code}" \
  -X PATCH \
  -H "Authorization: Bearer $VIEWER_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"email":"attacker@example.invalid"}' \
  "$API_BASE/auth/me" || true)"
[ "$HTTP_CODE" = "422" ] || fail "PATCH with email should be 422, got $HTTP_CODE"
echo "OK: profile update works; email change rejected."

section "10. Change password (then restore)"

HTTP_CODE="$(curl -sS -o "$BODY_FILE" -w "%{http_code}" \
  -X POST \
  -H "Authorization: Bearer $VIEWER_TOKEN" \
  -H "Content-Type: application/json" \
  -d "$(jq -n --arg c "$ORIGINAL_PASSWORD" --arg n "$TEMP_PASSWORD" \
    '{current_password:$c,new_password:$n}')" \
  "$API_BASE/auth/change-password" || true)"
[ "$HTTP_CODE" = "200" ] || fail "change-password expected 200, got $HTTP_CODE ($(cat "$BODY_FILE"))"
PASSWORD_CHANGED="1"
assert_no_password_material "change-password" "$BODY_FILE"

NEW_TOKEN="$(login "customer.viewer@demo.local" "$TEMP_PASSWORD" "customer_viewer")" \
  || fail "Login with new password failed"
VIEWER_TOKEN="$NEW_TOKEN"

HTTP_CODE="$(curl -sS -o "$BODY_FILE" -w "%{http_code}" \
  -X POST \
  -H "Authorization: Bearer $VIEWER_TOKEN" \
  -H "Content-Type: application/json" \
  -d "$(jq -n --arg c "definitely-wrong-password" --arg n "$TEMP_PASSWORD" \
    '{current_password:$c,new_password:$n}')" \
  "$API_BASE/auth/change-password" || true)"
[ "$HTTP_CODE" = "401" ] || fail "Wrong current password expected 401, got $HTTP_CODE"

HTTP_CODE="$(curl -sS -o "$BODY_FILE" -w "%{http_code}" \
  -X POST \
  -H "Authorization: Bearer $VIEWER_TOKEN" \
  -H "Content-Type: application/json" \
  -d "$(jq -n --arg c "$TEMP_PASSWORD" --arg n "$ORIGINAL_PASSWORD" \
    '{current_password:$c,new_password:$n}')" \
  "$API_BASE/auth/change-password" || true)"
[ "$HTTP_CODE" = "200" ] || fail "Restore original password expected 200, got $HTTP_CODE"
PASSWORD_CHANGED="0"

login "customer.viewer@demo.local" "$ORIGINAL_PASSWORD" "customer_viewer" >/dev/null \
  || fail "Login with restored original password failed"
echo "OK: password change and restore succeeded."

section "11. Frontend build"

if docker compose exec -T frontend-customer npm run build; then
  echo "OK: npm run build succeeded inside frontend-customer."
else
  fail "npm run build failed inside frontend-customer"
fi

section "12. Docs present"

[ -f "docs/KB034_CUSTOMER_ACCOUNT_PROFILE_HARDENING.md" ] || fail "docs missing"
grep -q 'change-password' docs/KB034_CUSTOMER_ACCOUNT_PROFILE_HARDENING.md \
  || fail "docs missing change-password"
echo "OK: docs present."

section "13. Manual browser note"

echo "Open $FRONTEND_BASE, sign in as customer.viewer@demo.local,"
echo "open Account, update name/phone, and optionally change password."

section "14. Final verdict"

echo "======================================================================"
echo "KB-034 CUSTOMER ACCOUNT PROFILE HARDENING VALIDATION PASSED"
echo "======================================================================"
