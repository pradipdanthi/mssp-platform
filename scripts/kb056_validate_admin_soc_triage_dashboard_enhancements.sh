#!/usr/bin/env bash
# KB-056: Validate Admin/SOC triage API and frontend enhancements.
# Set PLATFORM_ADMIN_PASSWORD for non-interactive use; otherwise prompts securely.
set -euo pipefail

PROJECT_DIR="/opt/mssp-control"
API_BASE="http://localhost:8000"
FRONTEND_BASE="http://localhost:3000"
BODY_FILE="/tmp/kb056-body.json"
LOGIN_FILE="/tmp/kb056-login.json"
ALERT_TITLE="KB056 validation alert"
INCIDENT_NUMBER="KB056-VALIDATION-INCIDENT"
ALERT_ID=""
INCIDENT_ID=""

cd "$PROJECT_DIR"

fail() {
  echo
  echo "VALIDATION FAILED: $1" >&2
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
    -X -q -t -A -v ON_ERROR_STOP=1 \
    -U "${POSTGRES_USER:-mssp_admin}" -d "${POSTGRES_DB:-mssp_control}" \
    -c "$sql" 2>/dev/null)" || return 1
  raw="$(printf '%s\n' "$raw" | sed 's/\r$//' | grep -v '^[[:space:]]*$' || true)"
  line_count="$(printf '%s\n' "$raw" | grep -c '.' || true)"
  [ "$line_count" = "1" ] || return 1
  printf '%s' "$raw"
}

cleanup() {
  if docker compose ps --status running --services 2>/dev/null | grep -qx postgres; then
    docker compose exec -T postgres psql \
      -X -q -v ON_ERROR_STOP=1 \
      -U "${POSTGRES_USER:-mssp_admin}" -d "${POSTGRES_DB:-mssp_control}" \
      -c "
        DELETE FROM incidents WHERE incident_number = '${INCIDENT_NUMBER}';
        DELETE FROM security_alerts WHERE alert_title = '${ALERT_TITLE}';
      " >/dev/null 2>&1 || true
  fi
  rm -f "$BODY_FILE" "$LOGIN_FILE"
}
trap cleanup EXIT

api_call() {
  local method="$1"
  local path="$2"
  local token="${3:-}"
  local body="${4:-}"
  local args=(-sS -o "$BODY_FILE" -w "%{http_code}" -X "$method")
  [ -z "$token" ] || args+=(-H "Authorization: Bearer $token")
  if [ -n "$body" ]; then
    args+=(-H "Content-Type: application/json" -d "$body")
  fi
  curl "${args[@]}" "$API_BASE$path" || true
}

echo "======================================================================"
echo "KB-056: Validate Admin/SOC Triage Dashboard Enhancements"
echo "Target: $PROJECT_DIR"
echo "======================================================================"

section "1. Required files and source wiring"
REQUIRED=(
  backend-api/app/api/routes/alert_incident_triage.py
  backend-api/app/schemas/triage.py
  backend-api/app/api/routes/admin.py
  backend-api/app/main.py
  frontend-admin/src/api/admin.ts
  frontend-admin/src/App.tsx
  frontend-admin/src/pages/AlertsPage.tsx
  frontend-admin/src/pages/IncidentsPage.tsx
  frontend-admin/src/pages/AlertDetailPage.tsx
  frontend-admin/src/pages/IncidentDetailPage.tsx
  scripts/kb056_validate_admin_soc_triage_dashboard_enhancements.sh
  docs/KB056_ADMIN_SOC_TRIAGE_DASHBOARD_ENHANCEMENTS.md
)
for file in "${REQUIRED[@]}"; do
  [ -f "$file" ] || fail "$file is missing"
  echo "found: $file"
done

grep -q 'include_router(alert_incident_triage_router)' backend-api/app/main.py \
  || fail "main.py does not register alert_incident_triage_router"
grep -q '@router.get("/alerts/{alert_id}")' backend-api/app/api/routes/alert_incident_triage.py \
  || fail "alert detail route is missing"
grep -q '@router.patch("/alerts/{alert_id}")' backend-api/app/api/routes/alert_incident_triage.py \
  || fail "alert PATCH route is missing"
grep -q '@router.get("/incidents/{incident_id}")' backend-api/app/api/routes/alert_incident_triage.py \
  || fail "incident detail route is missing"
