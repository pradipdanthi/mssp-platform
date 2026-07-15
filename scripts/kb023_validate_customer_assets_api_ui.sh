#!/usr/bin/env bash
# KB-023: Validate Customer Assets API + Customer Assets Page.
# Interactive: prompts for customer.viewer@demo.local password (never hardcoded).
# Optional: CUSTOMER_VIEWER_PASSWORD env for non-interactive runs.
set -euo pipefail

PROJECT_DIR="/opt/mssp-control"
API_BASE="http://localhost:8000"
FRONTEND_BASE="http://localhost:3001"
BODY_FILE="/tmp/kb023-body.txt"
LOGIN_FILE="/tmp/kb023-login.json"

cd "$PROJECT_DIR"

echo "======================================================================"
echo "KB-023: Validate Customer Assets API and Customer Assets Page"
echo "Target: $PROJECT_DIR"
echo "======================================================================"

fail() {
  echo
  echo "VALIDATION FAILED: $1" >&2
  rm -f "$BODY_FILE" "$LOGIN_FILE"
  exit 1
}

section() {
  echo
  echo "----------------------------------------------------------------------"
  echo "$1"
  echo "----------------------------------------------------------------------"
}

cleanup() {
  rm -f "$BODY_FILE" "$LOGIN_FILE"
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
  [ "$response" = "200" ] || fail "Login failed for $email (HTTP $response)"
  token="$(jq -r '.access_token // empty' "$LOGIN_FILE")"
  role="$(jq -r '.user.role // empty' "$LOGIN_FILE")"
  [ -n "$token" ] || fail "Login for $email returned no access_token"
  [ "$role" = "$expected_role" ] || fail "Login for $email expected role $expected_role, got $role"
  echo "$token"
}

assert_no_forbidden_payload() {
  local label="$1"
  local file="$2"
  local hit
  # Check JSON object *keys* only (recursively). Values must never become keys.
  hit="$(jq -r '
    def all_keys:
      if type == "object" then
        keys_unsorted[] ,
        (.[] | all_keys)
      elif type == "array" then
        .[] | all_keys
      else
        empty
      end;
    [
      all_keys
      | ascii_downcase
      | select(
          . == "api_key"
          or . == "token_hash"
          or . == "appliance_api_key_hash"
          or . == "appliance_api_key_hint"
          or . == "activation"
          or . == "password_hash"
          or . == "health_snapshot"
          or . == "details"
          or . == "raw_event"
          or . == "source_ip"
          or . == "local_ip"
          or . == "ip_address"
        )
    ]
    | unique
    | .[]
  ' "$file" 2>/dev/null || true)"
  if [ -n "$hit" ]; then
    fail "$label response exposes forbidden field key(s): $(echo "$hit" | tr '\n' ' ')"
  fi
  echo "OK: $label has no forbidden sensitive field keys."
}

section "1. Required files exist"

REQUIRED=(
  "backend-api/app/api/routes/customer.py"
  "frontend-customer/src/api/customer.ts"
  "frontend-customer/src/pages/AssetsPage.tsx"
  "scripts/kb023_validate_customer_assets_api_ui.sh"
  "docs/KB023_CUSTOMER_ASSETS_API_UI.md"
)

for f in "${REQUIRED[@]}"; do
  [ -f "$f" ] || fail "$f is missing"
  echo "found: $f"
done

section "2. Protected paths must remain unmodified"

for p in frontend-admin/ postgres/init/ docker-compose.yml; do
  git diff --quiet -- "$p" || fail "$p has working-tree changes but KB-023 must not modify it"
  git diff --cached --quiet -- "$p" || fail "$p has staged changes but KB-023 must not modify it"
  echo "OK: $p unmodified"
done

if git status --porcelain -- .env 2>/dev/null | grep -q .; then
  fail ".env shows as changed/untracked"
fi
echo "OK: .env not changed/untracked."

section "3. Backend source: assets endpoint + tenant filter"

grep -q '@router.get("/assets/{short_code}")' backend-api/app/api/routes/customer.py \
  || fail "customer.py missing GET /assets/{short_code}"
grep -q 'require_tenant_match' backend-api/app/api/routes/customer.py \
  || fail "customer.py missing require_tenant_match"
grep -c 'WHERE.*tenant_id' backend-api/app/api/routes/customer.py >/dev/null \
  || fail "customer assets queries missing tenant_id filters"
grep -q 'protected_assets' backend-api/app/api/routes/customer.py \
  || fail "customer assets query missing protected_assets"
echo "OK: customer assets route present with tenant isolation."

section "4. Frontend: getCustomerAssets + no /admin"

grep -q 'getCustomerAssets' frontend-customer/src/api/customer.ts \
  || fail "customer.ts missing getCustomerAssets"
grep -q '/customer/assets/' frontend-customer/src/api/customer.ts \
  || fail "customer.ts missing /customer/assets/ path"
grep -q 'getCustomerAssets' frontend-customer/src/pages/AssetsPage.tsx \
  || fail "AssetsPage.tsx must call getCustomerAssets"
