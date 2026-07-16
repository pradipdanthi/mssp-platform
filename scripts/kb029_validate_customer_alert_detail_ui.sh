#!/usr/bin/env bash
# KB-029: Validate Customer Alert Detail API + UI.
# Interactive: prompts for customer.viewer@demo.local password (never hardcoded).
# Optional: CUSTOMER_VIEWER_PASSWORD env for non-interactive runs.
# Creates temporary DEMO/DEMO2 security_alerts fixtures, then cleans them up.
set -euo pipefail

PROJECT_DIR="/opt/mssp-control"
API_BASE="http://localhost:8000"
FRONTEND_BASE="http://localhost:3001"
BODY_FILE="/tmp/kb029-body.txt"
LOGIN_FILE="/tmp/kb029-login.json"

DEMO_VISIBLE_TITLE="KB029 DEMO visible alert"
DEMO_HIDDEN_TITLE="KB029 DEMO hidden alert"
DEMO2_VISIBLE_TITLE="KB029 DEMO2 visible alert"

FIXTURE_DEMO_VISIBLE_ID=""
FIXTURE_DEMO_HIDDEN_ID=""
FIXTURE_DEMO2_VISIBLE_ID=""

cd "$PROJECT_DIR"

echo "======================================================================"
echo "KB-029: Validate Customer Alert Detail UI"
echo "Target: $PROJECT_DIR"
echo "======================================================================"

fail() {
  echo
  echo "VALIDATION FAILED: $1" >&2
  cleanup_fixtures || true
  rm -f "$BODY_FILE" "$LOGIN_FILE"
  exit 1
}

section() {
  echo
  echo "----------------------------------------------------------------------"
  echo "$1"
  echo "----------------------------------------------------------------------"
}

psql_scalar() {
  local sql="$1"
  local raw line_count

  raw="$(docker compose exec -T postgres psql \
    -X -q -t -A \
    -v ON_ERROR_STOP=1 \
    -U "${POSTGRES_USER:-mssp_admin}" -d "${POSTGRES_DB:-mssp_control}" \
    -c "$sql" 2>/dev/null)" || return 1

  raw="$(printf '%s\n' "$raw" | sed 's/\r$//' | grep -v '^[[:space:]]*$' || true)"
  line_count="$(printf '%s\n' "$raw" | grep -c '.' || true)"
  if [ "$line_count" != "1" ]; then
    echo "psql_scalar: expected exactly 1 non-blank output line, got $line_count" >&2
    return 1
  fi
  printf '%s' "$raw"
}

cleanup_fixtures() {
  docker compose exec -T postgres psql \
    -X -q -v ON_ERROR_STOP=1 \
    -U "${POSTGRES_USER:-mssp_admin}" -d "${POSTGRES_DB:-mssp_control}" \
    -c "
      DELETE FROM security_alerts
      WHERE alert_title IN (
        '${DEMO_VISIBLE_TITLE}',
        '${DEMO_HIDDEN_TITLE}',
        '${DEMO2_VISIBLE_TITLE}'
      );
    " >/dev/null 2>&1 || true
}

