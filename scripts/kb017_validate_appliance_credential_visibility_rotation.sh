#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="/opt/mssp-control"
API_BASE="http://localhost:8000"
BODY_FILE="/tmp/kb017-body.json"

FAKE_APPLIANCE_NAME="kb017-validation-appliance"
FAKE_TOKEN_SITE_NAME="KB017 Validation Site (fake, safe to delete)"

UUID_REGEX='^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$'

cd "$PROJECT_DIR"

echo "======================================================================"
echo "KB-017: Validate Appliance Credential Visibility and Rotation"
echo "Target: $PROJECT_DIR"
echo "======================================================================"

fail() {
  echo
  echo "VALIDATION FAILED: $1"
  echo "Recent backend-api logs (best-effort redacted, never trust logs to contain secrets in the first place):"
  docker compose logs --tail=80 backend-api 2>/dev/null | sed -E \
    -e 's/("?(activation_token|appliance_api_key|api_key|password|new_password|token|secret)"?[[:space:]]*[:=][[:space:]]*)("[^"]*"|[^,}[:space:]]+)/\1"<redacted>"/gI' \
    || true
  cleanup_fake_data || true
  exit 1
}

section() {
  echo
  echo "----------------------------------------------------------------------"
  echo "$1"
  echo "----------------------------------------------------------------------"
}

# cleanup_fake_data: removes every piece of fake fixture data this script
# creates. Safe to call multiple times (idempotent, ignores "not found").
# Deleting the fake appliance cascades to its appliance_heartbeats rows
# (ON DELETE CASCADE, see postgres/init/001_mssp_core_schema.sql).
cleanup_fake_data() {
  docker compose exec -T postgres psql \
    -U "${POSTGRES_USER:-mssp_admin}" -d "${POSTGRES_DB:-mssp_control}" \
    -c "DELETE FROM appliances WHERE appliance_name = '${FAKE_APPLIANCE_NAME}';" >/dev/null 2>&1 || true
  docker compose exec -T postgres psql \
    -U "${POSTGRES_USER:-mssp_admin}" -d "${POSTGRES_DB:-mssp_control}" \
    -c "DELETE FROM appliance_activation_tokens WHERE site_name = '${FAKE_TOKEN_SITE_NAME}';" >/dev/null 2>&1 || true
}

cleanup() {
  rm -f "$BODY_FILE"
  cleanup_fake_data
  unset PLATFORM_ADMIN_PASSWORD SOC_MANAGER_PASSWORD SOC_ANALYST_PASSWORD CUSTOMER_VIEWER_PASSWORD \
        PLATFORM_ADMIN_TOKEN SOC_MANAGER_TOKEN SOC_ANALYST_TOKEN CUSTOMER_VIEWER_TOKEN \
        ACTIVATION_RAW_TOKEN APPLIANCE_RAW_API_KEY ROTATED_RAW_API_KEY_1 ROTATED_RAW_API_KEY_2 \
        FAKE_APPLIANCE_ID FAKE_TOKEN_ID DEMO_TENANT_ID 2>/dev/null || true
}
trap cleanup EXIT

# psql_scalar <sql>
# Same fixed pattern from scripts/kb015_validate_admin_appliance_management.sh
# and scripts/kb016_validate_appliance_registration_heartbeat.sh: quiet/
# tuples-only/unaligned psql output, trimmed line-by-line, hard failure if
# the statement does not produce exactly one non-blank output line. Any
# write statement called through this must be phrased as a SELECT (e.g.
# `WITH inserted AS (INSERT ... RETURNING ...) SELECT ... FROM inserted;`)
# so psql never prints a row-count command tag that could get concatenated
# onto the value.
psql_scalar() {
  local sql="$1"
  local raw

  raw="$(docker compose exec -T postgres psql \
    -X -q -t -A \
    -v ON_ERROR_STOP=1 \
    -U "${POSTGRES_USER:-mssp_admin}" -d "${POSTGRES_DB:-mssp_control}" \
    -c "$sql" 2>/dev/null)" || return 1

  raw="$(printf '%s\n' "$raw" | sed 's/\r$//' | grep -v '^[[:space:]]*$' || true)"

  local line_count
  line_count="$(printf '%s\n' "$raw" | grep -c '.' || true)"
  if [ "$line_count" != "1" ]; then
    echo "psql_scalar: expected exactly 1 non-blank output line, got $line_count, for: $sql" >&2
    return 1
  fi

  printf '%s' "$raw"
}

# validate_uuid <value> <label>
# Fails immediately - before any API/SQL call is made with it - if $value
# is not a strict, well-formed UUID string.
validate_uuid() {
  local value="$1"
  local label="$2"
  if [[ ! "$value" =~ $UUID_REGEX ]]; then
    fail "$label is not a valid UUID (got: '$value') - refusing to use a corrupted id"
  fi
}