grep -q 'getCustomerDashboard' frontend-customer/src/pages/AssetsPage.tsx \
  && fail "AssetsPage.tsx must not call getCustomerDashboard anymore"

if grep -REn '/admin' frontend-customer/src 2>/dev/null; then
  fail "frontend-customer/src must not contain /admin"
fi
echo "OK: frontend uses /customer/assets and has no /admin string."

section "5. Rebuild backend-api so the new route is live"

echo "Running: docker compose build backend-api"
docker compose build backend-api || fail "docker compose build backend-api failed"
echo "Running: docker compose up -d backend-api"
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

section "6. OpenAPI lists /customer/assets/{short_code}"

OPENAPI="$(curl -fsS "$API_BASE/openapi.json" || fail "Could not fetch OpenAPI")"
echo "$OPENAPI" | jq -e '.paths | has("/customer/assets/{short_code}")' >/dev/null \
  || fail "OpenAPI missing /customer/assets/{short_code}"
echo "OK: OpenAPI registers /customer/assets/{short_code}."

section "7. Unauthenticated access returns 401"

HTTP_CODE="$(curl -sS -o "$BODY_FILE" -w "%{http_code}" "$API_BASE/customer/assets/DEMO" || true)"
[ "$HTTP_CODE" = "401" ] || fail "Unauthenticated GET /customer/assets/DEMO expected 401, got $HTTP_CODE"
echo "OK: unauthenticated request returns 401."

section "8. Login as customer.viewer@demo.local"

if [ -z "${CUSTOMER_VIEWER_PASSWORD:-}" ]; then
  echo
  read -rs -p "Enter the password for customer.viewer@demo.local: " CUSTOMER_VIEWER_PASSWORD
  echo
fi
[ -n "${CUSTOMER_VIEWER_PASSWORD:-}" ] || fail "Password was empty (set CUSTOMER_VIEWER_PASSWORD or type at prompt)"
CUSTOMER_VIEWER_TOKEN="$(login "customer.viewer@demo.local" "$CUSTOMER_VIEWER_PASSWORD" "customer_viewer")"
unset CUSTOMER_VIEWER_PASSWORD
echo "OK: logged in as customer_viewer."

section "9. customer.viewer can call /customer/assets/DEMO"

HTTP_CODE="$(curl -sS -o "$BODY_FILE" -w "%{http_code}" \
  -H "Authorization: Bearer $CUSTOMER_VIEWER_TOKEN" \
  "$API_BASE/customer/assets/DEMO" || true)"
[ "$HTTP_CODE" = "200" ] || fail "GET /customer/assets/DEMO expected 200, got $HTTP_CODE ($(cat "$BODY_FILE"))"

jq -e '.tenant.short_code == "DEMO"' "$BODY_FILE" >/dev/null \
  || fail "DEMO assets response missing tenant.short_code DEMO"
jq -e '.appliances | type == "array"' "$BODY_FILE" >/dev/null \
  || fail "DEMO assets response missing appliances array"
jq -e '.assets | type == "array"' "$BODY_FILE" >/dev/null \
  || fail "DEMO assets response missing assets array"
assert_no_forbidden_payload "DEMO assets" "$BODY_FILE"
echo "OK: DEMO assets response shape is customer-safe (appliances=$(jq '.appliances | length' "$BODY_FILE"), assets=$(jq '.assets | length' "$BODY_FILE"))."

section "10. customer.viewer cannot call /customer/assets/DEMO2 (expect 404)"

HTTP_CODE="$(curl -sS -o "$BODY_FILE" -w "%{http_code}" \
  -H "Authorization: Bearer $CUSTOMER_VIEWER_TOKEN" \
  "$API_BASE/customer/assets/DEMO2" || true)"
[ "$HTTP_CODE" = "404" ] || fail "GET /customer/assets/DEMO2 as DEMO viewer expected 404, got $HTTP_CODE"
echo "OK: cross-tenant assets access returns 404."

section "11. Frontend build"

if docker compose exec -T frontend-customer npm run build; then
  echo "OK: npm run build succeeded inside frontend-customer."
else
  fail "npm run build failed inside frontend-customer"
fi

section "12. Docs present"

[ -f "docs/KB023_CUSTOMER_ASSETS_API_UI.md" ] || fail "docs/KB023_CUSTOMER_ASSETS_API_UI.md missing"
grep -q 'GET /customer/assets' docs/KB023_CUSTOMER_ASSETS_API_UI.md \
  || fail "docs missing endpoint documentation"
grep -qi 'tenant' docs/KB023_CUSTOMER_ASSETS_API_UI.md \
  || fail "docs missing tenant isolation explanation"
echo "OK: completion docs present."

section "13. Manual browser note"

echo "curl validates API auth/tenant isolation and frontend build."
echo "Manually open $FRONTEND_BASE, sign in as customer.viewer@demo.local,"
echo "open Assets, and confirm appliance + protected-asset tables (or empty states)."

section "14. Final verdict"

echo "======================================================================"
echo "KB-023 CUSTOMER ASSETS API UI VALIDATION PASSED"
echo "======================================================================"
