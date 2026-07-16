#!/usr/bin/env bash
# KB-031: Validate Customer Report Detail API + UI.
# Interactive: prompts for customer.viewer@demo.local password (never hardcoded).
# Optional: CUSTOMER_VIEWER_PASSWORD env for non-interactive runs.
# Creates temporary DEMO/DEMO2 monthly_reports fixtures, then cleans them up.
set -euo pipefail

PROJECT_DIR="/opt/mssp-control"
API_BASE="http://localhost:8000"
FRONTEND_BASE="http://localhost:3001"
BODY_FILE="/tmp/kb031-body.txt"
LOGIN_FILE="/tmp/kb031-login.json"

# Far-future months to avoid UNIQUE (tenant_id, report_month) clashes with demo data.
DEMO_PUBLISHED_MONTH="2091-01-01"
DEMO_DRAFT_MONTH="2091-02-01"
DEMO2_PUBLISHED_MONTH="2091-01-01"

DEMO_PUBLISHED_SUMMARY="KB031 DEMO published report summary"
DEMO_DRAFT_SUMMARY="KB031 DEMO draft report summary — must return 404"
DEMO2_PUBLISHED_SUMMARY="KB031 DEMO2 published report summary"

FIXTURE_DEMO_PUBLISHED_ID=""
FIXTURE_DEMO_DRAFT_ID=""
FIXTURE_DEMO2_PUBLISHED_ID=""

cd "$PROJECT_DIR"