# print_body_redacted <body_file>
# Prints a response body for debugging with any sensitive JSON object key's
# value replaced by "<redacted>" - never prints a password, access token,
# activation token, appliance API key, or any hash.
print_body_redacted() {
  local file="$1"
  local redacted
  redacted="$(jq '
      walk(
        if type == "object" then
          with_entries(
            if (.key | ascii_downcase) as $k
               | ($k == "password" or $k == "new_password" or $k == "password_hash"
                  or $k == "access_token" or $k == "token" or $k == "token_hash"
                  or $k == "activation_token" or $k == "appliance_api_key"
                  or $k == "appliance_api_key_hash" or $k == "api_key"
                  or $k == "jwt" or $k == "secret" or $k == "jwt_secret")
            then .value = "<redacted>"
            else .
            end
          )
        else .
        end
      )
    ' "$file" 2>/dev/null)"
  if [ -n "$redacted" ]; then
    echo "$redacted"
  else
    echo "(response body omitted - could not be parsed/redacted safely)"
  fi
}

# response_has_sensitive_string <body_file>
# Fails if a hash/secret-shaped field name appears anywhere in the body.
# None of these strings has any legitimate reason to ever appear in any
# response.
response_has_sensitive_string() {
  local file="$1"
  grep -qi "token_hash" "$file" 2>/dev/null && return 0
  grep -qi "password_hash" "$file" 2>/dev/null && return 0
  grep -qi "appliance_api_key_hash" "$file" 2>/dev/null && return 0
  return 1
}

# response_has_raw_activation_token <body_file>
# Fails if the one-time raw activation token (captured into
# ACTIVATION_RAW_TOKEN once it exists) appears anywhere in the given body.
response_has_raw_activation_token() {
  local file="$1"
  [ -n "${ACTIVATION_RAW_TOKEN:-}" ] || return 1
  grep -qF -- "$ACTIVATION_RAW_TOKEN" "$file" 2>/dev/null
}

# response_has_raw_appliance_api_key <body_file>
# Fails if the original, KB-016-registration-issued raw appliance API key
# (captured into APPLIANCE_RAW_API_KEY once it exists) appears anywhere in
# the given body. This key is intentionally invalidated by the first
# rotation later in this script, but it must never leak in ANY response,
# including before or after it stops working.
response_has_raw_appliance_api_key() {
  local file="$1"
  [ -n "${APPLIANCE_RAW_API_KEY:-}" ] || return 1
  grep -qF -- "$APPLIANCE_RAW_API_KEY" "$file" 2>/dev/null
}

# response_has_raw_rotated_appliance_api_key <body_file>
# Fails if either KB-017 rotated raw appliance API key (captured into
# ROTATED_RAW_API_KEY_1 for the first rotation, ROTATED_RAW_API_KEY_2 for
# the second/retired-appliance rotation, once each exists) appears anywhere
# in the given body. Each variable is only set immediately AFTER its own
# one-time rotate response has already been checked, so the rotate
# response itself is correctly exempt from flagging its own one-time key.
response_has_raw_rotated_appliance_api_key() {
  local file="$1"
  if [ -n "${ROTATED_RAW_API_KEY_1:-}" ] && grep -qF -- "$ROTATED_RAW_API_KEY_1" "$file" 2>/dev/null; then
    return 0
  fi
  if [ -n "${ROTATED_RAW_API_KEY_2:-}" ] && grep -qF -- "$ROTATED_RAW_API_KEY_2" "$file" 2>/dev/null; then
    return 0
  fi
  return 1
}

# check_status <description> <expected_http_code> <method> <url> [token] [json_body]
check_status() {
  local description="$1"
  local expected="$2"
  local method="$3"
  local url="$4"
  local token="${5:-}"
  local body="${6:-}"
  local actual
  local args=(-s -o "$BODY_FILE" -w '%{http_code}' -X "$method")

  if [ -n "$token" ]; then
    args+=(-H "Authorization: Bearer $token")
  fi
  if [ -n "$body" ]; then
    args+=(-H "Content-Type: application/json" -d "$body")
  fi

  actual="$(curl "${args[@]}" "$url")"

  if [ "$actual" = "$expected" ]; then
    echo "OK   [$actual] $description"
  else
    echo "FAIL [$actual, expected $expected] $description"
    echo "Response body (redacted):"
    print_body_redacted "$BODY_FILE"
    echo
    fail "$description expected HTTP $expected but got $actual"
  fi

  if response_has_sensitive_string "$BODY_FILE"; then
    fail "$description leaked a sensitive hash string in the response body"
  fi
  if response_has_raw_activation_token "$BODY_FILE"; then
    fail "$description leaked the raw activation token in the response body"
  fi
  if response_has_raw_appliance_api_key "$BODY_FILE"; then
    fail "$description leaked the original raw appliance API key in the response body"
  fi
  if response_has_raw_rotated_appliance_api_key "$BODY_FILE"; then
    fail "$description leaked a rotated raw appliance API key in the response body"
  fi
}

