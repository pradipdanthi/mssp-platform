#!/usr/bin/env bash
# KB-028: Validate Customer Dashboard v2 (frontend-only composition).
# Interactive: prompts for customer.viewer@demo.local password (never hardcoded).
# Optional: CUSTOMER_VIEWER_PASSWORD env for non-interactive runs.
set -euo pipefail

PROJECT_DIR="/opt/mssp-control"
API_BASE="http://localhost:8000"
FRONTEND_BASE="http://localhost:3001"
BODY_FILE="/tmp/kb028-body.txt"
LOGIN_FILE="/tmp/kb028-login.json"

cd "$PROJECT_DIR"

echo "======================================================================"
echo "KB-028: Validate Customer Dashboard v2 / Portal Polish"
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

section "1. Required files exist"

REQUIRED=(
  "frontend-customer/src/pages/DashboardPage.tsx"
  "frontend-customer/src/api/customer.ts"
  "frontend-customer/src/styles.css"
  "frontend-customer/src/App.tsx"
  "frontend-customer/src/components/Layout.tsx"
  "scripts/kb028_validate_customer_dashboard_v2.sh"
  "docs/KB028_CUSTOMER_DASHBOARD_V2.md"
)

for f in "${REQUIRED[@]}"; do
  [ -f "$f" ] || fail "$f is missing"
  echo "found: $f"
done

section "2. Protected paths must remain unmodified"

for p in frontend-admin/ postgres/init/ docker-compose.yml; do
  git diff --quiet -- "$p" || fail "$p has working-tree changes but KB-028 must not modify it"
  git diff --cached --quiet -- "$p" || fail "$p has staged changes but KB-028 must not modify it"
  echo "OK: $p unmodified"
done

if git status --porcelain -- .env 2>/dev/null | grep -q .; then
  fail ".env shows as changed/untracked"
fi
echo "OK: .env not changed/untracked."

section "3. Frontend: Dashboard v2 helper + no /admin"

grep -q 'getCustomerDashboardV2' frontend-customer/src/api/customer.ts \
  || fail "customer.ts missing getCustomerDashboardV2"
grep -q 'getCustomerIncidents' frontend-customer/src/api/customer.ts \
  || fail "customer.ts missing getCustomerIncidents"
grep -q 'getCustomerAlerts' frontend-customer/src/api/customer.ts \
  || fail "customer.ts missing getCustomerAlerts"
grep -q 'getCustomerRecommendations' frontend-customer/src/api/customer.ts \
  || fail "customer.ts missing getCustomerRecommendations"
grep -q 'getCustomerAssets' frontend-customer/src/api/customer.ts \
  || fail "customer.ts missing getCustomerAssets"
grep -q 'getCustomerReports' frontend-customer/src/api/customer.ts \
  || fail "customer.ts missing getCustomerReports"
grep -q 'Promise.all' frontend-customer/src/api/customer.ts \
  || fail "getCustomerDashboardV2 should compose with Promise.all"

# Dashboard v2 must not call legacy dashboard endpoint or admin paths
if grep -n 'getCustomerDashboard(' frontend-customer/src/pages/DashboardPage.tsx 2>/dev/null | grep -v DashboardV2; then
  fail "DashboardPage must not call legacy getCustomerDashboard for KB-028"
fi
grep -q 'getCustomerDashboardV2' frontend-customer/src/pages/DashboardPage.tsx \
  || fail "DashboardPage.tsx must call getCustomerDashboardV2"

if grep -REn '/admin' frontend-customer/src 2>/dev/null; then
  fail "frontend-customer/src must not contain /admin"
fi
if grep -nE '/admin' frontend-customer/src/api/customer.ts 2>/dev/null; then
  fail "customer.ts must not contain /admin"
fi
echo "OK: Dashboard v2 uses composed customer helpers; no /admin."

section "4. Existing customer routes still present"

for r in \
  'path="/dashboard"' \
  'path="/alerts"' \
  'path="/incidents"' \
  'path="/incidents/:incidentNumber"' \
  'path="/assets"' \
  'path="/recommendations"' \
  'path="/recommendations/:recommendationId"' \
  'path="/reports"' \
  'path="/account"'
do
  grep -q "$r" frontend-customer/src/App.tsx || fail "App.tsx missing route $r"
  echo "found route: $r"
done

section "5. Backend health + OpenAPI customer paths"

UP=0
for _ in $(seq 1 20); do
  if curl -fsS "$API_BASE/health" -o "$BODY_FILE" 2>/dev/null; then
    if jq -e '.api == "ok" and .database == "ok" and .redis == "ok"' "$BODY_FILE" >/dev/null 2>&1; then
      UP=1
      break
    fi
  fi
  sleep 1
done
[ "$UP" = "1" ] || fail "backend /health not OK"
echo "OK: backend health healthy."

