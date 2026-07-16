#!/usr/bin/env bash
# KB-035: Validate Customer Appliance Detail API + UI.
# Interactive: prompts for customer.viewer@demo.local password (never hardcoded).
# Optional: CUSTOMER_VIEWER_PASSWORD env for non-interactive runs.
# Creates temporary DEMO/DEMO2 appliances and protected assets, then cleans them up.
set -euo pipefail

PROJECT_DIR="/opt/mssp-control"
API_BASE="http://localhost:8000"
FRONTEND_BASE="http://localhost:3001"
BODY_FILE="/tmp/kb035-body.txt"
LOGIN_FILE="/tmp/kb035-login.json"

DEMO_APPLIANCE_NAME="KB035 DEMO appliance"
DEMO2_APPLIANCE_NAME="KB035 DEMO2 appliance"
DEMO_ASSET_HOSTNAME="kb035-demo-asset-host"
DEMO2_ASSET_HOSTNAME="kb035-demo2-asset-host"

FIXTURE_DEMO_APPLIANCE_ID=""
FIXTURE_DEMO2_APPLIANCE_ID=""
FIXTURE_DEMO_ASSET_ID=""

cd "$PROJECT_DIR"

echo "======================================================================"
echo "KB-035: Validate Customer Appliance Detail UI"
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
      DELETE FROM protected_assets
      WHERE hostname IN (
        '${DEMO_ASSET_HOSTNAME}',
        '${DEMO2_ASSET_HOSTNAME}'
      );
      DELETE FROM appliances
      WHERE appliance_name IN (
        '${DEMO_APPLIANCE_NAME}',
        '${DEMO2_APPLIANCE_NAME}'
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
  [ "$response" = "200" ] || return 1
  token="$(jq -r '.access_token // empty' "$LOGIN_FILE")"
  role="$(jq -r '.user.role // empty' "$LOGIN_FILE")"
  [ -n "$token" ] || return 1
  [ "$role" = "$expected_role" ] || return 1
  echo "$token"
}

assert_safe_detail_payload() {
  local label="$1"
  local file="$2"

  jq -e '
    (. | keys | sort) == ["appliance","tenant"]
    and (.tenant | has("id") and has("name") and has("short_code"))
    and (.appliance | type == "object")
  ' "$file" >/dev/null \
    || fail "$label top-level / tenant shape invalid"

  jq -e '
    (.appliance | keys)
    | all(.[]; . == "appliance_id" or . == "appliance_name" or . == "site_name"
        or . == "status" or . == "last_seen_at" or . == "health_status"
        or . == "cpu_percent" or . == "memory_percent" or . == "disk_percent"
        or . == "agent_version" or . == "config_version" or . == "update_status"
        or . == "latest_heartbeat_at" or . == "protected_assets_count"
        or . == "protected_assets")
  ' "$file" >/dev/null \
    || fail "$label appliance object has unexpected keys"

  jq -e '
    (.appliance.protected_assets | type == "array")
    and (.appliance.protected_assets | all(
      (. | keys)
      | all(.[]; . == "asset_id" or . == "hostname" or . == "asset_type"
          or . == "criticality" or . == "status" or . == "last_seen_at")
    ))
  ' "$file" >/dev/null \
    || fail "$label protected_assets entries have unexpected keys"

  local hit
  hit="$(jq -r '
    def check($path):
      if type == "object" then
        (keys_unsorted[] as $k
          | ($k | ascii_downcase) as $kd
          | if ($kd == "tenant_id"
                or ($kd == "appliance_id" and ($path | test("^appliance$") | not))
                or ($kd == "asset_id" and ($path | test("^appliance\\.protected_assets\\.[0-9]+$") | not))
                or $kd == "protected_asset_id"
                or $kd == "ip_address"
                or $kd == "source_ip"
                or $kd == "local_ip"
                or $kd == "last_source_ip"
                or $kd == "details"
                or $kd == "raw_json"
                or $kd == "raw_event"
                or $kd == "health_snapshot"
                or $kd == "appliance_uuid"
                or $kd == "appliance_api_key_hash"
                or $kd == "appliance_api_key_hint"
                or $kd == "api_key"
                or $kd == "token"
                or $kd == "token_hash"
                or $kd == "password"
                or $kd == "password_hash"
                or $kd == "internal_notes"
                or $kd == "admin_notes"
                or $kd == "stack_trace"
                or $kd == "git_commit"
                or $kd == "created_at"
                or $kd == "updated_at"
                or ($kd == "id" and $path != "tenant"))
            then $k
            else empty
            end),
        (to_entries[] | .key as $k | .value | check(if $path == "" then $k else ($path + "." + $k) end))
      elif type == "array" then
        to_entries[] | .key as $i | .value | check($path + "." + ($i | tostring))
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
  "frontend-customer/src/pages/AssetsPage.tsx"
  "frontend-customer/src/pages/ApplianceDetailPage.tsx"
  "frontend-customer/src/App.tsx"
  "scripts/kb035_validate_customer_appliance_detail_ui.sh"
  "docs/KB035_CUSTOMER_APPLIANCE_DETAIL_UI.md"
)