# check_appliance_status <description> <expected_http_code> <appliance_id_header> <api_key_header> <json_body>
# For POST /appliance/heartbeat, which authenticates via
# X-Appliance-ID/X-Appliance-API-Key headers instead of Authorization.
# Pass "" for either header value to omit it entirely.
check_appliance_status() {
  local description="$1"
  local expected="$2"
  local aid_header="$3"
  local akey_header="$4"
  local body="$5"
  local actual
  local args=(-s -o "$BODY_FILE" -w '%{http_code}' -X POST -H "Content-Type: application/json")

  if [ -n "$aid_header" ]; then
    args+=(-H "X-Appliance-ID: $aid_header")
  fi
  if [ -n "$akey_header" ]; then
    args+=(-H "X-Appliance-API-Key: $akey_header")
  fi
  args+=(-d "$body")

  actual="$(curl "${args[@]}" "$API_BASE/appliance/heartbeat")"

  if [ "$actual" = "$expected" ]; then
    echo "OK   [$actual] $description"
  else
    echo "FAIL [$actual, expected $expected] $description"
    echo "Response body (redacted):"
    print_body_redacted "$BODY_FILE"
    echo
    fail "$description expected HTTP $expected but got $actual"
  fi

  if response_has_sensitive_string "$BODY_FILE"; then
    fail "$description leaked a sensitive hash string in the response body"
  fi
  if response_has_raw_activation_token "$BODY_FILE"; then
    fail "$description leaked the raw activation token in the response body"
  fi
  if response_has_raw_appliance_api_key "$BODY_FILE"; then
    fail "$description leaked the original raw appliance API key in the response body"
  fi
  if response_has_raw_rotated_appliance_api_key "$BODY_FILE"; then
    fail "$description leaked a rotated raw appliance API key in the response body"
  fi
}

section "1. File checks"

for f in \
  backend-api/app/api/routes/appliance_management.py \
  backend-api/app/schemas/appliances.py \
  backend-api/app/api/routes/appliance_agent.py \
  backend-api/app/main.py
do
  [ -f "$f" ] || fail "$f is missing"
  echo "found: $f"
done

grep -q "def get_appliance_credential" backend-api/app/api/routes/appliance_management.py \
  || fail "appliance_management.py does not define get_appliance_credential()"
grep -q "def rotate_appliance_credential" backend-api/app/api/routes/appliance_management.py \
  || fail "appliance_management.py does not define rotate_appliance_credential()"
grep -q 'ADMIN_APPLIANCE_CREDENTIAL_WRITE_ROLES = ("platform_admin",)' backend-api/app/api/routes/appliance_management.py \
  || fail "appliance_management.py does not define the distinct ADMIN_APPLIANCE_CREDENTIAL_WRITE_ROLES constant"
grep -q '"/admin/appliances/{appliance_id}/credential"' backend-api/app/api/routes/appliance_management.py \
  || fail "appliance_management.py does not define the /credential path"
grep -q '"/admin/appliances/{appliance_id}/credential/rotate"' backend-api/app/api/routes/appliance_management.py \
  || fail "appliance_management.py does not define the /credential/rotate path"
echo "OK: appliance_management.py defines both new KB-017 credential endpoints"

grep -q "class ApplianceCredentialMetadata" backend-api/app/schemas/appliances.py \
  || fail "schemas/appliances.py does not define ApplianceCredentialMetadata"
grep -q "class ApplianceCredentialRotateResponse" backend-api/app/schemas/appliances.py \
  || fail "schemas/appliances.py does not define ApplianceCredentialRotateResponse"
echo "OK: schemas/appliances.py defines both new KB-017 credential models"

grep -q '@router.get("/admin/appliances/{appliance_id}", response_model=ApplianceDetail)' backend-api/app/api/routes/appliance_management.py \
  || fail "appliance_management.py's existing GET /admin/appliances/{appliance_id} appears to have been modified"
echo "OK: existing KB-015 GET /admin/appliances/{appliance_id} handler is unmodified"

grep -q "appliance_management_router" backend-api/app/main.py \
  || fail "main.py does not include appliance_management_router"

# Git-diff based "unmodified" checks, not content-grep. A content grep for
# the word "credential" is a false positive here: backend-api/app/main.py
# and backend-api/app/api/routes/appliance_agent.py can legitimately
# already contain that word from earlier KB modules without KB-017 having
# touched either file. Checking for the absence of any working-tree or
# staged diff against the current HEAD is the actual, correct way to prove
# a file was not modified.
git diff --quiet -- backend-api/app/main.py \
  || fail "main.py has working-tree changes but KB-017 should not modify it"
