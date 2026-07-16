#!/usr/bin/env bash
# KB-025: Validate Customer Incident Detail API + UI.
# Interactive: prompts for customer.viewer@demo.local password (never hardcoded).
# Optional: CUSTOMER_VIEWER_PASSWORD env for non-interactive runs.
# Creates temporary DEMO/DEMO2 fixtures, then cleans them up.
set -euo pipefail

PROJECT_DIR="/opt/mssp-control"
API_BASE="http://localhost:8000"
FRONTEND_BASE="http://localhost:3001"
BODY_FILE="/tmp/kb025-body.txt"
LOGIN_FILE="/tmp/kb025-login.json"

DEMO_INC_NUMBER="KB025-DEMO-INC"
DEMO2_INC_NUMBER="KB025-DEMO2-INC"
DEMO_ALERT_TITLE_VISIBLE="KB025 DEMO customer-visible related alert"
DEMO_ALERT_TITLE_HIDDEN="KB025 DEMO internal-only related alert"

FIXTURE_DEMO_INCIDENT_ID=""
FIXTURE_DEMO2_INCIDENT_ID=""
FIXTURE_VISIBLE_ALERT_ID=""
FIXTURE_HIDDEN_ALERT_ID=""

cd "$PROJECT_DIR"

echo "======================================================================"
echo "KB-025: Validate Customer Incident Detail UI"
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
      DELETE FROM incident_alerts
      WHERE incident_id IN (
        SELECT id FROM incidents
        WHERE incident_number IN ('${DEMO_INC_NUMBER}', '${DEMO2_INC_NUMBER}')
      );
      DELETE FROM incident_timeline
      WHERE incident_id IN (
        SELECT id FROM incidents
        WHERE incident_number IN ('${DEMO_INC_NUMBER}', '${DEMO2_INC_NUMBER}')
      );
      DELETE FROM incident_comments
      WHERE incident_id IN (
        SELECT id FROM incidents
        WHERE incident_number IN ('${DEMO_INC_NUMBER}', '${DEMO2_INC_NUMBER}')
      );
      DELETE FROM security_alerts
      WHERE alert_title IN (
        '${DEMO_ALERT_TITLE_VISIBLE}',
        '${DEMO_ALERT_TITLE_HIDDEN}'
      );
      DELETE FROM incidents
      WHERE incident_number IN ('${DEMO_INC_NUMBER}', '${DEMO2_INC_NUMBER}');
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
    (. | keys | sort) == ["incident","related_alerts","tenant","timeline"]
    and (.tenant | keys | sort | inside(["id","name","short_code"]))
    and (.tenant | has("id") and has("name") and has("short_code"))
    and (.incident | type == "object")
    and (.timeline | type == "array")
    and (.related_alerts | type == "array")
  ' "$file" >/dev/null \
    || fail "$label top-level / tenant shape invalid"

  jq -e '
    (.incident | keys)
    | all(.[]; . == "incident_number" or . == "title" or . == "severity" or . == "status"
        or . == "customer_visible_summary" or . == "business_impact"
        or . == "customer_action_required" or . == "resolution_summary"
        or . == "opened_at" or . == "resolved_at" or . == "closed_at")
  ' "$file" >/dev/null \
    || fail "$label incident object has unexpected keys"

  jq -e '
    (.timeline | map(keys) | flatten | unique)
    | all(.[]; . == "event_type" or . == "title" or . == "created_at")
  ' "$file" >/dev/null \
    || fail "$label timeline objects have unexpected keys"

  jq -e '
    (.related_alerts | map(keys) | flatten | unique)
    | all(.[]; . == "alert_id" or . == "title" or . == "severity" or . == "status"
        or . == "source" or . == "summary" or . == "description"
        or . == "detected_at" or . == "hostname")
  ' "$file" >/dev/null \
    || fail "$label related_alerts objects have unexpected keys"

  # Recursive forbidden keys. Allow "id" only under tenant.
  local hit
  hit="$(jq -r '
    def check($path):
      if type == "object" then
        (keys_unsorted[] as $k
          | ($k | ascii_downcase) as $kd
          | if ($kd == "internal_notes"
                or $kd == "assigned_to_user_id"
                or $kd == "primary_alert_id"
                or $kd == "incident_id"
                or $kd == "created_by_user_id"
                or $kd == "details"
                or $kd == "raw_event"
                or $kd == "raw_json"
                or $kd == "external_alert_id"
                or $kd == "ai_technical_summary"
                or $kd == "mitre_mapping"
                or $kd == "ai_false_positive_score"
                or $kd == "false_positive"
                or $kd == "source_ip"
                or $kd == "local_ip"
                or $kd == "ip_address"
                or $kd == "api_key"
                or $kd == "token"
                or $kd == "token_hash"
                or $kd == "password"
                or $kd == "password_hash"
                or $kd == "stack_trace"
                or $kd == "admin_notes"
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
  "frontend-customer/src/pages/IncidentsPage.tsx"
  "frontend-customer/src/pages/IncidentDetailPage.tsx"
  "frontend-customer/src/App.tsx"
  "scripts/kb025_validate_customer_incident_detail_ui.sh"
  "docs/KB025_CUSTOMER_INCIDENT_DETAIL_UI.md"
)

for f in "${REQUIRED[@]}"; do
  [ -f "$f" ] || fail "$f is missing"
  echo "found: $f"
done

section "2. Protected paths must remain unmodified"

for p in frontend-admin/ postgres/init/ docker-compose.yml; do
  git diff --quiet -- "$p" || fail "$p has working-tree changes but KB-025 must not modify it"
  git diff --cached --quiet -- "$p" || fail "$p has staged changes but KB-025 must not modify it"
  echo "OK: $p unmodified"
done

if git status --porcelain -- .env 2>/dev/null | grep -q .; then
  fail ".env shows as changed/untracked"
fi
echo "OK: .env not changed/untracked."

section "3. Backend source: detail endpoint + tenant match"

grep -q '@router.get("/incidents/{short_code}/{incident_number}")' backend-api/app/api/routes/customer.py \
  || fail "customer.py missing GET /incidents/{short_code}/{incident_number}"
grep -q 'def customer_incident_detail' backend-api/app/api/routes/customer.py \
  || fail "customer.py missing customer_incident_detail"
grep -q 'require_tenant_match' backend-api/app/api/routes/customer.py \
  || fail "customer.py missing require_tenant_match"
grep -q "visibility = 'customer'" backend-api/app/api/routes/customer.py \
  || fail "customer detail missing customer timeline visibility filter"
grep -q 'customer_visible = true' backend-api/app/api/routes/customer.py \
  || fail "customer detail missing customer_visible alert filter"
echo "OK: detail endpoint present with tenant + visibility filters."

section "4. Frontend: getCustomerIncidentDetail + no /admin"

grep -q 'getCustomerIncidentDetail' frontend-customer/src/api/customer.ts \
  || fail "customer.ts missing getCustomerIncidentDetail"
grep -q '/customer/incidents/' frontend-customer/src/api/customer.ts \
  || fail "customer.ts missing /customer/incidents/ path"
grep -q 'getCustomerIncidentDetail' frontend-customer/src/pages/IncidentDetailPage.tsx \
  || fail "IncidentDetailPage.tsx must call getCustomerIncidentDetail"
grep -q 'incidents/:incidentNumber' frontend-customer/src/App.tsx \
  || fail "App.tsx missing /incidents/:incidentNumber route"
grep -q '/incidents/' frontend-customer/src/pages/IncidentsPage.tsx \
  || fail "IncidentsPage.tsx must link to detail route"

if grep -REn '/admin' frontend-customer/src 2>/dev/null; then
  fail "frontend-customer/src must not contain /admin"
fi
echo "OK: frontend uses customer incident detail paths and has no /admin."

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
echo "$OPENAPI" | jq -e '.paths | has("/customer/incidents/{short_code}/{incident_number}")' >/dev/null \
  || fail "OpenAPI missing /customer/incidents/{short_code}/{incident_number}"
echo "OK: OpenAPI registers incident detail route."

section "7. Unauthenticated access returns 401"

HTTP_CODE="$(curl -sS -o "$BODY_FILE" -w "%{http_code}" \
  "$API_BASE/customer/incidents/DEMO/${DEMO_INC_NUMBER}" || true)"
[ "$HTTP_CODE" = "401" ] || fail "Unauthenticated detail request expected 401, got $HTTP_CODE"
echo "OK: unauthenticated request returns 401."

section "8. Create temporary KB-025 fixtures"

cleanup_fixtures

DEMO_TENANT_ID="$(psql_scalar "SELECT id::text FROM tenants WHERE short_code = 'DEMO';")" \
  || fail "Could not resolve DEMO tenant id"
DEMO2_TENANT_ID="$(psql_scalar "SELECT id::text FROM tenants WHERE short_code = 'DEMO2';")" \
  || fail "Could not resolve DEMO2 tenant id"

FIXTURE_DEMO_INCIDENT_ID="$(psql_scalar "
WITH inserted AS (
  INSERT INTO incidents (
    tenant_id, incident_number, title, severity, status,
    customer_visible_summary, business_impact, customer_action_required,
    resolution_summary, internal_notes
  ) VALUES (
    '${DEMO_TENANT_ID}',
    '${DEMO_INC_NUMBER}',
    'KB025 DEMO validation incident',
    'high',
    'open',
    'Customer-visible summary for KB025 validation.',
    'Possible business impact for DEMO.',
    'Please review with your IT contact.',
    NULL,
    'INTERNAL ONLY — must never appear in customer API'
  )
  RETURNING id
)
SELECT id FROM inserted;
")" || fail "Could not create DEMO validation incident"

FIXTURE_DEMO2_INCIDENT_ID="$(psql_scalar "
WITH inserted AS (
  INSERT INTO incidents (
    tenant_id, incident_number, title, severity, status,
    customer_visible_summary, internal_notes
  ) VALUES (
    '${DEMO2_TENANT_ID}',
    '${DEMO2_INC_NUMBER}',
    'KB025 DEMO2 validation incident',
    'medium',
    'open',
    'DEMO2 customer summary — DEMO viewer must not see this.',
    'INTERNAL DEMO2 notes'
  )
  RETURNING id
)
SELECT id FROM inserted;
")" || fail "Could not create DEMO2 validation incident"

# Customer-visible + internal timeline rows on DEMO incident
psql_scalar "
WITH inserted AS (
  INSERT INTO incident_timeline (incident_id, event_type, visibility, title, details)
  VALUES (
    '${FIXTURE_DEMO_INCIDENT_ID}',
    'created',
    'customer',
    'KB025 customer-visible timeline event',
    'DETAILS must not be returned to customer API'
  )
  RETURNING id
)
SELECT id FROM inserted;
" >/dev/null || fail "Could not create customer-visible timeline row"

psql_scalar "
WITH inserted AS (
  INSERT INTO incident_timeline (incident_id, event_type, visibility, title, details)
  VALUES (
    '${FIXTURE_DEMO_INCIDENT_ID}',
    'assigned',
    'internal',
    'KB025 internal timeline event — must be hidden',
    'Internal SOC assignment details'
  )
  RETURNING id
)
SELECT id FROM inserted;
" >/dev/null || fail "Could not create internal timeline row"

FIXTURE_VISIBLE_ALERT_ID="$(psql_scalar "
WITH inserted AS (
  INSERT INTO security_alerts (
    tenant_id, source_tool, severity, alert_title, alert_description,
    ai_plain_summary, customer_visible, status, destination_host
  ) VALUES (
    '${DEMO_TENANT_ID}',
    'wazuh',
    'high',
    '${DEMO_ALERT_TITLE_VISIBLE}',
    'Customer-safe description for related alert.',
    'Plain summary for related alert.',
    true,
    'new',
    'demo-host-01'
  )
  RETURNING id
)
SELECT id FROM inserted;
")" || fail "Could not create customer-visible related alert"

FIXTURE_HIDDEN_ALERT_ID="$(psql_scalar "
WITH inserted AS (
  INSERT INTO security_alerts (
    tenant_id, source_tool, severity, alert_title, alert_description,
    customer_visible, status
  ) VALUES (
    '${DEMO_TENANT_ID}',
    'wazuh',
    'medium',
    '${DEMO_ALERT_TITLE_HIDDEN}',
    'Internal-only related alert description.',
    false,
    'new'
  )
  RETURNING id
)
SELECT id FROM inserted;
")" || fail "Could not create internal related alert"

psql_scalar "
WITH inserted AS (
  INSERT INTO incident_alerts (incident_id, alert_id)
  VALUES
    ('${FIXTURE_DEMO_INCIDENT_ID}', '${FIXTURE_VISIBLE_ALERT_ID}'),
    ('${FIXTURE_DEMO_INCIDENT_ID}', '${FIXTURE_HIDDEN_ALERT_ID}')
  RETURNING incident_id
)
SELECT incident_id FROM inserted LIMIT 1;
" >/dev/null || fail "Could not link related alerts to DEMO incident"

echo "OK: temporary DEMO/DEMO2 fixtures created."

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

section "10. DEMO customer can fetch DEMO incident detail (200)"

HTTP_CODE="$(curl -sS -o "$BODY_FILE" -w "%{http_code}" \
  -H "Authorization: Bearer $CUSTOMER_VIEWER_TOKEN" \
  "$API_BASE/customer/incidents/DEMO/${DEMO_INC_NUMBER}" || true)"
[ "$HTTP_CODE" = "200" ] || fail "DEMO detail expected 200, got $HTTP_CODE ($(cat "$BODY_FILE"))"

jq -e --arg n "$DEMO_INC_NUMBER" '
  .tenant.short_code == "DEMO"
  and .incident.incident_number == $n
  and (.timeline | length) == 1
  and .timeline[0].title == "KB025 customer-visible timeline event"
  and (.related_alerts | length) == 1
  and .related_alerts[0].title == "KB025 DEMO customer-visible related alert"
' "$BODY_FILE" >/dev/null \
  || fail "DEMO detail body missing expected fixture filtering (timeline/related_alerts)"

# Prove internal content is not present as values either
if grep -qi 'INTERNAL ONLY' "$BODY_FILE"; then
  fail "DEMO detail leaked internal_notes content"
fi
if grep -qi 'KB025 internal timeline event' "$BODY_FILE"; then
  fail "DEMO detail leaked internal timeline title"
fi
if grep -qi 'KB025 DEMO internal-only related alert' "$BODY_FILE"; then
  fail "DEMO detail leaked non-customer-visible related alert"
fi
if grep -qi 'DETAILS must not be returned' "$BODY_FILE"; then
  fail "DEMO detail leaked timeline details text"
fi

assert_safe_detail_payload "DEMO incident detail" "$BODY_FILE"
echo "OK: DEMO detail 200 with customer-visible timeline/alerts only."

section "11. DEMO customer cannot fetch DEMO2 incident (404)"

HTTP_CODE="$(curl -sS -o "$BODY_FILE" -w "%{http_code}" \
  -H "Authorization: Bearer $CUSTOMER_VIEWER_TOKEN" \
  "$API_BASE/customer/incidents/DEMO2/${DEMO2_INC_NUMBER}" || true)"
[ "$HTTP_CODE" = "404" ] || fail "DEMO2 detail as DEMO viewer expected 404, got $HTTP_CODE"

HTTP_CODE="$(curl -sS -o "$BODY_FILE" -w "%{http_code}" \
  -H "Authorization: Bearer $CUSTOMER_VIEWER_TOKEN" \
  "$API_BASE/customer/incidents/DEMO/${DEMO2_INC_NUMBER}" || true)"
[ "$HTTP_CODE" = "404" ] || fail "Wrong-tenant incident_number under DEMO short_code expected 404, got $HTTP_CODE"
echo "OK: cross-tenant incident detail returns 404."

section "12. Frontend build"

if docker compose exec -T frontend-customer npm run build; then
  echo "OK: npm run build succeeded inside frontend-customer."
else
  fail "npm run build failed inside frontend-customer"
fi

section "13. Docs present"

[ -f "docs/KB025_CUSTOMER_INCIDENT_DETAIL_UI.md" ] || fail "docs/KB025_CUSTOMER_INCIDENT_DETAIL_UI.md missing"
grep -q 'GET /customer/incidents' docs/KB025_CUSTOMER_INCIDENT_DETAIL_UI.md \
  || fail "docs missing endpoint documentation"
grep -qi 'comment' docs/KB025_CUSTOMER_INCIDENT_DETAIL_UI.md \
  || fail "docs should mention comments deferred/omitted"
echo "OK: completion docs present."

section "14. Cleanup fixtures verification"

cleanup_fixtures
REMAINING="$(psql_scalar "
  SELECT count(*) FROM incidents
  WHERE incident_number IN ('${DEMO_INC_NUMBER}', '${DEMO2_INC_NUMBER}');
")" || fail "Could not verify fixture cleanup"
[ "$REMAINING" = "0" ] || fail "KB-025 fixtures not cleaned up (incidents remaining=$REMAINING)"
echo "OK: temporary fixtures cleaned up."

section "15. Manual browser note"

echo "curl validates API auth/tenant isolation, visibility filters, and frontend build."
echo "Manually open $FRONTEND_BASE, sign in as customer.viewer@demo.local,"
echo "open Incidents, click an incident number/title, and confirm read-only detail."

section "16. Final verdict"

echo "======================================================================"
echo "KB-025 CUSTOMER INCIDENT DETAIL UI VALIDATION PASSED"
echo "======================================================================"