cleanup() {
  cleanup_fixtures
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

assert_safe_detail_payload() {
  local label="$1"
  local file="$2"

  jq -e '
    (. | keys | sort) == ["alert","tenant"]
    and (.tenant | has("id") and has("name") and has("short_code"))
    and (.alert | type == "object")
  ' "$file" >/dev/null \
    || fail "$label top-level / tenant shape invalid"

  jq -e '
    (.alert | keys)
    | all(.[]; . == "alert_id" or . == "title" or . == "severity" or . == "status"
        or . == "source" or . == "summary" or . == "description"
        or . == "detected_at" or . == "hostname")
  ' "$file" >/dev/null \
    || fail "$label alert object has unexpected keys"

  local hit
  hit="$(jq -r '
    def check($path):
      if type == "object" then
        (keys_unsorted[] as $k
          | ($k | ascii_downcase) as $kd
          | if ($kd == "tenant_id"
                or $kd == "appliance_id"
                or $kd == "asset_id"
                or $kd == "protected_asset_id"
                or $kd == "external_alert_id"
                or $kd == "raw_event"
                or $kd == "ai_technical_summary"
                or $kd == "ai_likely_attack_type"
                or $kd == "ai_business_impact"
                or $kd == "ai_recommended_action"
                or $kd == "ai_false_positive_score"
                or $kd == "mitre_mapping"
                or $kd == "customer_visible"
                or $kd == "source_ip"
                or $kd == "destination_ip"
                or $kd == "local_ip"
                or $kd == "ip_address"
                or $kd == "source_user"
                or $kd == "internal_notes"
                or $kd == "admin_notes"
                or $kd == "details"
                or $kd == "raw_json"
                or $kd == "assigned_to_user_id"
                or $kd == "created_by_user_id"
                or $kd == "api_key"
                or $kd == "token"
                or $kd == "token_hash"
                or $kd == "password"
                or $kd == "password_hash"
                or $kd == "stack_trace"
                or $kd == "false_positive"
                or ($kd == "id" and $path != "tenant"))
            then $k
            else empty
            end),
        (to_entries[] | .key as $k | .value | check(if $path == "" then $k else ($path + "." + $k) end))
      elif type == "array" then
        .[] | check($path)
      else
        empty
      end;
    [check("")] | unique | .[]
  ' "$file" 2>/dev/null || true)"
  if [ -n "$hit" ]; then
    fail "$label response exposes forbidden field key(s): $(echo "$hit" | tr '\n' ' ')"
  fi
  echo "OK: $label payload is customer-safe."
}

section "1. Required files exist"

REQUIRED=(
  "backend-api/app/api/routes/customer.py"
  "frontend-customer/src/api/customer.ts"
  "frontend-customer/src/pages/AlertsPage.tsx"
  "frontend-customer/src/pages/AlertDetailPage.tsx"
  "frontend-customer/src/pages/DashboardPage.tsx"
  "frontend-customer/src/App.tsx"
  "scripts/kb029_validate_customer_alert_detail_ui.sh"
  "docs/KB029_CUSTOMER_ALERT_DETAIL_UI.md"
)

for f in "${REQUIRED[@]}"; do
  [ -f "$f" ] || fail "$f is missing"
  echo "found: $f"
done

section "2. Protected paths must remain unmodified"

for p in frontend-admin/ postgres/init/ docker-compose.yml; do
  git diff --quiet -- "$p" || fail "$p has working-tree changes but KB-029 must not modify it"
  git diff --cached --quiet -- "$p" || fail "$p has staged changes but KB-029 must not modify it"
  echo "OK: $p unmodified"
done

if git status --porcelain -- .env 2>/dev/null | grep -q .; then
  fail ".env shows as changed/untracked"
fi
echo "OK: .env not changed/untracked."

section "3. Backend source: alert detail endpoint"

grep -q '@router.get("/alerts/{short_code}/{alert_id}")' backend-api/app/api/routes/customer.py \
  || fail "customer.py missing GET /alerts/{short_code}/{alert_id}"
grep -q 'def customer_alert_detail' backend-api/app/api/routes/customer.py \
  || fail "customer.py missing customer_alert_detail"
grep -q 'require_tenant_match' backend-api/app/api/routes/customer.py \
  || fail "customer.py missing require_tenant_match"
grep -q 'FROM security_alerts' backend-api/app/api/routes/customer.py \
  || fail "customer.py missing security_alerts query"
grep -q 'WHERE tenant_id = %s' backend-api/app/api/routes/customer.py \
  || fail "customer.py missing tenant_id filter"
grep -q 'customer_visible = true' backend-api/app/api/routes/customer.py \
  || fail "customer alert detail missing customer_visible = true"

DETAIL_BLOCK="$(awk '/def customer_alert_detail\(/,/^    return /' backend-api/app/api/routes/customer.py)"
SELECT_BLOCK="$(echo "$DETAIL_BLOCK" | awk '/SELECT/,/FROM security_alerts/')"
for forbidden in appliance_id asset_id external_alert_id raw_event ai_technical_summary \
  ai_likely_attack_type ai_business_impact ai_recommended_action ai_false_positive_score mitre_mapping \
  source_ip destination_ip source_user; do
  if echo "$SELECT_BLOCK" | grep -qE "(^|[[:space:]]+)${forbidden}[[:space:]]*(AS|,|$)"; then
    fail "customer_alert_detail SELECT must not expose $forbidden"
  fi
done
echo "OK: alert detail route present with tenant + visibility filters and safe SELECT."

section "4. Frontend: getCustomerAlertDetail + no /admin"

grep -q 'getCustomerAlertDetail' frontend-customer/src/api/customer.ts \
  || fail "customer.ts missing getCustomerAlertDetail"
grep -q '/customer/alerts/' frontend-customer/src/api/customer.ts \
  || fail "customer.ts missing /customer/alerts/ path"
grep -q 'getCustomerAlertDetail' frontend-customer/src/pages/AlertDetailPage.tsx \
  || fail "AlertDetailPage.tsx must call getCustomerAlertDetail"
grep -q 'alerts/:alertId' frontend-customer/src/App.tsx \
  || fail "App.tsx missing /alerts/:alertId route"
grep -q '/alerts/' frontend-customer/src/pages/AlertsPage.tsx \
  || fail "AlertsPage.tsx must link to detail route"
grep -q '/alerts/' frontend-customer/src/pages/DashboardPage.tsx \
  || fail "DashboardPage.tsx must link recent alerts to detail route"

if grep -REn '/admin' frontend-customer/src 2>/dev/null; then
  fail "frontend-customer/src must not contain /admin"
fi
echo "OK: frontend uses customer alert detail paths and has no /admin."

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

section "6. OpenAPI lists detail route"

OPENAPI="$(curl -fsS "$API_BASE/openapi.json" || fail "Could not fetch OpenAPI")"
echo "$OPENAPI" | jq -e '.paths | has("/customer/alerts/{short_code}/{alert_id}")' >/dev/null \
  || fail "OpenAPI missing /customer/alerts/{short_code}/{alert_id}"
echo "OK: OpenAPI registers alert detail route."

section "7. Unauthenticated access returns 401"

HTTP_CODE="$(curl -sS -o "$BODY_FILE" -w "%{http_code}" \
  "$API_BASE/customer/alerts/DEMO/00000000-0000-0000-0000-000000000001" || true)"
[ "$HTTP_CODE" = "401" ] || fail "Unauthenticated detail request expected 401, got $HTTP_CODE"
echo "OK: unauthenticated request returns 401."

section "8. Create temporary KB-029 fixtures"

cleanup_fixtures

DEMO_TENANT_ID="$(psql_scalar "SELECT id::text FROM tenants WHERE short_code = 'DEMO';")" \
  || fail "Could not resolve DEMO tenant id"
DEMO2_TENANT_ID="$(psql_scalar "SELECT id::text FROM tenants WHERE short_code = 'DEMO2';")" \
  || fail "Could not resolve DEMO2 tenant id"

FIXTURE_DEMO_VISIBLE_ID="$(psql_scalar "
WITH inserted AS (
  INSERT INTO security_alerts (
    tenant_id, source_tool, severity, alert_title, alert_description,
    ai_plain_summary, customer_visible, status, destination_host
  ) VALUES (
    '${DEMO_TENANT_ID}',
    'wazuh',
    'high',
    '${DEMO_VISIBLE_TITLE}',
    'Customer-safe description for KB029 visible alert detail.',
    'Plain summary for visible alert.',
    true,
    'false_positive',
    'demo-host-kb029'
  )
  RETURNING id
)
SELECT id::text FROM inserted;
")" || fail "Could not create DEMO visible alert"

FIXTURE_DEMO_HIDDEN_ID="$(psql_scalar "
WITH inserted AS (
  INSERT INTO security_alerts (
    tenant_id, source_tool, severity, alert_title, alert_description,
    customer_visible, status
  ) VALUES (
    '${DEMO_TENANT_ID}',
    'wazuh',
    'medium',
    '${DEMO_HIDDEN_TITLE}',
    'Internal-only alert — detail must return 404.',
    false,
    'new'
  )
  RETURNING id
)
SELECT id::text FROM inserted;
")" || fail "Could not create DEMO hidden alert"

FIXTURE_DEMO2_VISIBLE_ID="$(psql_scalar "
WITH inserted AS (
  INSERT INTO security_alerts (
    tenant_id, source_tool, severity, alert_title, alert_description,
    ai_plain_summary, customer_visible, status, destination_host
  ) VALUES (
    '${DEMO2_TENANT_ID}',
    'wazuh',
    'low',
    '${DEMO2_VISIBLE_TITLE}',
    'DEMO2 visible alert — DEMO viewer must not see detail.',
    'Plain summary for DEMO2 alert.',
    true,
    'new',
    'demo2-host-kb029'
  )
  RETURNING id
)
SELECT id::text FROM inserted;
")" || fail "Could not create DEMO2 visible alert"

echo "OK: temporary DEMO/DEMO2 alert fixtures created."

section "9. Login as customer.viewer@demo.local"

if [ -z "${CUSTOMER_VIEWER_PASSWORD:-}" ]; then
  echo
  read -rs -p "Enter the password for customer.viewer@demo.local: " CUSTOMER_VIEWER_PASSWORD
  echo
fi
[ -n "${CUSTOMER_VIEWER_PASSWORD:-}" ] || fail "Password was empty (set CUSTOMER_VIEWER_PASSWORD or type at prompt)"
CUSTOMER_VIEWER_TOKEN="$(login "customer.viewer@demo.local" "$CUSTOMER_VIEWER_PASSWORD" "customer_viewer")"
unset CUSTOMER_VIEWER_PASSWORD
echo "OK: logged in as customer_viewer."

section "10. DEMO customer can fetch DEMO visible alert detail (200)"

HTTP_CODE="$(curl -sS -o "$BODY_FILE" -w "%{http_code}" \
  -H "Authorization: Bearer $CUSTOMER_VIEWER_TOKEN" \
  "$API_BASE/customer/alerts/DEMO/${FIXTURE_DEMO_VISIBLE_ID}" || true)"
[ "$HTTP_CODE" = "200" ] || fail "DEMO visible detail expected 200, got $HTTP_CODE ($(cat "$BODY_FILE"))"

jq -e --arg id "$FIXTURE_DEMO_VISIBLE_ID" --arg t "$DEMO_VISIBLE_TITLE" '
  .tenant.short_code == "DEMO"
  and .alert.alert_id == $id
  and .alert.title == $t
  and .alert.status == "false_positive"
' "$BODY_FILE" >/dev/null \
  || fail "DEMO visible detail body missing expected fixture data"

assert_safe_detail_payload "DEMO visible alert detail" "$BODY_FILE"
echo "OK: DEMO visible alert detail 200 (status value false_positive allowed)."

section "11. DEMO customer gets 404 for DEMO hidden alert detail"

HTTP_CODE="$(curl -sS -o "$BODY_FILE" -w "%{http_code}" \
  -H "Authorization: Bearer $CUSTOMER_VIEWER_TOKEN" \
  "$API_BASE/customer/alerts/DEMO/${FIXTURE_DEMO_HIDDEN_ID}" || true)"
[ "$HTTP_CODE" = "404" ] || fail "DEMO hidden detail expected 404, got $HTTP_CODE"
echo "OK: hidden alert detail returns 404."

section "12. DEMO customer gets 404 for DEMO2 alert detail"

HTTP_CODE="$(curl -sS -o "$BODY_FILE" -w "%{http_code}" \
  -H "Authorization: Bearer $CUSTOMER_VIEWER_TOKEN" \
  "$API_BASE/customer/alerts/DEMO2/${FIXTURE_DEMO2_VISIBLE_ID}" || true)"
[ "$HTTP_CODE" = "404" ] || fail "DEMO2 detail as DEMO viewer expected 404, got $HTTP_CODE"

HTTP_CODE="$(curl -sS -o "$BODY_FILE" -w "%{http_code}" \
  -H "Authorization: Bearer $CUSTOMER_VIEWER_TOKEN" \
  "$API_BASE/customer/alerts/DEMO/${FIXTURE_DEMO2_VISIBLE_ID}" || true)"
[ "$HTTP_CODE" = "404" ] || fail "DEMO2 alert id under DEMO short_code expected 404, got $HTTP_CODE"
echo "OK: cross-tenant / hidden alert detail returns 404."

section "13. Frontend build"

if docker compose exec -T frontend-customer npm run build; then
  echo "OK: npm run build succeeded inside frontend-customer."
else
  fail "npm run build failed inside frontend-customer"
fi

section "14. Docs present"

[ -f "docs/KB029_CUSTOMER_ALERT_DETAIL_UI.md" ] || fail "docs/KB029_CUSTOMER_ALERT_DETAIL_UI.md missing"
grep -q 'GET /customer/alerts' docs/KB029_CUSTOMER_ALERT_DETAIL_UI.md \
  || fail "docs missing endpoint documentation"
grep -qi 'customer_visible' docs/KB029_CUSTOMER_ALERT_DETAIL_UI.md \
  || fail "docs missing customer_visible explanation"
echo "OK: completion docs present."

section "15. Cleanup fixtures verification"

cleanup_fixtures
REMAINING="$(psql_scalar "
  SELECT count(*) FROM security_alerts
  WHERE alert_title IN (
    '${DEMO_VISIBLE_TITLE}',
    '${DEMO_HIDDEN_TITLE}',
    '${DEMO2_VISIBLE_TITLE}'
  );
")" || fail "Could not verify fixture cleanup"
[ "$REMAINING" = "0" ] || fail "KB-029 fixtures not cleaned up (remaining=$REMAINING)"
echo "OK: temporary fixtures cleaned up."

section "16. Manual browser note"

echo "curl validates API auth/tenant isolation, visibility filters, and frontend build."
echo "Manually open $FRONTEND_BASE, sign in as customer.viewer@demo.local,"
echo "open Alerts or Dashboard, click an alert title, and confirm read-only detail."

section "17. Final verdict"

echo "======================================================================"
echo "KB-029 CUSTOMER ALERT DETAIL UI VALIDATION PASSED"
echo "======================================================================"