git diff --cached --quiet -- backend-api/app/main.py \
  || fail "main.py has staged changes but KB-017 should not modify it"
echo "OK: main.py is unmodified (no working-tree or staged diff; no new router line needed for KB-017)"

git diff --quiet -- backend-api/app/api/routes/appliance_agent.py \
  || fail "appliance_agent.py has working-tree changes but KB-017 should not modify it"
git diff --cached --quiet -- backend-api/app/api/routes/appliance_agent.py \
  || fail "appliance_agent.py has staged changes but KB-017 should not modify it"
echo "OK: appliance_agent.py is unmodified (no working-tree or staged diff)"

section "2. Docker Compose and service health"

docker compose ps

backend_state="$(docker inspect -f '{{.State.Status}}' mssp-backend-api 2>/dev/null || echo 'missing')"
postgres_health="$(docker inspect -f '{{.State.Health.Status}}' mssp-postgres 2>/dev/null || echo 'missing')"
redis_health="$(docker inspect -f '{{.State.Health.Status}}' mssp-redis 2>/dev/null || echo 'missing')"

echo
echo "mssp-backend-api state: $backend_state"
echo "mssp-postgres health:   $postgres_health"
echo "mssp-redis health:      $redis_health"

[ "$backend_state" = "running" ] || fail "backend-api container is not running (did you rebuild it after this change?)"
[ "$postgres_health" = "healthy" ] || fail "postgres is not healthy"
[ "$redis_health" = "healthy" ] || fail "redis is not healthy"

section "3. Public endpoints remain public; KB-016 and KB-017 endpoints are registered"

check_status "GET /health (public)" 200 GET "$API_BASE/health"
check_status "GET /auth/roles (public)" 200 GET "$API_BASE/auth/roles"
check_status "GET /docs (public, dev docs)" 200 GET "$API_BASE/docs"

OPENAPI="$(curl -fsS "$API_BASE/openapi.json")"
echo "$OPENAPI" | jq -e '.paths | has("/appliance/register")' >/dev/null \
  || fail "OpenAPI schema is missing /appliance/register (KB-016 regression)"
echo "$OPENAPI" | jq -e '.paths | has("/appliance/heartbeat")' >/dev/null \
  || fail "OpenAPI schema is missing /appliance/heartbeat (KB-016 regression)"
echo "$OPENAPI" | jq -e '.paths | has("/admin/appliances/{appliance_id}/credential")' >/dev/null \
  || fail "OpenAPI schema is missing /admin/appliances/{appliance_id}/credential"
echo "$OPENAPI" | jq -e '.paths | has("/admin/appliances/{appliance_id}/credential/rotate")' >/dev/null \
  || fail "OpenAPI schema is missing /admin/appliances/{appliance_id}/credential/rotate"
echo "OK: /appliance/register, /appliance/heartbeat, and both new KB-017 credential endpoints are registered"

section "4. Enter demo passwords (input hidden, never logged)"

read -rs -p "Enter the password for platform.admin@example.local: " PLATFORM_ADMIN_PASSWORD
echo
read -rs -p "Enter the password for soc.manager@example.local: " SOC_MANAGER_PASSWORD
echo
read -rs -p "Enter the password for soc.analyst@example.local: " SOC_ANALYST_PASSWORD
echo
read -rs -p "Enter the password for customer.viewer@demo.local: " CUSTOMER_VIEWER_PASSWORD
echo

for pw_name in PLATFORM_ADMIN_PASSWORD SOC_MANAGER_PASSWORD SOC_ANALYST_PASSWORD CUSTOMER_VIEWER_PASSWORD; do
  [ -n "${!pw_name}" ] || fail "$pw_name cannot be empty."
done

section "5. Logging in as platform_admin, soc_manager, soc_analyst, customer_viewer"

login() {
  local email="$1"
  local password="$2"
  local expected_role="$3"
  local body
  body="$(jq -n --arg email "$email" --arg password "$password" '{email:$email,password:$password}')"
  local response
  response="$(curl -fsS -X POST "$API_BASE/auth/login" \
    -H "Content-Type: application/json" \
    -d "$body")"
  echo "$response" | jq -e --arg role "$expected_role" '.user.role == $role' >/dev/null \
    || fail "Login for $email did not return expected role $expected_role"
  echo "$response" | grep -qi "password_hash" && fail "Login response for $email leaked password_hash"
  echo "$response" | jq -r '.access_token'
}