OPENAPI="$(curl -fsS "$API_BASE/openapi.json" || fail "Could not fetch OpenAPI")"
for path in \
  "/customer/dashboard/{short_code}" \
  "/customer/incidents/{short_code}" \
  "/customer/incidents/{short_code}/{incident_number}" \
  "/customer/alerts/{short_code}" \
  "/customer/assets/{short_code}" \
  "/customer/reports/{short_code}" \
  "/customer/recommendations/{short_code}" \
  "/customer/recommendations/{short_code}/{recommendation_id}"
do
  echo "$OPENAPI" | jq -e --arg p "$path" '.paths | has($p)' >/dev/null \
    || fail "OpenAPI missing $path"
  echo "OpenAPI has $path"
done

section "6. Login as customer.viewer@demo.local"

if [ -z "${CUSTOMER_VIEWER_PASSWORD:-}" ]; then
  echo
  read -rs -p "Enter the password for customer.viewer@demo.local: " CUSTOMER_VIEWER_PASSWORD
  echo
fi
[ -n "${CUSTOMER_VIEWER_PASSWORD:-}" ] || fail "Password was empty (set CUSTOMER_VIEWER_PASSWORD or type at prompt)"
CUSTOMER_VIEWER_TOKEN="$(login "customer.viewer@demo.local" "$CUSTOMER_VIEWER_PASSWORD" "customer_viewer")"
unset CUSTOMER_VIEWER_PASSWORD
echo "OK: logged in as customer_viewer."

section "7. DEMO underlying endpoints return 200"

for path in \
  "/customer/incidents/DEMO" \
  "/customer/alerts/DEMO" \
  "/customer/assets/DEMO" \
  "/customer/reports/DEMO" \
  "/customer/recommendations/DEMO"
do
  HTTP_CODE="$(curl -sS -o "$BODY_FILE" -w "%{http_code}" \
    -H "Authorization: Bearer $CUSTOMER_VIEWER_TOKEN" \
    "$API_BASE$path" || true)"
  [ "$HTTP_CODE" = "200" ] || fail "GET $path expected 200, got $HTTP_CODE"
  echo "OK: $path → 200"
done

section "8. DEMO customer gets 404 for DEMO2 endpoints"

for path in \
  "/customer/incidents/DEMO2" \
  "/customer/alerts/DEMO2" \
  "/customer/assets/DEMO2" \
  "/customer/reports/DEMO2" \
  "/customer/recommendations/DEMO2"
do
  HTTP_CODE="$(curl -sS -o "$BODY_FILE" -w "%{http_code}" \
    -H "Authorization: Bearer $CUSTOMER_VIEWER_TOKEN" \
    "$API_BASE$path" || true)"
  [ "$HTTP_CODE" = "404" ] || fail "GET $path as DEMO viewer expected 404, got $HTTP_CODE"
  echo "OK: $path → 404"
done

section "9. Frontend build"

if docker compose exec -T frontend-customer npm run build; then
  echo "OK: npm run build succeeded inside frontend-customer."
else
  fail "npm run build failed inside frontend-customer"
fi

section "10. Optional frontend proxy health"

if curl -fsS -o /dev/null "$FRONTEND_BASE/" 2>/dev/null; then
  curl -fsS "$FRONTEND_BASE/api/health" -o "$BODY_FILE" \
    || fail "GET /api/health via customer proxy failed"
  jq -e '.api == "ok" and .database == "ok" and .redis == "ok"' "$BODY_FILE" >/dev/null \
    || fail "proxied /api/health unhealthy"
  echo "OK: frontend-customer is up and /api/health proxy works."
else
  echo "NOTE: frontend-customer not reachable on $FRONTEND_BASE — skipped proxy check (build already passed)."
fi

section "11. Docs present"

[ -f "docs/KB028_CUSTOMER_DASHBOARD_V2.md" ] || fail "docs/KB028_CUSTOMER_DASHBOARD_V2.md missing"
grep -q 'getCustomerDashboardV2' docs/KB028_CUSTOMER_DASHBOARD_V2.md \
  || fail "docs missing getCustomerDashboardV2"
grep -qi 'frontend-only\|Frontend-only' docs/KB028_CUSTOMER_DASHBOARD_V2.md \
  || fail "docs missing frontend-only decision"
echo "OK: completion docs present."

section "12. Manual browser note"

echo "curl validates underlying APIs, OpenAPI, and frontend build."
echo "Manually open $FRONTEND_BASE, sign in as customer.viewer@demo.local,"
echo "open Dashboard, and confirm KPI cards + recent sections with links."

section "13. Final verdict"

echo "======================================================================"
echo "KB-028 CUSTOMER DASHBOARD V2 VALIDATION PASSED"
echo "======================================================================"