for f in "${REQUIRED[@]}"; do
  [ -f "$f" ] || fail "$f is missing"
  echo "found: $f"
done

section "2. Protected paths must remain unmodified"

for p in frontend-admin/ postgres/init/ docker-compose.yml; do
  git diff --quiet -- "$p" || fail "$p has working-tree changes but KB-035 must not modify it"
  git diff --cached --quiet -- "$p" || fail "$p has staged changes but KB-035 must not modify it"
  echo "OK: $p unmodified"
done

if git status --porcelain -- .env 2>/dev/null | grep -q .; then
  fail ".env shows as changed/untracked"
fi
echo "OK: .env not changed/untracked."

section "3. Backend source: appliance detail endpoint"

grep -q '@router.get("/appliances/{short_code}/{appliance_id}")' backend-api/app/api/routes/customer.py \
  || fail "customer.py missing GET /appliances/{short_code}/{appliance_id}"
grep -q 'def customer_appliance_detail' backend-api/app/api/routes/customer.py \
  || fail "customer.py missing customer_appliance_detail"
grep -q 'a.id::text AS appliance_id' backend-api/app/api/routes/customer.py \
  || fail "customer.py list query must expose appliance_id"
grep -q 'a.tenant_id = %s' backend-api/app/api/routes/customer.py \
  || fail "customer.py missing tenant filter"
grep -q 'a.id = %s' backend-api/app/api/routes/customer.py \
  || fail "customer.py missing appliance id filter"

DETAIL_BLOCK="$(awk '/def customer_appliance_detail\(/,/^    return /' backend-api/app/api/routes/customer.py)"
SELECT_BLOCK="$(echo "$DETAIL_BLOCK" | awk '/SELECT/,/WHERE a.tenant_id/')"
for forbidden in local_ip last_source_ip source_ip health_snapshot appliance_uuid \
  appliance_api_key_hash appliance_api_key_hint git_commit tenant_id; do
  if echo "$SELECT_BLOCK" | grep -qE "(^|[[:space:]]+)${forbidden}([[:space:]]|,|$|AS)"; then
    fail "customer_appliance_detail SELECT must not expose $forbidden"
  fi
done
echo "OK: appliance detail route present with tenant + id filters and safe SELECT."

section "4. Frontend: getCustomerApplianceDetail + appliance links + no /admin"

grep -q 'getCustomerApplianceDetail' frontend-customer/src/api/customer.ts \
  || fail "customer.ts missing getCustomerApplianceDetail"
grep -q '/customer/appliances/' frontend-customer/src/api/customer.ts \
  || fail "customer.ts missing /customer/appliances/ path"
grep -q 'getCustomerApplianceDetail' frontend-customer/src/pages/ApplianceDetailPage.tsx \
  || fail "ApplianceDetailPage.tsx must call getCustomerApplianceDetail"
grep -q 'appliances/:applianceId' frontend-customer/src/App.tsx \
  || fail "App.tsx missing /appliances/:applianceId route"