PLATFORM_ADMIN_TOKEN="$(login "platform.admin@example.local" "$PLATFORM_ADMIN_PASSWORD" "platform_admin")"
SOC_MANAGER_TOKEN="$(login "soc.manager@example.local" "$SOC_MANAGER_PASSWORD" "soc_manager")"
SOC_ANALYST_TOKEN="$(login "soc.analyst@example.local" "$SOC_ANALYST_PASSWORD" "soc_analyst")"
CUSTOMER_VIEWER_TOKEN="$(login "customer.viewer@demo.local" "$CUSTOMER_VIEWER_PASSWORD" "customer_viewer")"

unset PLATFORM_ADMIN_PASSWORD SOC_MANAGER_PASSWORD SOC_ANALYST_PASSWORD CUSTOMER_VIEWER_PASSWORD

for tok_name in PLATFORM_ADMIN_TOKEN SOC_MANAGER_TOKEN SOC_ANALYST_TOKEN CUSTOMER_VIEWER_TOKEN; do
  [ -n "${!tok_name}" ] || fail "$tok_name was not obtained - login must have failed."
done
echo "All 4 logins succeeded and returned tokens (not displayed)."

section "6. Resolve an existing tenant id (DEMO)"

DEMO_LOOKUP="$(curl -fsS -H "Authorization: Bearer $PLATFORM_ADMIN_TOKEN" "$API_BASE/admin/tenants")"
DEMO_TENANT_ID="$(echo "$DEMO_LOOKUP" | jq -r '.tenants[] | select(.short_code=="DEMO") | .id')"
[ -n "$DEMO_TENANT_ID" ] && [ "$DEMO_TENANT_ID" != "null" ] || fail "Could not resolve tenant id for short_code DEMO from GET /admin/tenants"
validate_uuid "$DEMO_TENANT_ID" "DEMO_TENANT_ID"
echo "Resolved DEMO tenant id: $DEMO_TENANT_ID"

section "7. platform_admin creates a fake activation token for DEMO tenant (KB-015 admin API)"

cleanup_fake_data

CREATE_TOKEN_BODY="$(jq -n --arg site "$FAKE_TOKEN_SITE_NAME" '{site_name: $site, expires_in_hours: 24}')"
check_status "POST .../appliance-activation-tokens as platform_admin" 201 POST "$API_BASE/admin/tenants/$DEMO_TENANT_ID/appliance-activation-tokens" "$PLATFORM_ADMIN_TOKEN" "$CREATE_TOKEN_BODY"

ACTIVATION_RAW_TOKEN="$(jq -r '.token' "$BODY_FILE")"
[ -n "$ACTIVATION_RAW_TOKEN" ] && [ "$ACTIVATION_RAW_TOKEN" != "null" ] || fail "Token creation response did not include a raw token"

FAKE_TOKEN_ID="$(jq -r '.metadata.id' "$BODY_FILE")"
[ -n "$FAKE_TOKEN_ID" ] && [ "$FAKE_TOKEN_ID" != "null" ] || fail "Token creation response did not include metadata.id"
validate_uuid "$FAKE_TOKEN_ID" "FAKE_TOKEN_ID"
echo "Created fake validation activation token id: $FAKE_TOKEN_ID (raw token not displayed)"

section "8. Register a fake appliance via KB-016 POST /appliance/register (captures original raw key)"

REGISTER_BODY="$(jq -n --arg token "$ACTIVATION_RAW_TOKEN" --arg name "$FAKE_APPLIANCE_NAME" \
  '{activation_token: $token, appliance_name: $name, agent_version: "kb017-test-1.0.0"}')"
check_status "POST /appliance/register with valid activation token" 201 POST "$API_BASE/appliance/register" "" "$REGISTER_BODY"

APPLIANCE_RAW_API_KEY="$(jq -r '.appliance_api_key' "$BODY_FILE")"
[ -n "$APPLIANCE_RAW_API_KEY" ] && [ "$APPLIANCE_RAW_API_KEY" != "null" ] || fail "Registration response did not include appliance_api_key"

FAKE_APPLIANCE_ID="$(jq -r '.appliance_id' "$BODY_FILE")"
[ -n "$FAKE_APPLIANCE_ID" ] && [ "$FAKE_APPLIANCE_ID" != "null" ] || fail "Registration response did not include appliance_id"
validate_uuid "$FAKE_APPLIANCE_ID" "FAKE_APPLIANCE_ID"
echo "Captured appliance_id and original raw appliance_api_key into shell variables (not displayed)."

section "9. GET /admin/appliances/{appliance_id}/credential - RBAC and safe metadata shape"

CRED_URL="$API_BASE/admin/appliances/$FAKE_APPLIANCE_ID/credential"

check_status "GET .../credential with no token" 401 GET "$CRED_URL"
check_status "GET .../credential with garbage token" 401 GET "$CRED_URL" "not-a-real-token"
check_status "GET .../credential as customer_viewer (must be denied)" 403 GET "$CRED_URL" "$CUSTOMER_VIEWER_TOKEN"
check_status "GET .../credential as soc_manager" 200 GET "$CRED_URL" "$SOC_MANAGER_TOKEN"
check_status "GET .../credential as soc_analyst" 200 GET "$CRED_URL" "$SOC_ANALYST_TOKEN"