grep -q '@router.patch("/incidents/{incident_id}")' backend-api/app/api/routes/alert_incident_triage.py \
  || fail "incident PATCH route is missing"
grep -q '@router.post("/incidents/{incident_id}/comments"' backend-api/app/api/routes/alert_incident_triage.py \
  || fail "incident comment route is missing"
grep -q 'alerts/:alertId' frontend-admin/src/App.tsx \
  || fail "admin alert detail route is missing"
grep -q 'incidents/:incidentId' frontend-admin/src/App.tsx \
  || fail "admin incident detail route is missing"
echo "OK: API and UI source wiring is present."

section "2. Protected paths and syntax"
for path in .env docker-compose.yml postgres/init frontend-customer; do
  if [ "$path" = ".env" ]; then
    git status --porcelain -- "$path" 2>/dev/null | grep -q . \
      && fail ".env shows as changed or untracked"
  else
    git diff --quiet -- "$path" || fail "$path has working-tree changes"
    git diff --cached --quiet -- "$path" || fail "$path has staged changes"
  fi
done
python3 -m py_compile \
  backend-api/app/api/routes/alert_incident_triage.py \
  backend-api/app/api/routes/admin.py \
  backend-api/app/schemas/triage.py \
  backend-api/app/main.py
bash -n scripts/kb056_validate_admin_soc_triage_dashboard_enhancements.sh
echo "OK: protected paths unchanged; Python and Bash syntax passed."

section "3. Docker Compose services and health"
RUNNING_SERVICES="$(docker compose ps --status running --services)" \
  || fail "docker compose ps failed"
for service in postgres redis backend-api frontend-admin frontend-customer; do
  printf '%s\n' "$RUNNING_SERVICES" | grep -qx "$service" \
    || fail "Docker Compose service is not running: $service"
done
curl -fsS "$API_BASE/health" -o "$BODY_FILE" \
  || fail "GET /health failed"
jq -e '.api == "ok" and .database == "ok" and .redis == "ok"' "$BODY_FILE" >/dev/null \
  || fail "/health did not report API, database, and Redis as ok"
echo "OK: required services are running and backend health is healthy."

section "4. OpenAPI route registration"
curl -fsS "$API_BASE/openapi.json" -o "$BODY_FILE" \
  || fail "Could not fetch OpenAPI"
jq -e '
  .paths
  | has("/admin/alerts/{alert_id}")
    and has("/admin/incidents/{incident_id}")
    and has("/admin/incidents/{incident_id}/comments")
' "$BODY_FILE" >/dev/null \
  || fail "Live backend does not include KB-056 routes; rebuild/redeploy backend-api, then rerun"
echo "OK: live OpenAPI includes all KB-056 detail and comment paths."

section "5. Platform administrator login"
if [ "${SKIP_LIVE:-}" = "1" ]; then
  echo "OK: SKIP_LIVE=1 — skipping interactive login and live triage API checks."
  echo "======================================================================"
  echo "KB-056 ADMIN SOC TRIAGE DASHBOARD ENHANCEMENTS VALIDATION PASSED (SOURCE+OPENAPI)"
  echo "======================================================================"
  exit 0
fi
PLATFORM_ADMIN_EMAIL="${PLATFORM_ADMIN_EMAIL:-$(psql_scalar "
  SELECT email
  FROM platform_users
  WHERE role = 'platform_admin' AND status = 'active'
  ORDER BY created_at
  LIMIT 1;
")}" || fail "Could not resolve an active platform administrator"
[ -n "$PLATFORM_ADMIN_EMAIL" ] || fail "No active platform administrator exists"
if [ -z "${PLATFORM_ADMIN_PASSWORD:-}" ]; then
  if [ ! -t 0 ]; then
    fail "PLATFORM_ADMIN_PASSWORD is required for non-interactive live validation (or set SKIP_LIVE=1)"
  fi
  read -rs -p "Enter the password for ${PLATFORM_ADMIN_EMAIL}: " PLATFORM_ADMIN_PASSWORD
  echo
fi
[ -n "${PLATFORM_ADMIN_PASSWORD:-}" ] || fail "PLATFORM_ADMIN_PASSWORD is empty"
LOGIN_BODY="$(jq -n \
  --arg email "$PLATFORM_ADMIN_EMAIL" \
  --arg password "$PLATFORM_ADMIN_PASSWORD" \
  '{email:$email,password:$password}')"