grep -q '/appliances/' frontend-customer/src/pages/AssetsPage.tsx \
  || fail "AssetsPage.tsx must link appliances to detail route"

if grep -REn '/admin' frontend-customer/src 2>/dev/null; then
  fail "frontend-customer/src must not contain /admin"
fi
echo "OK: frontend uses customer appliance detail paths and has no /admin."

section "5. Rebuild backend-api so the new route is live"

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

section "6. OpenAPI lists detail route"

OPENAPI="$(curl -fsS "$API_BASE/openapi.json" || fail "Could not fetch OpenAPI")"
echo "$OPENAPI" | jq -e '.paths | has("/customer/appliances/{short_code}/{appliance_id}")' >/dev/null \
  || fail "OpenAPI missing /customer/appliances/{short_code}/{appliance_id}"
echo "OK: OpenAPI registers appliance detail route."

section "7. Unauthenticated access returns 401"

HTTP_CODE="$(curl -sS -o "$BODY_FILE" -w "%{http_code}" \
  "$API_BASE/customer/appliances/DEMO/00000000-0000-0000-0000-000000000001" || true)"
[ "$HTTP_CODE" = "401" ] || fail "Unauthenticated detail request expected 401, got $HTTP_CODE"
echo "OK: unauthenticated request returns 401."

section "8. Create temporary KB-035 fixtures"

cleanup_fixtures

DEMO_TENANT_ID="$(psql_scalar "SELECT id::text FROM tenants WHERE short_code = 'DEMO';")" \
  || fail "Could not resolve DEMO tenant id"
DEMO2_TENANT_ID="$(psql_scalar "SELECT id::text FROM tenants WHERE short_code = 'DEMO2';")" \
  || fail "Could not resolve DEMO2 tenant id"

FIXTURE_DEMO_APPLIANCE_ID="$(psql_scalar "
WITH inserted AS (
  INSERT INTO appliances (
    tenant_id, appliance_name, site_name, status, config_version, update_status
  ) VALUES (
    '${DEMO_TENANT_ID}',
    '${DEMO_APPLIANCE_NAME}',
    'KB035 DEMO Site',
    'online',
    'cfg-1.0',
    'current'
  )
  RETURNING id
)
SELECT id::text FROM inserted;
")" || fail "Could not create DEMO appliance fixture"

FIXTURE_DEMO2_APPLIANCE_ID="$(psql_scalar "
WITH inserted AS (
  INSERT INTO appliances (
    tenant_id, appliance_name, site_name, status
  ) VALUES (
    '${DEMO2_TENANT_ID}',
    '${DEMO2_APPLIANCE_NAME}',
    'KB035 DEMO2 Site',
    'online'
  )
  RETURNING id
)
SELECT id::text FROM inserted;
")" || fail "Could not create DEMO2 appliance fixture"

FIXTURE_DEMO_ASSET_ID="$(psql_scalar "
WITH inserted AS (
  INSERT INTO protected_assets (
    tenant_id, appliance_id, hostname, asset_type, criticality, status, os_name, owner
  ) VALUES (
    '${DEMO_TENANT_ID}',
    '${FIXTURE_DEMO_APPLIANCE_ID}',
    '${DEMO_ASSET_HOSTNAME}',
    'server',
    'high',
    'active',
    'Ubuntu 22.04',
    'KB035 Demo Owner'
  )
  RETURNING id
)
SELECT id::text FROM inserted;
")" || fail "Could not create DEMO protected asset fixture"

echo "OK: temporary DEMO/DEMO2 appliance fixtures created."

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

section "10. DEMO customer can fetch DEMO appliance detail (200)"

HTTP_CODE="$(curl -sS -o "$BODY_FILE" -w "%{http_code}" \
  -H "Authorization: Bearer $CUSTOMER_VIEWER_TOKEN" \
  "$API_BASE/customer/appliances/DEMO/${FIXTURE_DEMO_APPLIANCE_ID}" || true)"