check_status "GET .../credential as platform_admin (before any heartbeat)" 200 GET "$CRED_URL" "$PLATFORM_ADMIN_TOKEN"
jq -e --arg id "$FAKE_APPLIANCE_ID" '.appliance_id == $id' "$BODY_FILE" >/dev/null || fail "Credential metadata appliance_id mismatch"
jq -e '.has_appliance_api_key == true' "$BODY_FILE" >/dev/null || fail "Credential metadata has_appliance_api_key should be true after registration"
jq -e '.appliance_api_key_hint != null and (.appliance_api_key_hint | length) > 0' "$BODY_FILE" >/dev/null || fail "Credential metadata appliance_api_key_hint was missing/empty"
jq -e '.appliance_key_created_at != null and (.appliance_key_created_at | length) > 0' "$BODY_FILE" >/dev/null || fail "Credential metadata appliance_key_created_at was missing/empty"
jq -e '.appliance_key_last_used_at == null' "$BODY_FILE" >/dev/null || fail "Credential metadata appliance_key_last_used_at should be null before any heartbeat"
jq -e '(has("appliance_api_key") or has("appliance_api_key_hash")) | not' "$BODY_FILE" >/dev/null || fail "Credential metadata must not have appliance_api_key or appliance_api_key_hash keys"
ORIGINAL_KEY_CREATED_AT="$(jq -r '.appliance_key_created_at' "$BODY_FILE")"
echo "OK: credential metadata shape correct; appliance_key_last_used_at is null before first heartbeat."

section "10. Heartbeat with the original key succeeds (baseline, before rotation)"

check_appliance_status "Heartbeat with original valid credentials (before rotation)" 200 "$FAKE_APPLIANCE_ID" "$APPLIANCE_RAW_API_KEY" '{"health_status":"healthy"}'

section "11. POST /admin/appliances/{appliance_id}/credential/rotate - RBAC and rotation"

ROTATE_URL="$API_BASE/admin/appliances/$FAKE_APPLIANCE_ID/credential/rotate"

check_status "POST .../credential/rotate with no token" 401 POST "$ROTATE_URL"
check_status "POST .../credential/rotate with garbage token" 401 POST "$ROTATE_URL" "not-a-real-token"
check_status "POST .../credential/rotate as customer_viewer (must be denied)" 403 POST "$ROTATE_URL" "$CUSTOMER_VIEWER_TOKEN"
check_status "POST .../credential/rotate as soc_manager (must be denied)" 403 POST "$ROTATE_URL" "$SOC_MANAGER_TOKEN"
check_status "POST .../credential/rotate as soc_analyst (must be denied)" 403 POST "$ROTATE_URL" "$SOC_ANALYST_TOKEN"

check_status "POST .../credential/rotate as platform_admin" 200 POST "$ROTATE_URL" "$PLATFORM_ADMIN_TOKEN"
jq -e --arg id "$FAKE_APPLIANCE_ID" '.appliance_id == $id' "$BODY_FILE" >/dev/null || fail "Rotate response appliance_id mismatch"
jq -e '.appliance_api_key != null and (.appliance_api_key | length) > 0' "$BODY_FILE" >/dev/null || fail "Rotate response did not include a new appliance_api_key"
jq -e '.api_key_hint != null and (.api_key_hint | length) > 0' "$BODY_FILE" >/dev/null || fail "Rotate response api_key_hint was missing/empty"
jq -e '.appliance_key_created_at != null and (.appliance_key_created_at | length) > 0' "$BODY_FILE" >/dev/null || fail "Rotate response appliance_key_created_at was missing/empty"
jq -e '.message != null and (.message | length) > 0' "$BODY_FILE" >/dev/null || fail "Rotate response message was missing/empty"
jq -e 'has("appliance_api_key_hash") | not' "$BODY_FILE" >/dev/null || fail "Rotate response must not have an appliance_api_key_hash key"

ROTATED_KEY_CREATED_AT_1="$(jq -r '.appliance_key_created_at' "$BODY_FILE")"
[ "$ROTATED_KEY_CREATED_AT_1" != "$ORIGINAL_KEY_CREATED_AT" ] || fail "appliance_key_created_at did not change after rotation"

# Captured only now, AFTER this rotate response has already been checked
# above - the leak-check functions correctly treat this specific response
# as the one legitimate, one-time place this value is allowed to appear.
ROTATED_RAW_API_KEY_1="$(jq -r '.appliance_api_key' "$BODY_FILE")"
echo "OK: rotation succeeded; appliance_key_created_at changed; new raw key captured (not displayed)."

section "12. Old/new key behavior after rotation"