HTTP_CODE="$(curl -sS -o "$LOGIN_FILE" -w "%{http_code}" \
  -X POST "$API_BASE/auth/login" \
  -H "Content-Type: application/json" \
  -d "$LOGIN_BODY" || true)"
unset PLATFORM_ADMIN_PASSWORD LOGIN_BODY
[ "$HTTP_CODE" = "200" ] || fail "Platform administrator login failed with HTTP $HTTP_CODE"
ADMIN_TOKEN="$(jq -r '.access_token // empty' "$LOGIN_FILE")"
ADMIN_USER_ID="$(jq -r '.user.id // empty' "$LOGIN_FILE")"
[ -n "$ADMIN_TOKEN" ] || fail "Login response did not include an access token"
jq -e '.user.role == "platform_admin"' "$LOGIN_FILE" >/dev/null \
  || fail "Login account is not platform_admin"
echo "OK: authenticated as platform_admin (credentials not printed)."

section "6. Authentication boundary and temporary fixtures"
HTTP_CODE="$(api_call GET "/admin/alerts/00000000-0000-0000-0000-000000000001")"
[ "$HTTP_CODE" = "401" ] || fail "Unauthenticated alert detail expected 401, got $HTTP_CODE"
cleanup
TENANT_ID="$(psql_scalar "SELECT id::text FROM tenants ORDER BY created_at LIMIT 1;")" \
  || fail "Could not resolve a tenant for fixtures"
ALERT_ID="$(psql_scalar "
  WITH inserted AS (
    INSERT INTO security_alerts (
      tenant_id, source_tool, external_alert_id, severity, alert_title,
      alert_description, raw_event, ai_technical_summary, customer_visible, status
    ) VALUES (
      '${TENANT_ID}', 'kb056-validator', 'KB056-ALERT', 'critical', '${ALERT_TITLE}',
      'Temporary KB-056 validation alert', '{\"validator\":true}'::jsonb,
      'Internal KB-056 technical summary', false, 'new'
    )
    RETURNING id
  )
  SELECT id::text FROM inserted;
")" || fail "Could not create alert fixture"
INCIDENT_ID="$(psql_scalar "
  WITH inserted AS (
    INSERT INTO incidents (
      tenant_id, primary_alert_id, incident_number, title, severity, status,
      customer_visible_summary, internal_notes
    ) VALUES (
      '${TENANT_ID}', '${ALERT_ID}', '${INCIDENT_NUMBER}',
      'KB056 validation incident', 'high', 'open',
      'Initial customer summary', 'Internal KB-056 validation note'
    )
    RETURNING id
  )
  SELECT id::text FROM inserted;
")" || fail "Could not create incident fixture"
docker compose exec -T postgres psql \
  -X -q -v ON_ERROR_STOP=1 \
  -U "${POSTGRES_USER:-mssp_admin}" -d "${POSTGRES_DB:-mssp_control}" \
  -c "
    INSERT INTO incident_timeline (
      incident_id, event_type, visibility, title, details, created_by_user_id
    ) VALUES (
      '${INCIDENT_ID}', 'created', 'internal',
      'KB056 fixture created', 'Temporary timeline entry', '${ADMIN_USER_ID}'
    );
  " >/dev/null
echo "OK: unauthenticated access is blocked and fixtures were created."

section "7. Alert list filters, detail, and PATCH"
HTTP_CODE="$(api_call GET "/admin/alerts?status=new&severity=critical&tenant_id=${TENANT_ID}" "$ADMIN_TOKEN")"
[ "$HTTP_CODE" = "200" ] || fail "Filtered alerts list expected 200, got $HTTP_CODE"
jq -e --arg id "$ALERT_ID" '
  (.alerts | any(.id == $id))
  and (.alerts | all(.status == "new" and .severity == "critical"))
' "$BODY_FILE" >/dev/null || fail "Alert list filters did not constrain results correctly"
HTTP_CODE="$(api_call GET "/admin/alerts/${ALERT_ID}" "$ADMIN_TOKEN")"
[ "$HTTP_CODE" = "200" ] || fail "Alert detail expected 200, got $HTTP_CODE"
jq -e --arg id "$ALERT_ID" '
  .alert.id == $id
  and .alert.raw_event.validator == true
  and .alert.ai_technical_summary == "Internal KB-056 technical summary"
