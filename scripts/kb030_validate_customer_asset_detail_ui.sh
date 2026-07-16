#!/usr/bin/env bash
# KB-030: Validate Customer Protected Asset Detail API + UI.
# Interactive: prompts for customer.viewer@demo.local password (never hardcoded).
# Optional: CUSTOMER_VIEWER_PASSWORD env for non-interactive runs.
# Creates temporary DEMO/DEMO2 protected_assets (and optional appliances), then cleans them up.
set -euo pipefail

PROJECT_DIR="/opt/mssp-control"
API_BASE="http://localhost:8000"
FRONTEND_BASE="http://localhost:3001"
BODY_FILE="/tmp/kb030-body.txt"
LOGIN_FILE="/tmp/kb030-login.json"

DEMO_ASSET_HOSTNAME="kb030-demo-asset-host"
DEMO2_ASSET_HOSTNAME="kb030-demo2-asset-host"
DEMO_APPLIANCE_NAME="KB030 DEMO appliance"
DEMO2_APPLIANCE_NAME="KB030 DEMO2 appliance"

FIXTURE_DEMO_ASSET_ID=""
FIXTURE_DEMO2_ASSET_ID=""

cd "$PROJECT_DIR"

echo "======================================================================"
echo "KB-030: Validate Customer Protected Asset Detail UI"
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
    (. | keys | sort) == ["asset","tenant"]
    and (.tenant | has("id") and has("name") and has("short_code"))
    and (.asset | type == "object")
  ' "$file" >/dev/null \
    || fail "$label top-level / tenant shape invalid"

  jq -e '
    (.asset | keys)
    | all(.[]; . == "asset_id" or . == "hostname" or . == "asset_type"
        or . == "criticality" or . == "status" or . == "os_name" or . == "owner"
        or . == "last_seen_at" or . == "appliance_name" or . == "site_name")
  ' "$file" >/dev/null \
    || fail "$label asset object has unexpected keys"

  local hit
  hit="$(jq -r '
    def check($path):
      if type == "object" then
        (keys_unsorted[] as $k
          | ($k | ascii_downcase) as $kd
          | if ($kd == "tenant_id"
                or $kd == "appliance_id"
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
                or $kd == "created_at"
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
  "frontend-customer/src/pages/AssetsPage.tsx"
  "frontend-customer/src/pages/AssetDetailPage.tsx"
  "frontend-customer/src/App.tsx"
  "scripts/kb030_validate_customer_asset_detail_ui.sh"
  "docs/KB030_CUSTOMER_ASSET_DETAIL_UI.md"
)

for f in "${REQUIRED[@]}"; do
  [ -f "$f" ] || fail "$f is missing"
  echo "found: $f"
done

section "2. Protected paths must remain unmodified"

for p in frontend-admin/ postgres/init/ docker-compose.yml; do
  git diff --quiet -- "$p" || fail "$p has working-tree changes but KB-030 must not modify it"
  git diff --cached --quiet -- "$p" || fail "$p has staged changes but KB-030 must not modify it"
  echo "OK: $p unmodified"
done

if git status --porcelain -- .env 2>/dev/null | grep -q .; then
  fail ".env shows as changed/untracked"
fi
echo "OK: .env not changed/untracked."

section "3. Backend source: asset detail endpoint"

grep -q '@router.get("/assets/{short_code}/{asset_id}")' backend-api/app/api/routes/customer.py \
  || fail "customer.py missing GET /assets/{short_code}/{asset_id}"
grep -q 'def customer_asset_detail' backend-api/app/api/routes/customer.py \
  || fail "customer.py missing customer_asset_detail"
grep -q 'require_tenant_match' backend-api/app/api/routes/customer.py \
  || fail "customer.py missing require_tenant_match"
grep -q 'FROM protected_assets' backend-api/app/api/routes/customer.py \
  || fail "customer.py missing protected_assets query"
grep -q 'pa.tenant_id = %s' backend-api/app/api/routes/customer.py \
  || fail "customer.py missing pa.tenant_id filter"
grep -q 'pa.id = %s' backend-api/app/api/routes/customer.py \
  || fail "customer.py missing pa.id filter"

DETAIL_BLOCK="$(awk '/def customer_asset_detail\(/,/^    return /' backend-api/app/api/routes/customer.py)"
SELECT_BLOCK="$(echo "$DETAIL_BLOCK" | awk '/SELECT/,/FROM protected_assets/')"
for forbidden in appliance_id ip_address details health_snapshot appliance_uuid \
  appliance_api_key_hash appliance_api_key_hint local_ip last_source_ip source_ip \
  created_at updated_at; do
  if echo "$SELECT_BLOCK" | grep -qE "(^|[[:space:]]+)${forbidden}([[:space:]]|,|$|AS)"; then
    fail "customer_asset_detail SELECT must not expose $forbidden"
  fi
done
echo "OK: asset detail route present with tenant + id filters and safe SELECT."

section "4. Frontend: getCustomerAssetDetail + no /admin"

grep -q 'getCustomerAssetDetail' frontend-customer/src/api/customer.ts \
  || fail "customer.ts missing getCustomerAssetDetail"
grep -q '/customer/assets/' frontend-customer/src/api/customer.ts \
  || fail "customer.ts missing /customer/assets/ path"
grep -q 'getCustomerAssetDetail' frontend-customer/src/pages/AssetDetailPage.tsx \
  || fail "AssetDetailPage.tsx must call getCustomerAssetDetail"
grep -q 'assets/:assetId' frontend-customer/src/App.tsx \
  || fail "App.tsx missing /assets/:assetId route"
grep -q '/assets/' frontend-customer/src/pages/AssetsPage.tsx \
  || fail "AssetsPage.tsx must link protected assets to detail route"

# Appliance rows must remain plain text (no Link wrapping appliance_name in appliances table)
APPLIANCE_TD_COUNT="$(grep -c '<td>{row.appliance_name}</td>' frontend-customer/src/pages/AssetsPage.tsx || true)"
[ "$APPLIANCE_TD_COUNT" -ge 1 ] || fail "AssetsPage appliance name should remain plain text (no detail link)"
if grep -n 'to=.*appliance' frontend-customer/src/pages/AssetsPage.tsx 2>/dev/null; then
  fail "AssetsPage must not link appliance rows to appliance detail"
fi

if grep -REn '/admin' frontend-customer/src 2>/dev/null; then
  fail "frontend-customer/src must not contain /admin"
fi
echo "OK: frontend uses customer asset detail paths and has no /admin."

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
echo "$OPENAPI" | jq -e '.paths | has("/customer/assets/{short_code}/{asset_id}")' >/dev/null \
  || fail "OpenAPI missing /customer/assets/{short_code}/{asset_id}"
echo "OK: OpenAPI registers asset detail route."

section "7. Unauthenticated access returns 401"

HTTP_CODE="$(curl -sS -o "$BODY_FILE" -w "%{http_code}" \
  "$API_BASE/customer/assets/DEMO/00000000-0000-0000-0000-000000000001" || true)"
[ "$HTTP_CODE" = "401" ] || fail "Unauthenticated detail request expected 401, got $HTTP_CODE"
echo "OK: unauthenticated request returns 401."

section "8. Create temporary KB-030 fixtures"

cleanup_fixtures

DEMO_TENANT_ID="$(psql_scalar "SELECT id::text FROM tenants WHERE short_code = 'DEMO';")" \
  || fail "Could not resolve DEMO tenant id"
DEMO2_TENANT_ID="$(psql_scalar "SELECT id::text FROM tenants WHERE short_code = 'DEMO2';")" \
  || fail "Could not resolve DEMO2 tenant id"

DEMO_APPLIANCE_ID="$(psql_scalar "
WITH inserted AS (
  INSERT INTO appliances (tenant_id, appliance_name, site_name, status)
  VALUES (
    '${DEMO_TENANT_ID}',
    '${DEMO_APPLIANCE_NAME}',
    'KB030 DEMO Site',
    'online'
  )
  RETURNING id
)
SELECT id::text FROM inserted;
")" || fail "Could not create DEMO appliance fixture"

DEMO2_APPLIANCE_ID="$(psql_scalar "
WITH inserted AS (
  INSERT INTO appliances (tenant_id, appliance_name, site_name, status)
  VALUES (
    '${DEMO2_TENANT_ID}',
    '${DEMO2_APPLIANCE_NAME}',
    'KB030 DEMO2 Site',
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
    '${DEMO_APPLIANCE_ID}',
    '${DEMO_ASSET_HOSTNAME}',
    'server',
    'high',
    'active',
    'Ubuntu 22.04',
    'KB030 Demo Owner'
  )
  RETURNING id
)
SELECT id::text FROM inserted;
")" || fail "Could not create DEMO protected asset"

FIXTURE_DEMO2_ASSET_ID="$(psql_scalar "
WITH inserted AS (
  INSERT INTO protected_assets (
    tenant_id, appliance_id, hostname, asset_type, criticality, status, os_name, owner
  ) VALUES (
    '${DEMO2_TENANT_ID}',
    '${DEMO2_APPLIANCE_ID}',
    '${DEMO2_ASSET_HOSTNAME}',
    'workstation',
    'medium',
    'active',
    'Windows 11',
    'KB030 Demo2 Owner'
  )
  RETURNING id
)
SELECT id::text FROM inserted;
")" || fail "Could not create DEMO2 protected asset"

echo "OK: temporary DEMO/DEMO2 asset fixtures created."

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

section "10. DEMO customer can fetch DEMO asset detail (200)"

HTTP_CODE="$(curl -sS -o "$BODY_FILE" -w "%{http_code}" \
  -H "Authorization: Bearer $CUSTOMER_VIEWER_TOKEN" \
  "$API_BASE/customer/assets/DEMO/${FIXTURE_DEMO_ASSET_ID}" || true)"
[ "$HTTP_CODE" = "200" ] || fail "DEMO asset detail expected 200, got $HTTP_CODE ($(cat "$BODY_FILE"))"

jq -e --arg id "$FIXTURE_DEMO_ASSET_ID" --arg h "$DEMO_ASSET_HOSTNAME" \
  --arg an "$DEMO_APPLIANCE_NAME" '
  .tenant.short_code == "DEMO"
  and .asset.asset_id == $id
  and .asset.hostname == $h
  and .asset.appliance_name == $an
  and .asset.site_name == "KB030 DEMO Site"
' "$BODY_FILE" >/dev/null \
  || fail "DEMO asset detail body missing expected fixture data"

assert_safe_detail_payload "DEMO asset detail" "$BODY_FILE"
echo "OK: DEMO asset detail 200."

section "11. DEMO customer gets 404 for DEMO2 asset detail"

HTTP_CODE="$(curl -sS -o "$BODY_FILE" -w "%{http_code}" \
  -H "Authorization: Bearer $CUSTOMER_VIEWER_TOKEN" \
  "$API_BASE/customer/assets/DEMO2/${FIXTURE_DEMO2_ASSET_ID}" || true)"
[ "$HTTP_CODE" = "404" ] || fail "DEMO2 detail as DEMO viewer expected 404, got $HTTP_CODE"

HTTP_CODE="$(curl -sS -o "$BODY_FILE" -w "%{http_code}" \
  -H "Authorization: Bearer $CUSTOMER_VIEWER_TOKEN" \
  "$API_BASE/customer/assets/DEMO/${FIXTURE_DEMO2_ASSET_ID}" || true)"
[ "$HTTP_CODE" = "404" ] || fail "DEMO2 asset id under DEMO short_code expected 404, got $HTTP_CODE"
echo "OK: cross-tenant asset detail returns 404."

section "12. DEMO customer gets 404 for nonexistent asset UUID"

HTTP_CODE="$(curl -sS -o "$BODY_FILE" -w "%{http_code}" \
  -H "Authorization: Bearer $CUSTOMER_VIEWER_TOKEN" \
  "$API_BASE/customer/assets/DEMO/00000000-0000-0000-0000-000000000099" || true)"
[ "$HTTP_CODE" = "404" ] || fail "Nonexistent asset detail expected 404, got $HTTP_CODE"
echo "OK: nonexistent asset detail returns 404."

section "13. Frontend build"

if docker compose exec -T frontend-customer npm run build; then
  echo "OK: npm run build succeeded inside frontend-customer."
else
  fail "npm run build failed inside frontend-customer"
fi

section "14. Docs present"

[ -f "docs/KB030_CUSTOMER_ASSET_DETAIL_UI.md" ] || fail "docs/KB030_CUSTOMER_ASSET_DETAIL_UI.md missing"
grep -q 'GET /customer/assets' docs/KB030_CUSTOMER_ASSET_DETAIL_UI.md \
  || fail "docs missing endpoint documentation"
grep -qi 'protected_assets' docs/KB030_CUSTOMER_ASSET_DETAIL_UI.md \
  || fail "docs missing protected_assets explanation"
echo "OK: completion docs present."

section "15. Cleanup fixtures verification"

cleanup_fixtures
REMAINING_ASSETS="$(psql_scalar "
  SELECT count(*) FROM protected_assets
  WHERE hostname IN (
    '${DEMO_ASSET_HOSTNAME}',
    '${DEMO2_ASSET_HOSTNAME}'
  );
")" || fail "Could not verify asset fixture cleanup"
[ "$REMAINING_ASSETS" = "0" ] || fail "KB-030 asset fixtures not cleaned up (remaining=$REMAINING_ASSETS)"

REMAINING_APPLIANCES="$(psql_scalar "
  SELECT count(*) FROM appliances
  WHERE appliance_name IN (
    '${DEMO_APPLIANCE_NAME}',
    '${DEMO2_APPLIANCE_NAME}'
  );
")" || fail "Could not verify appliance fixture cleanup"
[ "$REMAINING_APPLIANCES" = "0" ] || fail "KB-030 appliance fixtures not cleaned up (remaining=$REMAINING_APPLIANCES)"
echo "OK: temporary fixtures cleaned up."

section "16. Manual browser note"

echo "curl validates API auth/tenant isolation and frontend build."
echo "Manually open $FRONTEND_BASE, sign in as customer.viewer@demo.local,"
echo "open Assets, click a protected-asset hostname, and confirm read-only detail."
echo "Confirm appliance rows are not clickable detail links."

section "17. Final verdict"

echo "======================================================================"
echo "KB-030 CUSTOMER ASSET DETAIL UI VALIDATION PASSED"
echo "======================================================================"