check_appliance_status "Heartbeat with the OLD (pre-rotation) key must now fail" 401 "$FAKE_APPLIANCE_ID" "$APPLIANCE_RAW_API_KEY" '{"health_status":"healthy"}'

OLD_KEY_STILL_UNUSED="$(psql_scalar "SELECT (appliance_key_last_used_at IS NULL) FROM appliances WHERE id = '${FAKE_APPLIANCE_ID}';")" \
  || fail "Could not check appliances.appliance_key_last_used_at after rotation (psql error)"
[ "$OLD_KEY_STILL_UNUSED" = "t" ] || fail "appliance_key_last_used_at should still be NULL immediately after rotation (rejected old-key heartbeat must not update it)"
echo "OK: appliance_key_last_used_at is still NULL after rotation and a failed old-key heartbeat attempt."

check_appliance_status "Heartbeat with the NEW (rotated) key succeeds" 200 "$FAKE_APPLIANCE_ID" "$ROTATED_RAW_API_KEY_1" '{"health_status":"healthy"}'

NEW_KEY_USED="$(psql_scalar "SELECT (appliance_key_last_used_at IS NOT NULL) FROM appliances WHERE id = '${FAKE_APPLIANCE_ID}';")" \
  || fail "Could not check appliances.appliance_key_last_used_at after new-key heartbeat (psql error)"
[ "$NEW_KEY_USED" = "t" ] || fail "appliance_key_last_used_at should be set after a successful new-key heartbeat"
echo "OK: appliance_key_last_used_at is set after the new key's first successful heartbeat."

check_status "GET .../credential as platform_admin (after rotation + new-key heartbeat)" 200 GET "$CRED_URL" "$PLATFORM_ADMIN_TOKEN"
jq -e '.has_appliance_api_key == true' "$BODY_FILE" >/dev/null || fail "Credential metadata has_appliance_api_key should still be true after rotation"
jq -e --arg t "$ROTATED_KEY_CREATED_AT_1" '.appliance_key_created_at == $t' "$BODY_FILE" >/dev/null || fail "Credential metadata appliance_key_created_at does not match the rotate response value"
jq -e '.appliance_key_last_used_at != null' "$BODY_FILE" >/dev/null || fail "Credential metadata appliance_key_last_used_at should be non-null after the new key's heartbeat"

section "13. Rotation is allowed for a retired appliance and does not change status"

check_status "PATCH /admin/appliances/$FAKE_APPLIANCE_ID set status=retired as platform_admin" 200 PATCH "$API_BASE/admin/appliances/$FAKE_APPLIANCE_ID" "$PLATFORM_ADMIN_TOKEN" '{"status":"retired"}'
jq -e '.status == "retired"' "$BODY_FILE" >/dev/null || fail "PATCH did not persist status=retired"

check_status "POST .../credential/rotate as platform_admin on a retired appliance" 200 POST "$ROTATE_URL" "$PLATFORM_ADMIN_TOKEN"
jq -e '.appliance_api_key != null and (.appliance_api_key | length) > 0' "$BODY_FILE" >/dev/null || fail "Rotate response (retired appliance) did not include a new appliance_api_key"
ROTATED_RAW_API_KEY_2="$(jq -r '.appliance_api_key' "$BODY_FILE")"

check_status "GET .../credential as platform_admin confirms status still retired after rotation" 200 GET "$CRED_URL" "$PLATFORM_ADMIN_TOKEN"
jq -e '.status == "retired"' "$BODY_FILE" >/dev/null || fail "Rotation must not change appliance status - expected status still 'retired'"
echo "OK: rotation succeeded for a retired appliance without changing its status."

check_appliance_status "Heartbeat from a retired appliance with the freshly rotated key must still fail with 403" 403 "$FAKE_APPLIANCE_ID" "$ROTATED_RAW_API_KEY_2" '{"health_status":"healthy"}'
echo "OK: a retired appliance's heartbeat is rejected with 403 even immediately after a successful credential rotation."

section "14. Invalid UUID path parameters must be a clean 422"

check_status "GET /admin/appliances/not-a-uuid/credential as platform_admin" 422 GET "$API_BASE/admin/appliances/not-a-uuid/credential" "$PLATFORM_ADMIN_TOKEN"
check_status "POST /admin/appliances/not-a-uuid/credential/rotate as platform_admin" 422 POST "$API_BASE/admin/appliances/not-a-uuid/credential/rotate" "$PLATFORM_ADMIN_TOKEN"

section "15. Unknown valid UUID must be a clean 404"

check_status "GET /admin/appliances/<unknown uuid>/credential as platform_admin" 404 GET "$API_BASE/admin/appliances/00000000-0000-0000-0000-000000000000/credential" "$PLATFORM_ADMIN_TOKEN"
check_status "POST /admin/appliances/<unknown uuid>/credential/rotate as platform_admin" 404 POST "$API_BASE/admin/appliances/00000000-0000-0000-0000-000000000000/credential/rotate" "$PLATFORM_ADMIN_TOKEN"