[ "$HTTP_CODE" = "200" ] || fail "DEMO appliance detail expected 200, got $HTTP_CODE ($(cat "$BODY_FILE"))"

jq -e --arg id "$FIXTURE_DEMO_APPLIANCE_ID" --arg name "$DEMO_APPLIANCE_NAME" \
  --arg asset "$FIXTURE_DEMO_ASSET_ID" --arg host "$DEMO_ASSET_HOSTNAME" '
  .tenant.short_code == "DEMO"
  and .appliance.appliance_id == $id
  and .appliance.appliance_name == $name
  and .appliance.site_name == "KB035 DEMO Site"
  and .appliance.config_version == "cfg-1.0"
  and .appliance.update_status == "current"
  and .appliance.protected_assets_count == 1
  and (.appliance.protected_assets | length) == 1
  and .appliance.protected_assets[0].asset_id == $asset
  and .appliance.protected_assets[0].hostname == $host
' "$BODY_FILE" >/dev/null \
  || fail "DEMO appliance detail body missing expected fixture data"

assert_safe_detail_payload "DEMO appliance detail" "$BODY_FILE"
echo "OK: DEMO appliance detail 200."

section "11. DEMO customer gets 404 for DEMO2 appliance detail"

HTTP_CODE="$(curl -sS -o "$BODY_FILE" -w "%{http_code}" \
  -H "Authorization: Bearer $CUSTOMER_VIEWER_TOKEN" \
  "$API_BASE/customer/appliances/DEMO2/${FIXTURE_DEMO2_APPLIANCE_ID}" || true)"
[ "$HTTP_CODE" = "404" ] || fail "DEMO2 detail as DEMO viewer expected 404, got $HTTP_CODE"

HTTP_CODE="$(curl -sS -o "$BODY_FILE" -w "%{http_code}" \
  -H "Authorization: Bearer $CUSTOMER_VIEWER_TOKEN" \
  "$API_BASE/customer/appliances/DEMO/${FIXTURE_DEMO2_APPLIANCE_ID}" || true)"
[ "$HTTP_CODE" = "404" ] || fail "DEMO2 appliance id under DEMO short_code expected 404, got $HTTP_CODE"
echo "OK: cross-tenant appliance detail returns 404."

section "12. DEMO customer gets 404 for nonexistent appliance UUID"

HTTP_CODE="$(curl -sS -o "$BODY_FILE" -w "%{http_code}" \
  -H "Authorization: Bearer $CUSTOMER_VIEWER_TOKEN" \
  "$API_BASE/customer/appliances/DEMO/00000000-0000-0000-0000-000000000099" || true)"
[ "$HTTP_CODE" = "404" ] || fail "Nonexistent appliance detail expected 404, got $HTTP_CODE"
echo "OK: nonexistent appliance detail returns 404."

section "13. Assets list includes appliance_id"

HTTP_CODE="$(curl -sS -o "$BODY_FILE" -w "%{http_code}" \
  -H "Authorization: Bearer $CUSTOMER_VIEWER_TOKEN" \
  "$API_BASE/customer/assets/DEMO" || true)"
[ "$HTTP_CODE" = "200" ] || fail "DEMO assets list expected 200, got $HTTP_CODE"
jq -e --arg id "$FIXTURE_DEMO_APPLIANCE_ID" \
  '[.appliances[] | select(.appliance_id == $id)] | length == 1' "$BODY_FILE" >/dev/null \
  || fail "DEMO assets list missing fixture appliance_id"
echo "OK: assets list includes appliance_id."

section "14. Frontend build"

if docker compose exec -T frontend-customer npm run build; then
  echo "OK: npm run build succeeded inside frontend-customer."
else
  fail "npm run build failed inside frontend-customer"
fi

section "15. Final verdict"

echo "======================================================================"
echo "KB-035 CUSTOMER APPLIANCE DETAIL UI VALIDATION PASSED"
echo "======================================================================"
echo
echo "Manually open $FRONTEND_BASE, sign in as customer.viewer@demo.local,"
echo "open Assets, click an appliance name, and confirm detail + linked assets."
