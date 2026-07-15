#!/usr/bin/env bash
# KB-022: Validate Customer Alerts API + Customer Alerts Page.
# Interactive: prompts for customer.viewer@demo.local password (never hardcoded).
set -euo pipefail

PROJECT_DIR="/opt/mssp-control"
API_BASE="http://localhost:8000"
FRONTEND_BASE="http://localhost:3001"
BODY_FILE="/tmp/kb022-body.txt"
LOGIN_FILE="/tmp/kb022-login.json"

cd "$PROJECT_DIR"

echo "======================================================================"
echo "KB-022: Validate Customer Alerts API and Customer Alerts Page"
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
  # Check JSON object *keys* only (recursively). String values may mention
  # password attacks etc. without exposing sensitive fields.
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
          . == "raw_event"
          or . == "external_alert_id"
          or . == "ai_technical_summary"
          or . == "mitre_mapping"
          or . == "ai_false_positive_score"
          or . == "false_positive"
          or . == "api_key"
          or . == "token_hash"
          or . == "password"
          or . == "password_hash"
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
  "frontend-customer/src/pages/AlertsPage.tsx"
  "scripts/kb022_validate_customer_alerts_api_ui.sh"
  "docs/KB022_CUSTOMER_ALERTS_API_UI.md"
)

for f in "${REQUIRED[@]}"; do
  [ -f "$f" ] || fail "$f is missing"
  echo "found: $f"
done

section "2. Protected paths must remain unmodified by this module"

for p in frontend-admin/ postgres/init/ docker-compose.yml; do
  if [ -e "$p" ] || [ -d "$p" ]; then
    git diff --quiet -- "$p" || fail "$p has working-tree changes but KB-022 must not modify it"
    git diff --cached --quiet -- "$p" || fail "$p has staged changes but KB-022 must not modify it"
  fi
  echo "OK: $p unmodified"
done

if git status --porcelain -- .env 2>/dev/null | grep -q .; then
  fail ".env shows as changed/untracked"
fi
echo "OK: .env not changed/untracked."

section "3. Backend source: alerts endpoint + customer_visible filter"

grep -q '@router.get("/alerts/{short_code}")' backend-api/app/api/routes/customer.py \
  || fail "customer.py missing GET /alerts/{short_code}"
grep -q 'customer_visible = true' backend-api/app/api/routes/customer.py \
  || fail "customer alerts query missing customer_visible = true"
grep -q 'require_tenant_match' backend-api/app/api/routes/customer.py \
  || fail "customer.py missing require_tenant_match"
grep -q 'alert_id' backend-api/app/api/routes/customer.py \
  || fail "customer alerts SELECT missing alert_id alias"
echo "OK: customer alerts route uses tenant match + customer_visible = true."

section "4. Frontend: getCustomerAlerts + no /admin"

grep -q 'getCustomerAlerts' frontend-customer/src/api/customer.ts \
  || fail "customer.ts missing getCustomerAlerts"
grep -q '/customer/alerts/' frontend-customer/src/api/customer.ts \
  || fail "customer.ts missing /customer/alerts/ path"
grep -q 'getCustomerAlerts' frontend-customer/src/pages/AlertsPage.tsx \
  || fail "AlertsPage.tsx must call getCustomerAlerts"

if grep -REn '/admin' frontend-customer/src 2>/dev/null; then
  fail "frontend-customer/src must not contain /admin"
fi
echo "OK: frontend uses /customer/alerts and has no /admin string."

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

section "6. OpenAPI lists /customer/alerts/{short_code}"

OPENAPI="$(curl -fsS "$API_BASE/openapi.json" || fail "Could not fetch OpenAPI")"
echo "$OPENAPI" | jq -e '.paths | has("/customer/alerts/{short_code}")' >/dev/null \
  || fail "OpenAPI missing /customer/alerts/{short_code}"
echo "OK: OpenAPI registers /customer/alerts/{short_code}."

section "7. Unauthenticated access returns 401"

HTTP_CODE="$(curl -sS -o "$BODY_FILE" -w "%{http_code}" "$API_BASE/customer/alerts/DEMO" || true)"
[ "$HTTP_CODE" = "401" ] || fail "Unauthenticated GET /customer/alerts/DEMO expected 401, got $HTTP_CODE"
echo "OK: unauthenticated request returns 401."