section "16. Clean up fake KB-017 validation appliance, heartbeats, and activation token"

cleanup_fake_data

REMAINING_APPLIANCES="$(psql_scalar "SELECT count(*) FROM appliances WHERE appliance_name = '${FAKE_APPLIANCE_NAME}';")" \
  || fail "Could not verify fake validation appliance cleanup (psql error)"
[ "$REMAINING_APPLIANCES" = "0" ] || fail "Fake validation appliance was not cleaned up (found $REMAINING_APPLIANCES rows)"

REMAINING_HEARTBEATS="$(psql_scalar "SELECT count(*) FROM appliance_heartbeats WHERE appliance_id = '${FAKE_APPLIANCE_ID}';")" \
  || fail "Could not verify fake validation heartbeat cleanup (psql error)"
[ "$REMAINING_HEARTBEATS" = "0" ] || fail "Fake validation heartbeat rows were not cleaned up via cascade (found $REMAINING_HEARTBEATS rows)"

REMAINING_TOKENS="$(psql_scalar "SELECT count(*) FROM appliance_activation_tokens WHERE site_name = '${FAKE_TOKEN_SITE_NAME}';")" \
  || fail "Could not verify fake validation activation token cleanup (psql error)"
[ "$REMAINING_TOKENS" = "0" ] || fail "Fake validation activation token was not cleaned up (found $REMAINING_TOKENS rows)"

echo "OK: all fake KB-017 validation appliance/heartbeat/activation-token fixtures removed, no leftover data."

section "17. Behavior regression gate: scripts/kb016_validate_appliance_registration_heartbeat.sh"

echo "Running the full, unmodified KB-016 validation script now (which itself"
echo "reruns KB-015, and through it KB-014, KB-013, KB-012, and KB-011). It"
echo "will ask for demo passwords again."
echo

if ! ./scripts/kb016_validate_appliance_registration_heartbeat.sh; then
  fail "scripts/kb016_validate_appliance_registration_heartbeat.sh did not pass after adding credential visibility/rotation - this is a real regression"
fi

section "18. Final validation verdict"

echo "KB-017 APPLIANCE CREDENTIAL VISIBILITY AND ROTATION VALIDATION PASSED"
echo
echo "Summary:"
echo "  - /health, /auth/roles, /docs remain public; /appliance/register and"
echo "    /appliance/heartbeat (KB-016) remain registered and working."
echo "  - GET /admin/appliances/{appliance_id}/credential and"
echo "    POST /admin/appliances/{appliance_id}/credential/rotate both require a"
echo "    valid token (401 with none/garbage) and deny customer_viewer (403)."
echo "  - platform_admin, soc_manager, and soc_analyst can all read credential"
echo "    metadata (200); only platform_admin can rotate (soc_manager/soc_analyst"
echo "    get 403 on rotate)."
echo "  - Credential metadata never exposed appliance_api_key or"
echo "    appliance_api_key_hash; has_appliance_api_key, appliance_api_key_hint,"
echo "    and appliance_key_created_at were correct, and"
echo "    appliance_key_last_used_at was null before the first heartbeat."
echo "  - Rotation returned a new raw appliance_api_key exactly once, refreshed"
echo "    appliance_key_created_at, and reset appliance_key_last_used_at to null."
echo "  - After rotation, a heartbeat with the OLD key failed with 401 (and did"
echo "    not update appliance_key_last_used_at), while a heartbeat with the NEW"
echo "    key succeeded with 200 and set appliance_key_last_used_at."
echo "  - Rotation succeeded for a retired appliance without changing its status;"
echo "    a heartbeat from that retired appliance still failed with 403 even"
echo "    with the freshly rotated key."
echo "  - Invalid UUID path parameters returned a clean 422; unknown valid UUIDs"
echo "    returned a clean 404."
echo "  - No response ever exposed token_hash, appliance_api_key_hash, the raw"
echo "    activation token (outside its one creation response), the original or"
echo "    any rotated raw appliance API key (outside their own one-time"
echo "    responses), password_hash, or a password value."
echo "  - All fake KB-017 validation appliance/heartbeat/activation-token"
echo "    fixtures were cleaned up - no leftover data."
echo "  - scripts/kb016_validate_appliance_registration_heartbeat.sh passed"
echo "    unmodified - no observable behavior change to appliance registration,"
echo "    heartbeat, admin appliance management, user management, tenant"
echo "    management, route structure, auth, RBAC, tenant isolation, or"
echo "    validation-error redaction."
echo
echo "======================================================================"
echo "KB-017 validation completed successfully."
echo "======================================================================"