echo "======================================================================"
echo "KB-031: Validate Customer Report Detail UI"
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
      DELETE FROM monthly_reports
      WHERE executive_summary IN (
        '${DEMO_PUBLISHED_SUMMARY}',
        '${DEMO_DRAFT_SUMMARY}',
        '${DEMO2_PUBLISHED_SUMMARY}'
      )
      OR (
        report_month IN (
          DATE '${DEMO_PUBLISHED_MONTH}',
          DATE '${DEMO_DRAFT_MONTH}',
          DATE '${DEMO2_PUBLISHED_MONTH}'
        )
        AND executive_summary LIKE 'KB031 %'
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
    (. | keys | sort) == ["report","tenant"]
    and (.tenant | has("id") and has("name") and has("short_code"))
    and (.report | type == "object")
  ' "$file" >/dev/null \
    || fail "$label top-level / tenant shape invalid"

  jq -e '
    (.report | keys)
    | all(.[]; . == "report_id" or . == "report_month" or . == "status"
        or . == "title" or . == "summary" or . == "created_at" or . == "published_at")
  ' "$file" >/dev/null \
    || fail "$label report object has unexpected keys"

  local hit
  hit="$(jq -r '
    def check($path):
      if type == "object" then
        (keys_unsorted[] as $k
          | ($k | ascii_downcase) as $kd
          | if ($kd == "tenant_id"
                or $kd == "metrics"
                or $kd == "report_file_path"
                or $kd == "raw_json"
                or $kd == "raw_event"
                or $kd == "details"
                or $kd == "internal_notes"
                or $kd == "admin_notes"
                or $kd == "api_key"
                or $kd == "token"
                or $kd == "token_hash"
                or $kd == "password"
                or $kd == "password_hash"
                or $kd == "stack_trace"
                or $kd == "updated_at"
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
  "frontend-customer/src/pages/ReportsPage.tsx"
  "frontend-customer/src/pages/ReportDetailPage.tsx"
  "frontend-customer/src/pages/DashboardPage.tsx"
  "frontend-customer/src/App.tsx"
  "scripts/kb031_validate_customer_report_detail_ui.sh"
  "docs/KB031_CUSTOMER_REPORT_DETAIL_UI.md"
)

for f in "${REQUIRED[@]}"; do
  [ -f "$f" ] || fail "$f is missing"
  echo "found: $f"
done

section "2. Protected paths must remain unmodified"

for p in frontend-admin/ postgres/init/ docker-compose.yml; do
  git diff --quiet -- "$p" || fail "$p has working-tree changes but KB-031 must not modify it"
  git diff --cached --quiet -- "$p" || fail "$p has staged changes but KB-031 must not modify it"
  echo "OK: $p unmodified"
done

if git status --porcelain -- .env 2>/dev/null | grep -q .; then
  fail ".env shows as changed/untracked"
fi
echo "OK: .env not changed/untracked."

section "3. Backend source: report detail endpoint"

grep -q '@router.get("/reports/{short_code}/{report_id}")' backend-api/app/api/routes/customer.py \
  || fail "customer.py missing GET /reports/{short_code}/{report_id}"
grep -q 'def customer_report_detail' backend-api/app/api/routes/customer.py \
  || fail "customer.py missing customer_report_detail"
grep -q 'require_tenant_match' backend-api/app/api/routes/customer.py \
  || fail "customer.py missing require_tenant_match"
grep -q 'FROM monthly_reports' backend-api/app/api/routes/customer.py \
  || fail "customer.py missing monthly_reports query"
grep -q "status IN ('published', 'archived')" backend-api/app/api/routes/customer.py \
  || fail "customer report detail missing published/archived status filter"

DETAIL_BLOCK="$(awk '/def customer_report_detail\(/,/^    return /' backend-api/app/api/routes/customer.py)"
SELECT_BLOCK="$(echo "$DETAIL_BLOCK" | awk '/SELECT/,/FROM monthly_reports/')"
for forbidden in metrics report_file_path updated_at tenant_id; do
  if echo "$SELECT_BLOCK" | grep -qE "(^|[[:space:]]+)${forbidden}([[:space:]]|,|$|AS)"; then
    fail "customer_report_detail SELECT must not expose $forbidden"
  fi
done
echo "OK: report detail route present with tenant + id + status filters and safe SELECT."

section "4. Frontend: getCustomerReportDetail + no /admin"

grep -q 'getCustomerReportDetail' frontend-customer/src/api/customer.ts \
  || fail "customer.ts missing getCustomerReportDetail"
grep -q '/customer/reports/' frontend-customer/src/api/customer.ts \
  || fail "customer.ts missing /customer/reports/ path"
grep -q 'getCustomerReportDetail' frontend-customer/src/pages/ReportDetailPage.tsx \
  || fail "ReportDetailPage.tsx must call getCustomerReportDetail"
grep -q 'reports/:reportId' frontend-customer/src/App.tsx \
  || fail "App.tsx missing /reports/:reportId route"
grep -q '/reports/' frontend-customer/src/pages/ReportsPage.tsx \
  || fail "ReportsPage.tsx must link report title to detail route"
grep -q '/reports/' frontend-customer/src/pages/DashboardPage.tsx \
  || fail "DashboardPage.tsx must link latest report to detail route"

if grep -REn '/admin' frontend-customer/src 2>/dev/null; then
  fail "frontend-customer/src must not contain /admin"
fi
echo "OK: frontend uses customer report detail paths and has no /admin."

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
echo "$OPENAPI" | jq -e '.paths | has("/customer/reports/{short_code}/{report_id}")' >/dev/null \
  || fail "OpenAPI missing /customer/reports/{short_code}/{report_id}"
echo "OK: OpenAPI registers report detail route."

section "7. Unauthenticated access returns 401"

HTTP_CODE="$(curl -sS -o "$BODY_FILE" -w "%{http_code}" \
  "$API_BASE/customer/reports/DEMO/00000000-0000-0000-0000-000000000001" || true)"
[ "$HTTP_CODE" = "401" ] || fail "Unauthenticated detail request expected 401, got $HTTP_CODE"
echo "OK: unauthenticated request returns 401."

section "8. Create temporary KB-031 fixtures"

cleanup_fixtures

DEMO_TENANT_ID="$(psql_scalar "SELECT id::text FROM tenants WHERE short_code = 'DEMO';")" \
  || fail "Could not resolve DEMO tenant id"
DEMO2_TENANT_ID="$(psql_scalar "SELECT id::text FROM tenants WHERE short_code = 'DEMO2';")" \
  || fail "Could not resolve DEMO2 tenant id"

FIXTURE_DEMO_PUBLISHED_ID="$(psql_scalar "
WITH inserted AS (
  INSERT INTO monthly_reports (
    tenant_id, report_month, status, executive_summary, published_at
  ) VALUES (
    '${DEMO_TENANT_ID}',
    DATE '${DEMO_PUBLISHED_MONTH}',
    'published',
    '${DEMO_PUBLISHED_SUMMARY}',
    now()
  )
  RETURNING id
)
SELECT id::text FROM inserted;
")" || fail "Could not create DEMO published report"

FIXTURE_DEMO_DRAFT_ID="$(psql_scalar "
WITH inserted AS (
  INSERT INTO monthly_reports (
    tenant_id, report_month, status, executive_summary
  ) VALUES (
    '${DEMO_TENANT_ID}',
    DATE '${DEMO_DRAFT_MONTH}',
    'draft',
    '${DEMO_DRAFT_SUMMARY}'
  )
  RETURNING id
)
SELECT id::text FROM inserted;
")" || fail "Could not create DEMO draft report"

FIXTURE_DEMO2_PUBLISHED_ID="$(psql_scalar "
WITH inserted AS (
  INSERT INTO monthly_reports (
    tenant_id, report_month, status, executive_summary, published_at
  ) VALUES (
    '${DEMO2_TENANT_ID}',
    DATE '${DEMO2_PUBLISHED_MONTH}',
    'published',
    '${DEMO2_PUBLISHED_SUMMARY}',
    now()
  )
  RETURNING id
)
SELECT id::text FROM inserted;
")" || fail "Could not create DEMO2 published report"

echo "OK: temporary DEMO/DEMO2 report fixtures created."

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

section "10. DEMO customer can fetch DEMO published report detail (200)"

HTTP_CODE="$(curl -sS -o "$BODY_FILE" -w "%{http_code}" \
  -H "Authorization: Bearer $CUSTOMER_VIEWER_TOKEN" \
  "$API_BASE/customer/reports/DEMO/${FIXTURE_DEMO_PUBLISHED_ID}" || true)"
[ "$HTTP_CODE" = "200" ] || fail "DEMO published detail expected 200, got $HTTP_CODE ($(cat "$BODY_FILE"))"

jq -e --arg id "$FIXTURE_DEMO_PUBLISHED_ID" --arg s "$DEMO_PUBLISHED_SUMMARY" '
  .tenant.short_code == "DEMO"
  and .report.report_id == $id
  and .report.status == "published"
  and .report.summary == $s
  and (.report.title | type == "string")
' "$BODY_FILE" >/dev/null \
  || fail "DEMO published detail body missing expected fixture data"

assert_safe_detail_payload "DEMO published report detail" "$BODY_FILE"
echo "OK: DEMO published report detail 200."

section "11. DEMO customer gets 404 for DEMO draft report detail"

HTTP_CODE="$(curl -sS -o "$BODY_FILE" -w "%{http_code}" \
  -H "Authorization: Bearer $CUSTOMER_VIEWER_TOKEN" \
  "$API_BASE/customer/reports/DEMO/${FIXTURE_DEMO_DRAFT_ID}" || true)"
[ "$HTTP_CODE" = "404" ] || fail "DEMO draft detail expected 404, got $HTTP_CODE"
echo "OK: draft report detail returns 404."

section "12. DEMO customer gets 404 for DEMO2 report detail"

HTTP_CODE="$(curl -sS -o "$BODY_FILE" -w "%{http_code}" \
  -H "Authorization: Bearer $CUSTOMER_VIEWER_TOKEN" \
  "$API_BASE/customer/reports/DEMO2/${FIXTURE_DEMO2_PUBLISHED_ID}" || true)"
[ "$HTTP_CODE" = "404" ] || fail "DEMO2 detail as DEMO viewer expected 404, got $HTTP_CODE"

HTTP_CODE="$(curl -sS -o "$BODY_FILE" -w "%{http_code}" \
  -H "Authorization: Bearer $CUSTOMER_VIEWER_TOKEN" \
  "$API_BASE/customer/reports/DEMO/${FIXTURE_DEMO2_PUBLISHED_ID}" || true)"
[ "$HTTP_CODE" = "404" ] || fail "DEMO2 report id under DEMO short_code expected 404, got $HTTP_CODE"
echo "OK: cross-tenant report detail returns 404."

section "13. DEMO customer gets 404 for nonexistent report UUID"

HTTP_CODE="$(curl -sS -o "$BODY_FILE" -w "%{http_code}" \
  -H "Authorization: Bearer $CUSTOMER_VIEWER_TOKEN" \
  "$API_BASE/customer/reports/DEMO/00000000-0000-0000-0000-000000000099" || true)"
[ "$HTTP_CODE" = "404" ] || fail "Nonexistent report detail expected 404, got $HTTP_CODE"
echo "OK: nonexistent report detail returns 404."

section "14. Frontend build"

if docker compose exec -T frontend-customer npm run build; then
  echo "OK: npm run build succeeded inside frontend-customer."
else
  fail "npm run build failed inside frontend-customer"
fi

section "15. Docs present"

[ -f "docs/KB031_CUSTOMER_REPORT_DETAIL_UI.md" ] || fail "docs/KB031_CUSTOMER_REPORT_DETAIL_UI.md missing"
grep -q 'GET /customer/reports' docs/KB031_CUSTOMER_REPORT_DETAIL_UI.md \
  || fail "docs missing endpoint documentation"
grep -qi 'published' docs/KB031_CUSTOMER_REPORT_DETAIL_UI.md \
  || fail "docs missing published/archived visibility explanation"
echo "OK: completion docs present."

section "16. Cleanup fixtures verification"

cleanup_fixtures
REMAINING="$(psql_scalar "
  SELECT count(*) FROM monthly_reports
  WHERE executive_summary IN (
    '${DEMO_PUBLISHED_SUMMARY}',
    '${DEMO_DRAFT_SUMMARY}',
    '${DEMO2_PUBLISHED_SUMMARY}'
  );
")" || fail "Could not verify fixture cleanup"
[ "$REMAINING" = "0" ] || fail "KB-031 fixtures not cleaned up (remaining=$REMAINING)"
echo "OK: temporary fixtures cleaned up."

section "17. Manual browser note"

echo "curl validates API auth/tenant isolation, draft filtering, and frontend build."
echo "Manually open $FRONTEND_BASE, sign in as customer.viewer@demo.local,"
echo "open Reports or Dashboard latest report, click through, and confirm read-only detail."

section "18. Final verdict"

echo "======================================================================"
echo "KB-031 CUSTOMER REPORT DETAIL UI VALIDATION PASSED"
echo "======================================================================"