' "$BODY_FILE" >/dev/null || fail "Alert detail is missing internal fixture fields"
HTTP_CODE="$(api_call PATCH "/admin/alerts/${ALERT_ID}" "$ADMIN_TOKEN" \
  '{"status":"triaged","customer_visible":true}')"
[ "$HTTP_CODE" = "200" ] || fail "Alert PATCH expected 200, got $HTTP_CODE"
jq -e '.alert.status == "triaged" and .alert.customer_visible == true' "$BODY_FILE" >/dev/null \
  || fail "Alert PATCH response did not contain updated values"
echo "OK: alert filters, internal detail, and triage update passed."

section "8. Incident list filters, detail, PATCH, and comments"
HTTP_CODE="$(api_call GET "/admin/incidents?status=open&severity=high&tenant_id=${TENANT_ID}" "$ADMIN_TOKEN")"
[ "$HTTP_CODE" = "200" ] || fail "Filtered incidents list expected 200, got $HTTP_CODE"
jq -e --arg id "$INCIDENT_ID" '
  (.incidents | any(.id == $id))
  and (.incidents | all(.status == "open" and .severity == "high"))
' "$BODY_FILE" >/dev/null || fail "Incident list filters did not constrain results correctly"
HTTP_CODE="$(api_call PATCH "/admin/incidents/${INCIDENT_ID}" "$ADMIN_TOKEN" \
  "$(jq -n --arg assignee "$ADMIN_USER_ID" \
    '{status:"in_progress",assigned_to_user_id:$assignee,customer_visible_summary:"Updated KB-056 customer summary"}')")"
[ "$HTTP_CODE" = "200" ] || fail "Incident PATCH expected 200, got $HTTP_CODE"
jq -e --arg assignee "$ADMIN_USER_ID" '
  .incident.status == "in_progress"
  and .incident.assigned_to_user_id == $assignee
  and .incident.customer_visible_summary == "Updated KB-056 customer summary"
  and (.timeline | length) == 1
' "$BODY_FILE" >/dev/null || fail "Incident PATCH/detail response is incorrect"
HTTP_CODE="$(api_call POST "/admin/incidents/${INCIDENT_ID}/comments" "$ADMIN_TOKEN" \
  '{"comment_text":"KB056 validation comment","visibility":"internal"}')"
[ "$HTTP_CODE" = "201" ] || fail "Incident comment POST expected 201, got $HTTP_CODE"
jq -e '.comment.comment_text == "KB056 validation comment" and .comment.visibility == "internal"' \
  "$BODY_FILE" >/dev/null || fail "Incident comment response is incorrect"
HTTP_CODE="$(api_call GET "/admin/incidents/${INCIDENT_ID}" "$ADMIN_TOKEN")"
[ "$HTTP_CODE" = "200" ] || fail "Incident detail expected 200, got $HTTP_CODE"
jq -e '
  .incident.internal_notes == "Internal KB-056 validation note"
  and (.timeline | length) == 1
  and (.comments | any(.comment_text == "KB056 validation comment"))
' "$BODY_FILE" >/dev/null || fail "Incident detail did not include timeline and comments"
echo "OK: incident filters, detail, triage, assignment, timeline, and comments passed."

section "9. Not-found behavior and Admin UI build"
HTTP_CODE="$(api_call GET "/admin/incidents/00000000-0000-0000-0000-000000000099" "$ADMIN_TOKEN")"
[ "$HTTP_CODE" = "404" ] || fail "Missing incident expected 404, got $HTTP_CODE"
docker compose exec -T frontend-admin npm run build \
  || fail "frontend-admin TypeScript/Vite build failed"
curl -fsS "$FRONTEND_BASE" -o /dev/null \
  || fail "Admin frontend is not reachable at $FRONTEND_BASE"
echo "OK: 404 behavior and Admin UI build passed."

section "10. Fixture cleanup and final verdict"
cleanup
LEFTOVER="$(psql_scalar "
  SELECT (
    (SELECT count(*) FROM security_alerts WHERE alert_title = '${ALERT_TITLE}')
    + (SELECT count(*) FROM incidents WHERE incident_number = '${INCIDENT_NUMBER}')
  )::text;
")" || fail "Could not verify fixture cleanup"
[ "$LEFTOVER" = "0" ] || fail "KB-056 fixture rows remain after cleanup"

echo "======================================================================"
echo "KB-056 ADMIN/SOC TRIAGE DASHBOARD ENHANCEMENTS VALIDATION PASSED"
echo "======================================================================"