section "8. Login as customer.viewer@demo.local"

# Prefer env CUSTOMER_VIEWER_PASSWORD when set (automation); otherwise prompt (never logged).
if [ -z "${CUSTOMER_VIEWER_PASSWORD:-}" ]; then
  echo
  read -rs -p "Enter the password for customer.viewer@demo.local: " CUSTOMER_VIEWER_PASSWORD
  echo
fi
[ -n "${CUSTOMER_VIEWER_PASSWORD:-}" ] || fail "Password was empty (set CUSTOMER_VIEWER_PASSWORD or type at prompt)"
CUSTOMER_VIEWER_TOKEN="$(login "customer.viewer@demo.local" "$CUSTOMER_VIEWER_PASSWORD" "customer_viewer")"
unset CUSTOMER_VIEWER_PASSWORD
echo "OK: logged in as customer_viewer."

section "9. customer.viewer can call /customer/alerts/DEMO"

HTTP_CODE="$(curl -sS -o "$BODY_FILE" -w "%{http_code}" \
  -H "Authorization: Bearer $CUSTOMER_VIEWER_TOKEN" \
  "$API_BASE/customer/alerts/DEMO" || true)"
[ "$HTTP_CODE" = "200" ] || fail "GET /customer/alerts/DEMO expected 200, got $HTTP_CODE ($(cat "$BODY_FILE"))"

jq -e '.tenant.short_code == "DEMO"' "$BODY_FILE" >/dev/null \
  || fail "DEMO alerts response missing tenant.short_code DEMO"
jq -e '.alerts | type == "array"' "$BODY_FILE" >/dev/null \
  || fail "DEMO alerts response missing alerts array"
assert_no_forbidden_payload "DEMO alerts" "$BODY_FILE"

# Every alert object must only expose customer-safe keys (when any exist).
ALERT_COUNT="$(jq '.alerts | length' "$BODY_FILE")"
if [ "$ALERT_COUNT" -gt 0 ]; then
  jq -e '
    .alerts
    | map(keys)
    | flatten
    | unique
    | all(.[]; . == "alert_id" or . == "title" or . == "severity" or . == "status"
        or . == "source" or . == "summary" or . == "description"
        or . == "detected_at" or . == "hostname")
  ' "$BODY_FILE" >/dev/null \
    || fail "alerts objects contain unexpected keys"
fi
echo "OK: DEMO alerts response shape is customer-safe (alerts length=$ALERT_COUNT)."

section "10. customer.viewer cannot call /customer/alerts/DEMO2 (expect 404)"

HTTP_CODE="$(curl -sS -o "$BODY_FILE" -w "%{http_code}" \
  -H "Authorization: Bearer $CUSTOMER_VIEWER_TOKEN" \
  "$API_BASE/customer/alerts/DEMO2" || true)"
[ "$HTTP_CODE" = "404" ] || fail "GET /customer/alerts/DEMO2 as DEMO viewer expected 404, got $HTTP_CODE"
echo "OK: cross-tenant alerts access returns 404."

section "11. Frontend build"

if docker compose exec -T frontend-customer npm run build; then
  echo "OK: npm run build succeeded inside frontend-customer."
else
  fail "npm run build failed inside frontend-customer"
fi

section "12. Docs present"

[ -f "docs/KB022_CUSTOMER_ALERTS_API_UI.md" ] || fail "docs/KB022_CUSTOMER_ALERTS_API_UI.md missing"
grep -q 'customer_visible' docs/KB022_CUSTOMER_ALERTS_API_UI.md \
  || fail "docs missing customer_visible explanation"
grep -q 'GET /customer/alerts' docs/KB022_CUSTOMER_ALERTS_API_UI.md \
  || fail "docs missing endpoint documentation"
echo "OK: completion docs present."

section "13. Manual browser note"

echo "curl validates API auth/tenant isolation and frontend build."
echo "Manually open $FRONTEND_BASE, sign in as customer.viewer@demo.local,"
echo "open Alerts, and confirm a read-only list or empty state (no admin APIs)."

section "14. Final verdict"

echo "======================================================================"
echo "KB-022 CUSTOMER ALERTS API UI VALIDATION PASSED"
echo "======================================================================"
